import contextlib
import io
import json
import shlex
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_policy import hardware

from local_ai.cli import main


class StartGuidanceTests(unittest.TestCase):
    def invoke(self, root, host, result=None, failure=None):
        output, progress = io.StringIO(), io.StringIO()
        with (
            patch("local_ai.cli.server.inventory", return_value=hardware()),
            patch("local_ai.cli.server.start", return_value=result, side_effect=failure),
            patch("local_ai.cli.readiness.wait", return_value={"state": "ready", "ready": True}),
            contextlib.redirect_stdout(output),
            contextlib.redirect_stderr(progress),
        ):
            code = main(
                [
                    "server",
                    "start",
                    "--gpus",
                    "0,1,2,3",
                    "--host",
                    host,
                    "--name",
                    "a",
                    "--data-dir",
                    str(root),
                ]
            )
        return code, output.getvalue(), progress.getvalue()

    def test_new_start_shows_follow_command_and_preserves_json(self):
        result = {"state": "started-not-yet-ready", "container": "local-ai-a"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "data space"
            code, output, progress = self.invoke(root, "0.0.0.0", result)
            log = str(root / "instances/a/server.log")
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output)["state"], "ready")
            self.assertTrue(json.loads(output)["ready"])
            self.assertIn("正在等待 API 就绪", progress)
            self.assertIn("Runtime log: " + log, progress)
            self.assertIn("Follow startup: " + shlex.join(["tail", "-f", log]), progress)
            self.assertIn("server status --name a", progress)
            self.assertIn("Runtime log: " + log, (root / "install.log").read_text())

    def test_existing_container_also_gets_guidance_for_selected_host(self):
        result = {"state": "already-running", "container": "local-ai-a"}
        with tempfile.TemporaryDirectory() as root:
            code, output, progress = self.invoke(root, "192.0.2.10", result)
            self.assertEqual(code, 0)
            self.assertEqual(json.loads(output)["state"], "ready")
            self.assertTrue(json.loads(output)["ready"])
            self.assertIn("Follow startup:", progress)
            self.assertIn("server status --name a", progress)

    def test_failed_launch_does_not_print_success_guidance(self):
        with tempfile.TemporaryDirectory() as root:
            code, output, progress = self.invoke(
                root, "0.0.0.0", failure=RuntimeError("launch failed")
            )
            self.assertEqual(code, 1)
            self.assertEqual(output, "")
            self.assertIn("launch failed", progress)
            self.assertNotIn("Container is running", progress)
            self.assertNotIn("Follow startup:", progress)
