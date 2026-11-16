import contextlib
import fcntl
import io
import json
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

import test_warmup

from local_ai import benchmark
from local_ai.cli import main, parser


@contextlib.contextmanager
def streaming_api(mode="normal", delay=0.02, tokenize_delay=0):
    calls = []
    active = {"count": 0, "peak": 0}
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.send_response(200)
            self.end_headers()

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            try:
                if self.path == "/tokenize":
                    time.sleep(tokenize_delay)
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(json.dumps({"tokens": list(data["prompt"].encode())}).encode())
                    return
                if mode == "http":
                    self.send_response(500)
                    self.end_headers()
                    return
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream; charset=utf-8")
                self.end_headers()
                with lock:
                    calls.append(data)
                    active["count"] += 1
                    active["peak"] = max(active["peak"], active["count"])

                def send(value):
                    self.wfile.write(b"data: " + json.dumps(value).encode() + b"\n\n")
                    self.wfile.flush()

                try:
                    send({"choices": [{"text": "", "finish_reason": None}]})
                    time.sleep(delay)
                    if mode == "error":
                        send({"error": {"message": "synthetic failure"}})
                        return
                    send({"choices": [{"text": "a", "finish_reason": None}]})
                    time.sleep(delay)
                    if mode == "disconnect":
                        return
                    send(
                        {
                            "choices": [
                                {
                                    "text": "b",
                                    "finish_reason": ("stop" if mode == "early" else "length"),
                                }
                            ]
                        }
                    )
                    if mode != "missing-usage":
                        send(
                            {
                                "choices": [],
                                "usage": {
                                    "prompt_tokens": len(data["prompt"]),
                                    "completion_tokens": data["max_tokens"] + (mode == "bad-count"),
                                },
                            }
                        )
                    self.wfile.write(b"data: [DONE]\n\n")
                    self.wfile.flush()
                finally:
                    with lock:
                        active["count"] -= 1
            except OSError:
                pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as http:
        worker = threading.Thread(
            target=lambda: http.serve_forever(poll_interval=0.01), daemon=True
        )
        worker.start()
        try:
            yield http.server_port, calls, active
        finally:
            http.shutdown()
            worker.join(timeout=2)


class BenchmarkTests(unittest.TestCase):
    def fixture(self, root, port=18000):
        return test_warmup.WarmupTests().fixture(str(Path(root).resolve()), port)

    def run_benchmark(self, spec, container, **options):
        with contextlib.redirect_stderr(io.StringIO()):
            return benchmark.run(
                spec, Mock(return_value=container), input_tokens=64, output_tokens=8, **options
            )

    def test_stream_timing_usage_warmup_exclusion_and_persistence(self):
        with (
            tempfile.TemporaryDirectory() as root,
            streaming_api(tokenize_delay=0.01) as (port, calls, _),
        ):
            spec, container, directory = self.fixture(root, port)
            value = self.run_benchmark(spec, container, repeats=2)
            measured = value["summary"]
            self.assertTrue(value["completed"])
            self.assertEqual(measured["requests"], 2)
            self.assertEqual(len(calls), 3)
            self.assertEqual(len(value["warmup"]["rounds"]), 1)
            self.assertGreater(value["warmup"]["elapsed_seconds"], 0.03)
            self.assertGreater(measured["first_chunk_seconds"]["mean"], 0.015)
            self.assertGreater(measured["request_seconds"]["mean"], 0.035)
            self.assertLess(
                measured["first_chunk_seconds"]["mean"], measured["request_seconds"]["mean"]
            )
            self.assertEqual(
                measured["aggregate_output_tokens_per_second"], 16 / measured["elapsed_seconds"]
            )
            self.assertGreater(value["elapsed_seconds"], measured["elapsed_seconds"] + 0.03)
            self.assertEqual(
                json.loads(next(directory.glob("benchmark-*.json")).read_text()), value
            )
            self.assertFalse((directory / "warmup.json").exists())
            self.assertTrue(all(c["ignore_eos"] and c["stream"] for c in calls))
            self.assertTrue(all(len(c["prompt"]) == 64 and c["max_tokens"] == 8 for c in calls))
            self.assertEqual(len({tuple(c["prompt"]) for c in calls}), 3)

    def test_concurrency_and_zero_warmup(self):
        with tempfile.TemporaryDirectory() as root, streaming_api() as (port, calls, active):
            spec, container, _ = self.fixture(root, port)
            value = self.run_benchmark(spec, container, concurrency=3, repeats=2, warmup_rounds=0)
            self.assertEqual(value["summary"]["requests"], 6)
            self.assertEqual(len(calls), 6)
            self.assertEqual(active["peak"], 3)
            self.assertEqual(value["warmup"]["rounds"], [])

    def test_failed_stream_never_reports_success_or_estimated_token_counts(self):
        for mode in ("missing-usage", "bad-count", "disconnect", "error", "early", "http"):
            with (
                self.subTest(mode=mode),
                tempfile.TemporaryDirectory() as root,
                streaming_api(mode) as (port, _, _),
            ):
                spec, container, directory = self.fixture(root, port)
                with self.assertRaisesRegex(RuntimeError, "Benchmark failed"):
                    self.run_benchmark(spec, container, repeats=1, warmup_rounds=0)
                value = json.loads(next(directory.glob("benchmark-*.json")).read_text())
                self.assertEqual(value["state"], "failed")
                self.assertFalse(value["completed"])
                self.assertNotIn("summary", value)
                self.assertTrue(container["State"]["Running"])

    def test_timeout_interrupts_stream_and_tokenization(self):
        for options in ({"delay": 1}, {"tokenize_delay": 1}):
            with (
                self.subTest(options=options),
                tempfile.TemporaryDirectory() as root,
                streaming_api(**options) as (port, _, _),
            ):
                spec, container, directory = self.fixture(root, port)
                before = time.monotonic()
                with self.assertRaisesRegex(RuntimeError, "Benchmark failed"):
                    self.run_benchmark(spec, container, timeout=0.1, repeats=1)
                self.assertLess(time.monotonic() - before, 0.8)
                self.assertEqual(
                    json.loads(next(directory.glob("benchmark-*.json")).read_text())["state"],
                    "failed",
                )

    def test_cancel_saves_record_and_keeps_instance(self):
        with tempfile.TemporaryDirectory() as root:
            spec, container, directory = self.fixture(root)
            with (
                patch("local_ai.benchmark.readiness.probe", return_value={"ready": True}),
                patch("local_ai.benchmark.Transport.tokenize", side_effect=KeyboardInterrupt),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    self.run_benchmark(spec, container)
            value = json.loads(next(directory.glob("benchmark-*.json")).read_text())
            self.assertEqual(value["state"], "cancelled")
            self.assertNotIn("summary", value)
            self.assertTrue(container["State"]["Running"])

    def test_restart_invalidates_results(self):
        with tempfile.TemporaryDirectory() as root, streaming_api() as (port, _, _):
            spec, container, directory = self.fixture(root, port)
            restarted = {"State": {"Running": True, "StartedAt": "new-start"}}
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaisesRegex(RuntimeError, "restarted"):
                    benchmark.run(
                        spec,
                        Mock(side_effect=[container, container, restarted]),
                        input_tokens=64,
                        output_tokens=8,
                        repeats=1,
                        warmup_rounds=0,
                    )
            value = json.loads(next(directory.glob("benchmark-*.json")).read_text())
            self.assertFalse(value["completed"])
            self.assertNotIn("summary", value)

    def test_bounds_fail_before_network_and_files(self):
        with tempfile.TemporaryDirectory() as root:
            spec, container, directory = self.fixture(root)
            for options in (
                {"input_tokens": 0},
                {"output_tokens": 0},
                {"repeats": 0},
                {"warmup_rounds": -1},
                {"timeout": 0},
                {"concurrency": 0},
                {"concurrency": 65},
                {"input_tokens": 4096},
            ):
                with (
                    self.subTest(options=options),
                    patch("local_ai.benchmark.Transport") as transport,
                ):
                    with self.assertRaises(ValueError):
                        benchmark.run(spec, Mock(return_value=container), **options)
                    transport.assert_not_called()
            self.assertFalse(list(directory.glob("benchmark-*.json")))
            self.assertFalse((directory / ".warmup.lock").exists())

    def test_shared_warmup_lock_rejects_overlap(self):
        with tempfile.TemporaryDirectory() as root:
            spec, container, directory = self.fixture(root)
            with (directory / ".warmup.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                with self.assertRaisesRegex(RuntimeError, "already running"):
                    self.run_benchmark(spec, container)

    def test_stopped_unready_or_missing_identity_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            spec, container, directory = self.fixture(root)
            for current in (None, {"State": {"Running": False}}, {"State": {"Running": True}}):
                with self.assertRaises(RuntimeError):
                    self.run_benchmark(spec, current)
            with patch("local_ai.benchmark.readiness.probe", return_value={"ready": False}):
                with self.assertRaisesRegex(RuntimeError, "not ready"):
                    self.run_benchmark(spec, container)
            self.assertFalse(list(directory.glob("benchmark-*.json")))

    def test_cli_defaults_and_custom_shape_json(self):
        args = parser().parse_args(["server", "benchmark"])
        self.assertEqual(
            (
                args.name,
                args.input_tokens,
                args.output_tokens,
                args.concurrency,
                args.repeats,
                args.warmup_rounds,
                args.timeout,
            ),
            ("a", 1024, 256, 1, 3, 1, 600),
        )
        output = io.StringIO()
        with (
            patch("local_ai.cli.server.managed_spec", return_value={}) as managed,
            patch("local_ai.cli.benchmark.run", return_value={"completed": True}) as run,
            contextlib.redirect_stdout(output),
        ):
            code = main(
                [
                    "server",
                    "benchmark",
                    "--name",
                    "b",
                    "--data-dir",
                    "/tmp/bench",
                    "--input-tokens",
                    "128",
                    "--output-tokens",
                    "16",
                    "--concurrency",
                    "2",
                    "--repeats",
                    "4",
                    "--warmup-rounds",
                    "0",
                    "--timeout",
                    "20",
                ]
            )
        self.assertEqual(code, 0)
        self.assertTrue(json.loads(output.getvalue())["completed"])
        self.assertEqual(managed.call_args.args[1], "b")
        self.assertEqual(
            run.call_args.kwargs,
            {
                "input_tokens": 128,
                "output_tokens": 16,
                "concurrency": 2,
                "repeats": 4,
                "warmup_rounds": 0,
                "timeout": 20,
            },
        )

    def test_percentiles_and_rate_definitions(self):
        rows = [
            {
                "first_chunk_seconds": n / 10,
                "elapsed_seconds": n,
                "output_tokens": 8,
                "output_tokens_per_second": 8 / n,
            }
            for n in range(1, 21)
        ]
        value = benchmark.summary(rows, 100)
        self.assertEqual(value["first_chunk_seconds"]["p95"], 1.9)
        self.assertEqual(value["request_seconds"]["median"], 10.5)
        self.assertEqual(value["aggregate_output_tokens_per_second"], 1.6)

    def test_cli_reads_managed_instance_and_preserves_json_stdout(self):
        with tempfile.TemporaryDirectory() as root, streaming_api() as (port, _, _):
            _, container, directory = self.fixture(root, port)
            output, progress = io.StringIO(), io.StringIO()
            with (
                patch("local_ai.server.inspect_container", return_value=container),
                contextlib.redirect_stdout(output),
                contextlib.redirect_stderr(progress),
            ):
                code = main(
                    [
                        "server",
                        "benchmark",
                        "--data-dir",
                        root,
                        "--input-tokens",
                        "64",
                        "--output-tokens",
                        "8",
                        "--repeats",
                        "1",
                    ]
                )
            self.assertEqual(code, 0)
            value = json.loads(output.getvalue())
            self.assertTrue(value["completed"])
            self.assertEqual(value["endpoint"], "http://127.0.0.1:%s/v1" % port)
            self.assertIn("BENCHMARK COMPLETE", progress.getvalue())
            saved = next(directory.glob("benchmark-*.json"))
            self.assertEqual(saved.stat().st_mode & 0o777, 0o600)
            self.assertEqual(json.loads(saved.read_text()), value)
