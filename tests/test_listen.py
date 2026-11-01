import contextlib
import io
import json
import socket
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_policy import hardware

from local_ai import server
from local_ai.cli import main, parser
from local_ai.common import fingerprint
from local_ai.profiles import engine_args, profile


class ListenTests(unittest.TestCase):
    def value(self, root, host="127.0.0.1"):
        return server.plan(root, profile("b300-tp4"), "0,1,2,3", "a", 18000, hardware(), host)

    def test_default_preserves_legacy_spec_shape_and_arguments(self):
        value = self.value("/tmp/local-ai-listen")
        self.assertNotIn("host", value["spec"])
        self.assertEqual(value["spec"]["args"], engine_args(profile("b300-tp4"), 18000))
        args = value["spec"]["args"]
        self.assertEqual(args[args.index("--host") + 1], "127.0.0.1")

    def test_cli_custom_host_plan_has_no_side_effects(self):
        fixture = Path(__file__).parent / "fixtures/b300-tp4.json"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "absent"
            output = io.StringIO()
            with (
                patch("local_ai.server.inventory", side_effect=AssertionError("no hardware")),
                patch("local_ai.server.socket.socket", side_effect=AssertionError("no sockets")),
                patch("local_ai.common.subprocess.run", side_effect=AssertionError("no commands")),
                contextlib.redirect_stdout(output),
            ):
                code = main(
                    [
                        "server",
                        "plan",
                        "--gpus",
                        "0,1,2,3",
                        "--host",
                        "0.0.0.0",
                        "--inventory",
                        str(fixture),
                        "--data-dir",
                        str(root),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertFalse(root.exists())
            value = json.loads(output.getvalue())
            self.assertEqual(value["spec"]["host"], "0.0.0.0")
            args = value["spec"]["args"]
            self.assertEqual(args[args.index("--host") + 1], "0.0.0.0")

    def test_invalid_listen_addresses_rejected(self):
        for host in [
            "localhost",
            "::1",
            "1.2.3.999",
            "http://host",
            "224.0.0.1",
            "255.255.255.255",
            "--help",
            "",
        ]:
            with self.subTest(host=host), self.assertRaisesRegex(ValueError, "Host must"):
                self.value("/tmp/local-ai-listen", host)

    def test_wildcard_check_detects_other_interface_port_conflict(self):
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.2", 0))
            occupied.listen()
            port = occupied.getsockname()[1]
            server.check_port("127.0.0.1", port)
            with self.assertRaisesRegex(RuntimeError, "Cannot bind model API at 0.0.0.0"):
                server.check_port("0.0.0.0", port)

    def test_stopped_http_listener_time_wait_does_not_block_restart(self):
        with socket.socket() as listener:
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind(("127.0.0.1", 0))
            listener.listen()
            port = listener.getsockname()[1]
            with self.assertRaisesRegex(RuntimeError, "Cannot bind"):
                server.check_port("127.0.0.1", port)
            with socket.create_connection(("127.0.0.1", port), timeout=2) as client:
                accepted, _ = listener.accept()
                with accepted:
                    accepted.shutdown(socket.SHUT_WR)
                    self.assertEqual(client.recv(1), b"")
        server.check_port("127.0.0.1", port)

    def test_start_parser_accepts_specific_ipv4(self):
        args = parser().parse_args(["server", "start", "--gpus", "0,1,2,3", "--host", "192.0.2.10"])
        self.assertEqual(args.host, "192.0.2.10")

    def start_with_mocks(self, value, old=None, check=None):
        def command(args, **kwargs):
            output = "\n".join("nvidia.com/gpu=" + g for g in value["spec"]["gpus"])
            return subprocess.CompletedProcess(
                args, 0, output if args[0] == "nvidia-ctk" else "", ""
            )

        with (
            patch("local_ai.server.validate_model"),
            patch("local_ai.server.check_host_memory"),
            patch("local_ai.server.resolve_image", return_value=value["spec"]["image"]),
            patch("local_ai.server.inspect_container", return_value=old),
            patch("local_ai.server.run", side_effect=command),
            patch("local_ai.server.check_port", side_effect=check) as probe,
        ):
            result = server.start(value, profile("b300-tp4"))
        return result, probe

    def test_start_checks_selected_host_and_returns_reachable_health_url(self):
        for host, health in [
            ("127.0.0.1", "127.0.0.1"),
            ("0.0.0.0", "127.0.0.1"),
            ("192.0.2.10", "192.0.2.10"),
        ]:
            with self.subTest(host=host), tempfile.TemporaryDirectory() as root:
                value = self.value(root, host)
                result, probe = self.start_with_mocks(value)
                probe.assert_called_once_with(host, 18000)
                self.assertEqual(result["health"], "http://%s:18000/health" % health)
                saved = json.loads((Path(root) / "instances/a/args.json").read_text())
                self.assertEqual(saved[saved.index("--host") + 1], host)

    def test_host_change_rejects_existing_container_before_launch(self):
        with tempfile.TemporaryDirectory() as root:
            old = self.value(root)
            current = self.value(root, "0.0.0.0")
            labels = {
                "local-ai.project": "cluster-local-ai",
                "local-ai.spec": fingerprint(old["spec"]),
            }
            container = {"Config": {"Labels": labels}, "State": {"Running": True}}
            with self.assertRaisesRegex(RuntimeError, "Existing container differs"):
                self.start_with_mocks(current, old=container)
            self.assertFalse((Path(root) / "instances").exists())

    def test_port_conflict_prevents_instance_files_or_launch(self):
        with tempfile.TemporaryDirectory() as root:
            value = self.value(root, "0.0.0.0")
            with self.assertRaisesRegex(RuntimeError, "occupied"):
                self.start_with_mocks(value, check=RuntimeError("occupied"))
            self.assertFalse((Path(root) / "instances").exists())
