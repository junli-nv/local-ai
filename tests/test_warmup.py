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

from test_policy import hardware

from local_ai import server, warmup
from local_ai.cli import main
from local_ai.common import fingerprint
from local_ai.profiles import engine_args, profile


@contextlib.contextmanager
def inference_api(fail_at=None, delay=0):
    calls = []
    active = {"count": 0, "peak": 0}
    lock = threading.Lock()
    entered, release = threading.Event(), threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, value):
            body = json.dumps(value).encode()
            try:
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (OSError, BrokenPipeError):
                pass

        def do_GET(self):
            self.send(200, {})

        def do_POST(self):
            data = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            if self.path == "/tokenize":
                self.send(200, {"tokens": [ord(c) for c in data["prompt"]]})
                return
            with lock:
                calls.append(data)
                index = len(calls)
                active["count"] += 1
                active["peak"] = max(active["peak"], active["count"])
            entered.set()
            try:
                if delay == "block":
                    release.wait(3)
                elif delay:
                    time.sleep(delay)
                if fail_at == index:
                    self.send(500, {"error": "synthetic failure"})
                else:
                    self.send(
                        200,
                        {
                            "choices": [{"text": "synthetic"}],
                            "usage": {
                                "prompt_tokens": len(data["prompt"]),
                                "completion_tokens": data["max_tokens"],
                            },
                        },
                    )
            finally:
                with lock:
                    active["count"] -= 1

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as http:
        worker = threading.Thread(
            target=lambda: http.serve_forever(poll_interval=0.01), daemon=True
        )
        worker.start()
        try:
            yield http.server_port, calls, entered, release
        finally:
            release.set()
            http.shutdown()
            worker.join(timeout=2)


class WarmupTests(unittest.TestCase):
    def fixture(self, root, port=18000):
        spec = {
            "data_dir": str(root),
            "instance": "a",
            "container": "local-ai-a",
            "port": port,
            "host": "0.0.0.0",
            "args": [
                "serve",
                "/models/example",
                "--served-model-name",
                "example",
                "--max-model-len",
                "4096",
                "--max-num-seqs",
                "2",
            ],
        }
        directory = Path(root) / "instances/a"
        directory.mkdir(parents=True)
        (directory / "spec.json").write_text(json.dumps(spec))
        (directory / "args.json").write_text(json.dumps(spec["args"]))
        container = {
            "Name": "/local-ai-a",
            "State": {"Running": True, "StartedAt": "first-start", "ExitCode": 0},
            "Config": {
                "Labels": {
                    "local-ai.project": "cluster-local-ai",
                    "local-ai.data-dir": str(root),
                    "local-ai.port": str(port),
                    "local-ai.spec": fingerprint(spec),
                }
            },
        }
        return spec, container, directory

    def test_exact_shapes_success_logs_and_unique_prefixes(self):
        with tempfile.TemporaryDirectory() as root, inference_api() as (port, calls, _, _):
            spec, container, directory = self.fixture(root, port)
            value = warmup.run(
                spec,
                Mock(return_value=container),
                timeout=10,
                inputs="64,128",
                concurrency="1,3",
                output_tokens=8,
                repeats=2,
            )
            self.assertTrue(value["completed"])
            self.assertEqual(value["completed_requests"], 16)
            self.assertEqual(len(calls), 16)
            self.assertEqual({len(c["prompt"]) for c in calls}, {64, 128})
            self.assertEqual(len({tuple(c["prompt"]) for c in calls}), 16)
            self.assertTrue(all(c["ignore_eos"] and c["max_tokens"] == 8 for c in calls))
            self.assertIn("WARMUP COMPLETE", (directory / "server.log").read_text())
            self.assertTrue(warmup.progress(spec, container)["completed"])

    def test_api_failure_records_partial_progress_and_never_completed(self):
        with tempfile.TemporaryDirectory() as root, inference_api(fail_at=2) as (port, _, _, _):
            spec, container, directory = self.fixture(root, port)
            with self.assertRaisesRegex(RuntimeError, "HTTP 500"):
                warmup.run(
                    spec,
                    Mock(return_value=container),
                    inputs="64",
                    concurrency="1",
                    output_tokens=8,
                    repeats=2,
                )
            value = json.loads((directory / "warmup.json").read_text())
            self.assertEqual(value["state"], "failed")
            self.assertEqual(value["completed_requests"], 1)
            self.assertFalse(value["completed"])
            self.assertTrue(container["State"]["Running"])

    def test_timeout_is_bounded_and_leaves_container_running(self):
        with tempfile.TemporaryDirectory() as root, inference_api(delay=1) as (port, _, _, _):
            spec, container, directory = self.fixture(root, port)
            with self.assertRaisesRegex(RuntimeError, "Warmup failed"):
                warmup.run(
                    spec,
                    Mock(return_value=container),
                    timeout=0.2,
                    inputs="64",
                    concurrency="1",
                    output_tokens=8,
                    repeats=1,
                )
            value = json.loads((directory / "warmup.json").read_text())
            self.assertEqual(value["state"], "failed")
            self.assertTrue(container["State"]["Running"])

    def test_abort_unblocks_inflight_http_connection(self):
        with inference_api(delay="block") as (port, _, entered, release):
            transport = warmup.Transport({"host": "0.0.0.0", "port": port}, time.monotonic() + 10)
            errors = []

            def call():
                try:
                    transport.post("/v1/completions", {"prompt": [1], "max_tokens": 8})
                except Exception as error:
                    errors.append(error)

            worker = threading.Thread(target=call)
            worker.start()
            try:
                self.assertTrue(entered.wait(2))
                transport.abort()
                worker.join(timeout=2)
                self.assertFalse(worker.is_alive())
                self.assertTrue(errors)
            finally:
                release.set()
                worker.join(timeout=2)

    def test_interruption_records_cancelled_without_stopping_instance(self):
        with tempfile.TemporaryDirectory() as root:
            spec, container, directory = self.fixture(root)
            with (
                patch("local_ai.warmup.readiness.probe", return_value={"ready": True}),
                patch("local_ai.warmup.Transport.post", side_effect=KeyboardInterrupt),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    warmup.run(
                        spec,
                        Mock(return_value=container),
                        inputs="64",
                        concurrency="1",
                        output_tokens=8,
                        repeats=1,
                    )
            self.assertEqual(
                json.loads((directory / "warmup.json").read_text())["state"], "cancelled"
            )
            self.assertTrue(container["State"]["Running"])

    def test_stale_or_corrupt_progress_cannot_claim_current_warmup(self):
        with tempfile.TemporaryDirectory() as root:
            spec, container, directory = self.fixture(root)
            path = directory / "warmup.json"
            path.write_text(
                json.dumps(
                    {
                        "state": "completed",
                        "container_started_at": "old",
                        "spec_fingerprint": fingerprint(spec),
                    }
                )
            )
            self.assertEqual(warmup.progress(spec, container)["state"], "stale")
            path.write_text("[]")
            self.assertEqual(warmup.progress(spec, container)["state"], "invalid")
            self.assertFalse(warmup.progress(spec, container)["completed"])

    def test_status_reads_progress_without_inference_or_file_mutation(self):
        with tempfile.TemporaryDirectory() as root, inference_api() as (port, calls, _, _):
            spec, container, directory = self.fixture(root, port)
            marker = {
                "state": "completed",
                "container_started_at": "first-start",
                "spec_fingerprint": fingerprint(spec),
            }
            (directory / "warmup.json").write_text(json.dumps(marker))
            before = {p.name: p.read_bytes() for p in directory.iterdir()}
            with patch("local_ai.server.inspect_container", return_value=container):
                value = server.status("a")
            self.assertTrue(value["ready"])
            self.assertTrue(value["warmup"]["completed"])
            self.assertEqual(calls, [])
            self.assertEqual(before, {p.name: p.read_bytes() for p in directory.iterdir()})

    def test_concurrent_warmup_is_rejected_before_network(self):
        with tempfile.TemporaryDirectory() as root:
            spec, _, directory = self.fixture(root)
            with (directory / ".warmup.lock").open("a") as lock:
                fcntl.flock(lock, fcntl.LOCK_EX)
                with patch("local_ai.warmup.Transport.post", side_effect=AssertionError):
                    with self.assertRaisesRegex(RuntimeError, "already running"):
                        warmup.run(spec, Mock(), inputs="64", concurrency="1", output_tokens=8)

    def test_bounds_and_invalid_lists_fail_before_network(self):
        with tempfile.TemporaryDirectory() as root:
            spec, _, directory = self.fixture(root)
            for values in (
                {"inputs": "0"},
                {"concurrency": "1,x"},
                {"inputs": "4096"},
                {"output_tokens": 4096},
                {"repeats": 0},
            ):
                with self.assertRaises(ValueError):
                    warmup.run(spec, Mock(), **values)
            self.assertFalse((directory / "warmup.json").exists())
            self.assertEqual(warmup.suite(spec)["input_tokens"], [1024])
            self.assertEqual(warmup.suite(spec)["concurrency"], [1, 2, 4])

    def test_managed_spec_rejects_wrong_deployment_metadata_and_args(self):
        with tempfile.TemporaryDirectory() as root:
            spec, container, directory = self.fixture(root)
            with patch("local_ai.server.inspect_container", return_value=container):
                self.assertEqual(server.managed_spec(root, "a"), spec)
                with self.assertRaisesRegex(ValueError, "another deployment"):
                    server.managed_spec(Path(root) / "other", "a")
                (directory / "args.json").write_text("[]")
                with self.assertRaisesRegex(ValueError, "drift"):
                    server.managed_spec(root, "a")

    def test_profile_is_opt_in_and_uses_persistent_compiler_cache(self):
        base, fast = profile("b300-tp4"), profile("b300-tp4-dspark")
        normal = engine_args(base, 18000)
        args = engine_args(fast, 18000)
        self.assertNotIn("--speculative-config", normal)
        self.assertEqual(
            json.loads(normal[normal.index("--compilation-config") + 1])["cudagraph_capture_sizes"],
            [1, 2, 4],
        )
        speculative = json.loads(args[args.index("--speculative-config") + 1])
        self.assertEqual(speculative["method"], "dspark")
        self.assertNotEqual(speculative["rejection_sample_method"], "synthetic")
        self.assertEqual(fast["environment"]["TILELANG_CACHE_DIR"], "/root/.cache/tilelang")
        self.assertEqual(base["environment"], {"VLLM_USE_RUST_FRONTEND": "1"})

    def test_start_only_generates_warmup_when_explicitly_requested(self):
        for extra in ([], ["--warmup", "--warmup-timeout", "7"]):
            with tempfile.TemporaryDirectory() as root:
                output = io.StringIO()
                with (
                    patch("local_ai.cli.server.inventory", return_value=hardware()),
                    patch("local_ai.cli.server.start", return_value={"state": "started"}),
                    patch(
                        "local_ai.cli.readiness.wait",
                        return_value={"ready": True, "state": "ready"},
                    ),
                    patch("local_ai.cli.warmup.run", return_value={"state": "completed"}) as run,
                    contextlib.redirect_stdout(output),
                    contextlib.redirect_stderr(io.StringIO()),
                ):
                    code = main(
                        ["server", "start", "--gpus", "0,1,2,3", "--data-dir", root, *extra]
                    )
                self.assertEqual(code, 0)
                self.assertEqual(run.call_count, bool(extra))
                if extra:
                    self.assertEqual(run.call_args.kwargs["timeout"], 7)
                    self.assertEqual(json.loads(output.getvalue())["warmup"]["state"], "completed")

    def test_restart_during_warmup_prevents_complete_marker(self):
        with tempfile.TemporaryDirectory() as root, inference_api() as (port, _, _, _):
            spec, container, directory = self.fixture(root, port)
            restarted = json.loads(json.dumps(container))
            restarted["State"]["StartedAt"] = "second-start"
            inspect = Mock(side_effect=[container, container, restarted])
            with self.assertRaisesRegex(RuntimeError, "restarted during warmup"):
                warmup.run(
                    spec,
                    inspect,
                    inputs="64",
                    concurrency="1",
                    output_tokens=8,
                    repeats=1,
                )
            value = json.loads((directory / "warmup.json").read_text())
            self.assertEqual(value["state"], "failed")
            self.assertFalse(value["completed"])
            self.assertNotIn("WARMUP COMPLETE", (directory / "server.log").read_text())

    def test_standalone_cli_passes_explicit_suite_and_reports_json(self):
        with tempfile.TemporaryDirectory() as root:
            spec, container, _ = self.fixture(root)
            output = io.StringIO()
            with (
                patch("local_ai.cli.server.managed_spec", return_value=spec) as managed,
                patch(
                    "local_ai.cli.warmup.run",
                    return_value={
                        "state": "completed",
                        "completed": True,
                    },
                ) as run,
                contextlib.redirect_stdout(output),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                code = main(
                    [
                        "server",
                        "warmup",
                        "--name",
                        "a",
                        "--data-dir",
                        root,
                        "--input-tokens",
                        "64,128",
                        "--concurrency",
                        "1,3",
                        "--output-tokens",
                        "8",
                        "--repeats",
                        "1",
                        "--timeout",
                        "7",
                    ]
                )
            self.assertEqual(code, 0)
            managed.assert_called_once()
            self.assertEqual(
                run.call_args.kwargs,
                {
                    "timeout": 7,
                    "inputs": "64,128",
                    "concurrency": "1,3",
                    "output_tokens": 8,
                    "repeats": 1,
                },
            )
            self.assertTrue(json.loads(output.getvalue())["warmup"]["completed"])
