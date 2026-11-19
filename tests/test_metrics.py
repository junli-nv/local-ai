import contextlib
import io
import unittest
from unittest.mock import patch

from local_ai import cli, metrics


def snapshot(waiting, kv, count):
    return metrics.parse_metrics(
        f"""
vllm:num_requests_running{{engine="0"}} 6
vllm:num_requests_waiting{{engine="0"}} {waiting}
vllm:kv_cache_usage_perc{{engine="0"}} {kv}
vllm:num_preemptions_total{{engine="0"}} {count}
vllm:prefix_cache_queries{{engine="0"}} {count * 10}
vllm:prefix_cache_hits{{engine="0"}} {count * 8}
vllm:request_queue_time_seconds_bucket{{engine="0",le="0.2"}} {count}
vllm:request_queue_time_seconds_bucket{{le="+Inf",engine="0"}} {count * 2}
"""
    )


class MetricsTests(unittest.TestCase):
    def test_cli_reads_saved_endpoint_once(self):
        output = io.StringIO()
        with (
            patch.object(cli, "settings", return_value={"endpoint": "http://model:8000/v1"}),
            patch.object(metrics, "fetch", return_value=snapshot(0, 0.72, 6)) as fetch,
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(cli.main(["client", "metrics"]), 0)
        fetch.assert_called_once_with("http://model:8000/metrics")
        self.assertIn("72%", output.getvalue())
        self.assertIn("KV cache usage", output.getvalue())
        self.assertNotIn("Sampling complete", output.getvalue())

    def test_loop_uses_window_deltas_and_prints_each_sample(self):
        output = io.StringIO()
        rows = [snapshot(2, 0.72, 20), snapshot(0, 0.65, 21), snapshot(1, 0.73, 23)]
        with (
            patch.object(metrics, "fetch", side_effect=rows) as fetch,
            patch.object(metrics.time, "sleep") as sleep,
            contextlib.redirect_stdout(output),
        ):
            self.assertEqual(
                cli.main(
                    [
                        "client",
                        "metrics",
                        "--endpoint",
                        "https://model/proxy/v1/",
                        "--count",
                        "3",
                        "--lang",
                        "zh",
                    ]
                ),
                0,
            )
        self.assertEqual(fetch.call_count, 3)
        self.assertEqual(fetch.call_args.args, ("https://model/proxy/metrics",))
        self.assertEqual(sleep.call_count, 2)
        self.assertIn("3 次有效采样中有 2 次排队、1 次队列为空", output.getvalue())
        self.assertIn("KV 缓存池最高 73%", output.getvalue())
        self.assertIn("新增抢占 3 次", output.getvalue())
        self.assertIn("命中率 80%", output.getvalue())
        self.assertIn("排队中位数 ≤ 0.2 秒（6 个）", output.getvalue())
        self.assertIn("首 token 中位数 不可用", output.getvalue())

    def test_failed_sample_preserves_rows_but_invalidates_window_totals(self):
        output, errors = io.StringIO(), io.StringIO()
        with (
            patch.object(metrics, "fetch", side_effect=[OSError("timeout"), snapshot(0, 0, 5)]),
            patch.object(metrics.time, "sleep"),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(errors),
        ):
            self.assertEqual(metrics.probe("http://model/v1", 2, 2, "zh"), 1)
        self.assertIn("1/2 次成功", output.getvalue())
        self.assertIn("新增抢占 不可用", output.getvalue())
        self.assertIn("timeout", errors.getvalue())

    def test_reset_and_small_histogram(self):
        start, middle, end = snapshot(0, 0, 10), snapshot(0, 0, 1), snapshot(0, 0, 15)
        self.assertIsNone(metrics.changes([start, middle, end], metrics.PREEMPTIONS))
        self.assertEqual(
            metrics.median([middle, snapshot(0, 0, 2)], metrics.QUEUE_TIME, "zh"),
            "样本不足（2 个）",
        )

    def test_partial_and_multi_engine_snapshot(self):
        row = metrics.parse_metrics(
            'vllm:kv_cache_usage_perc{engine="0"} 0.7\n'
            'vllm:kv_cache_usage_perc{engine="1"} 0.9\n'
            'vllm:num_requests_running{engine="0"} 2\n'
            'vllm:num_requests_running{engine="1"} 3\n'
            "vllm:num_requests_waiting NaN"
        )
        self.assertEqual(metrics.gauge(row, metrics.RUNNING), 5)
        self.assertEqual(metrics.gauge(row, metrics.KV), 0.9)
        self.assertIsNone(metrics.gauge(row, metrics.WAITING))
