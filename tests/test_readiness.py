import contextlib
import io
import json
import socket
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import Mock, patch

from local_ai import readiness, server
from local_ai.cli import main


@contextlib.contextmanager
def health_api(statuses=(200,)):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(statuses[min(len(requests) - 1, len(statuses) - 1)])
            self.end_headers()

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as http:
        worker = threading.Thread(
            target=lambda: http.serve_forever(poll_interval=0.01), daemon=True
        )
        worker.start()
        try:
            yield http.server_port, requests
        finally:
            http.shutdown()
            worker.join(timeout=2)


class Clock:
    def __init__(self):
        self.now = 0

    def monotonic(self):
        return self.now

    def sleep(self, seconds):
        self.now += seconds


class ReadinessTests(unittest.TestCase):
    def spec(self, root, port=18000):
        return {
            "data_dir": str(root),
            "instance": "a",
            "container": "local-ai-a",
            "host": "0.0.0.0",
            "port": port,
        }

    def container(self, spec, running=True):
        return {
            "Name": "/local-ai-a",
            "State": {"Running": running, "ExitCode": 0},
            "Config": {
                "Labels": {
                    "local-ai.project": "cluster-local-ai",
                    "local-ai.data-dir": spec["data_dir"],
                    "local-ai.port": str(spec["port"]),
                }
            },
        }

    def instance(self, root, port=18000):
        spec = self.spec(root, port)
        directory = Path(root) / "instances/a"
        directory.mkdir(parents=True)
        (directory / "spec.json").write_text(json.dumps(spec))
        return spec, directory

    def test_empty_http_200_is_ready(self):
        with health_api() as (port, requests):
            value = readiness.probe(self.spec("/unused", port))
        self.assertTrue(value["listening"])
        self.assertTrue(value["ready"])
        self.assertIn("服务已就绪", readiness.message(value))
        self.assertEqual(requests, ["/health"])

    def test_open_port_with_503_is_not_ready(self):
        with health_api((503,)) as (port, _):
            value = readiness.probe(self.spec("/unused", port))
        self.assertTrue(value["listening"])
        self.assertFalse(value["ready"])
        self.assertIn("503", value["detail"])
        self.assertIn("服务尚未就绪", readiness.message(value))

    def test_closed_port_is_not_ready(self):
        with socket.socket() as reserved:
            reserved.bind(("127.0.0.1", 0))
            value = readiness.probe(self.spec("/unused", reserved.getsockname()[1]))
        self.assertFalse(value["ready"])
        self.assertFalse(value["listening"])

    def test_wait_records_explicit_ready_marker(self):
        with tempfile.TemporaryDirectory() as root, health_api() as (port, _):
            spec, directory = self.instance(root, port)
            inspect = Mock(return_value=self.container(spec))
            value = readiness.wait(spec, inspect, timeout=1)
            text = (directory / "server.log").read_text()
        self.assertTrue(value["ready"])
        self.assertEqual(value["state"], "ready")
        self.assertIn("[local-ai] 服务已就绪（READY）", text)

    def test_wait_retries_pending_api_then_records_ready(self):
        clock = Clock()
        with tempfile.TemporaryDirectory() as root, health_api((503, 200)) as (port, requests):
            spec, directory = self.instance(root, port)
            with (
                patch("local_ai.readiness.time.monotonic", side_effect=clock.monotonic),
                patch("local_ai.readiness.time.sleep", side_effect=clock.sleep),
            ):
                value = readiness.wait(spec, Mock(return_value=self.container(spec)), timeout=5)
            self.assertTrue(value["ready"])
            self.assertEqual(requests, ["/health", "/health"])
            self.assertIn("服务已就绪", (directory / "server.log").read_text())

    def test_timeout_records_not_ready_and_does_not_stop_container(self):
        clock = Clock()
        with tempfile.TemporaryDirectory() as root:
            spec, directory = self.instance(root)
            inspect = Mock(return_value=self.container(spec))
            with (
                patch("local_ai.readiness.time.monotonic", side_effect=clock.monotonic),
                patch("local_ai.readiness.time.sleep", side_effect=clock.sleep),
                patch(
                    "local_ai.readiness.probe", return_value={"ready": False, "detail": "pending"}
                ),
            ):
                with self.assertRaisesRegex(RuntimeError, "NOT READY.*超时"):
                    readiness.wait(spec, inspect, timeout=1)
            text = (directory / "server.log").read_text()
            self.assertIn("容器未停止", text)
            self.assertNotIn("服务已就绪", text)
            self.assertTrue(all(call.args == ("local-ai-a",) for call in inspect.call_args_list))

    def test_exited_container_fails_without_probing_api(self):
        with tempfile.TemporaryDirectory() as root:
            spec, directory = self.instance(root)
            container = self.container(spec, running=False)
            container["State"].update(ExitCode=1, OOMKilled=True)
            with patch("local_ai.readiness.probe", side_effect=AssertionError("do not probe")):
                with self.assertRaisesRegex(RuntimeError, "FAILED"):
                    readiness.wait(spec, Mock(return_value=container), timeout=1)
            text = (directory / "server.log").read_text()
            self.assertIn("OOMKilled=True", text)
            self.assertNotIn("服务已就绪", text)

    def test_status_ready_is_read_only_and_cli_says_ready(self):
        with tempfile.TemporaryDirectory() as root, health_api() as (port, _):
            spec, directory = self.instance(root, port)
            original = (directory / "spec.json").read_bytes()
            output, progress = io.StringIO(), io.StringIO()
            with (
                patch("local_ai.server.inspect_container", return_value=self.container(spec)),
                contextlib.redirect_stdout(output),
                contextlib.redirect_stderr(progress),
            ):
                code = main(["server", "status", "--name", "a"])
            self.assertEqual(code, 0)
            self.assertTrue(json.loads(output.getvalue())["ready"])
            self.assertIn("服务已就绪", progress.getvalue())
            self.assertFalse((directory / "server.log").exists())
            self.assertFalse((Path(root) / "install.log").exists())
            self.assertEqual((directory / "spec.json").read_bytes(), original)

    def test_status_http_503_returns_not_ready_and_exit_one(self):
        with tempfile.TemporaryDirectory() as root, health_api((503,)) as (port, _):
            spec, _ = self.instance(root, port)
            output, progress = io.StringIO(), io.StringIO()
            with (
                patch("local_ai.server.inspect_container", return_value=self.container(spec)),
                contextlib.redirect_stdout(output),
                contextlib.redirect_stderr(progress),
            ):
                code = main(["server", "status", "--name", "a"])
            self.assertEqual(code, 1)
            value = json.loads(output.getvalue())
            self.assertTrue(value["listening"])
            self.assertFalse(value["ready"])
            self.assertIn("服务尚未就绪", progress.getvalue())

    def test_stopped_container_cannot_be_ready_even_if_port_is_healthy(self):
        with tempfile.TemporaryDirectory() as root, health_api() as (port, requests):
            spec, _ = self.instance(root, port)
            with patch(
                "local_ai.server.inspect_container", return_value=self.container(spec, False)
            ):
                value = server.status("a")
            self.assertFalse(value["ready"])
            self.assertEqual(requests, [])

    def test_container_exit_after_api_response_is_not_reported_ready(self):
        with tempfile.TemporaryDirectory() as root, health_api() as (port, _):
            spec, directory = self.instance(root, port)
            inspect = Mock(side_effect=[self.container(spec), self.container(spec, False)])
            with self.assertRaisesRegex(RuntimeError, "FAILED"):
                readiness.wait(spec, inspect, timeout=1)
            self.assertNotIn("服务已就绪", (directory / "server.log").read_text())

    def test_interrupted_wait_leaves_explicit_log(self):
        with tempfile.TemporaryDirectory() as root:
            spec, directory = self.instance(root)
            with (
                patch(
                    "local_ai.readiness.probe", return_value={"ready": False, "detail": "pending"}
                ),
                patch("local_ai.readiness.time.sleep", side_effect=KeyboardInterrupt),
            ):
                with self.assertRaises(KeyboardInterrupt):
                    readiness.wait(spec, Mock(return_value=self.container(spec)), timeout=1)
            text = (directory / "server.log").read_text()
            self.assertIn("WAIT CANCELLED", text)
            self.assertIn("容器未停止", text)

    def test_invalid_wait_timeout_never_launches_container(self):
        with tempfile.TemporaryDirectory() as root:
            with (
                patch("local_ai.cli.server.inventory") as inventory,
                patch("local_ai.cli.server.start") as start,
                contextlib.redirect_stdout(io.StringIO()),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                code = main(
                    [
                        "server",
                        "start",
                        "--gpus",
                        "0,1,2,3",
                        "--data-dir",
                        root,
                        "--wait-timeout",
                        "0",
                    ]
                )
            self.assertEqual(code, 1)
            inventory.assert_not_called()
            start.assert_not_called()

    def test_status_missing_configuration_is_not_ready_without_writes(self):
        with tempfile.TemporaryDirectory() as root:
            spec = self.spec(root)
            with patch("local_ai.server.inspect_container", return_value=self.container(spec)):
                value = server.status("a")
            self.assertFalse(value["ready"])
            self.assertEqual(list(Path(root).iterdir()), [])

    def test_status_malformed_spec_is_not_ready(self):
        with tempfile.TemporaryDirectory() as root:
            spec, directory = self.instance(root)
            (directory / "spec.json").write_text("[]")
            with patch("local_ai.server.inspect_container", return_value=self.container(spec)):
                value = server.status("a")
            self.assertFalse(value["ready"])
            self.assertIn("invalid instance configuration", value["detail"])
            self.assertFalse((directory / "server.log").exists())
