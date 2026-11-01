import argparse
import contextlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_ai import images, installlog
from local_ai.cli import main
from local_ai.common import run
from local_ai.profiles import profile


class ImageErrorTests(unittest.TestCase):
    def test_missing_image_downloads_and_verifies(self):
        policy = profile("b300-tp4")
        missing = subprocess.CompletedProcess(
            [], 1, "[]", "Error response from daemon: No such image: " + policy["image"] + "\n"
        )
        image = {"Id": "sha256:test", "Architecture": "amd64", "Os": "linux"}
        found = subprocess.CompletedProcess([], 0, json.dumps([image]), "")
        with tempfile.TemporaryDirectory() as root:
            with (
                patch("local_ai.images.run", side_effect=[missing, found]),
                patch(
                    "local_ai.images.download_command",
                    return_value=subprocess.CompletedProcess([], 0),
                ) as download,
            ):
                self.assertEqual(images.pull(root, policy)["status"], "downloaded")
            download.assert_called_once()

    def test_inspect_failures_do_not_trigger_download(self):
        for error in [
            "Cannot connect to the Docker daemon",
            "permission denied",
            "metadata.db: no such file or directory",
            "",
        ]:
            with self.subTest(error=error), tempfile.TemporaryDirectory() as root:
                with (
                    patch(
                        "local_ai.images.run",
                        return_value=subprocess.CompletedProcess([], 1, "", error),
                    ),
                    patch("local_ai.images.download_command") as download,
                ):
                    with self.assertRaisesRegex(RuntimeError, "Docker image inspection failed"):
                        images.pull(root, profile("b300-tp4"))
                    download.assert_not_called()

    def test_cli_pull_failure_displays_error_and_keeps_stdout_empty(self):
        error = "failed to open database file: metadata.db: no such file or directory"
        with tempfile.TemporaryDirectory() as root:
            output, console = io.StringIO(), io.StringIO()
            with (
                patch("local_ai.images.inspect_image", return_value=None),
                patch(
                    "local_ai.images.download_command",
                    return_value=subprocess.CompletedProcess([], 1, "", error),
                ),
                contextlib.redirect_stdout(output),
                contextlib.redirect_stderr(console),
            ):
                code = main(["image", "pull", "--profile", "b300-tp4", "--data-dir", root])
            self.assertNotEqual(code, 0)
            self.assertEqual(output.getvalue(), "")
            self.assertIn(error, console.getvalue())
            self.assertIn(error, (Path(root) / "install.log").read_text())

    def test_failed_command_shows_error_end_and_preserves_full_log(self):
        error = "x" * 400 + " metadata.db: no such file or directory"
        with tempfile.TemporaryDirectory() as root:
            options = argparse.Namespace(
                group="image", action="pull", data_dir=Path(root), install_log=None
            )
            console = io.StringIO()
            with contextlib.redirect_stderr(console), installlog.session(options):
                result = run(
                    [
                        sys.executable,
                        "-c",
                        "import sys; print(%r,file=sys.stderr); sys.exit(7)" % error,
                    ],
                    check=False,
                )
            self.assertEqual(result.returncode, 7)
            self.assertIn("metadata.db: no such file or directory", console.getvalue())
            self.assertIn(error, (Path(root) / "install.log").read_text())
