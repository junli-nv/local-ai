import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_ai.artifacts import install


class ClientVersionTests(unittest.TestCase):
    def binary(self, root):
        path = root / "local-opencode"
        value = bytearray(20)
        value[:4] = b"\x7fELF"
        value[4] = 2
        value[5] = 1
        value[18:20] = (62).to_bytes(2, "little")
        path.write_bytes(value)
        return path

    def test_import_detects_version_and_repeat_install_never_downgrades(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = subprocess.CompletedProcess([], 0, "9.8.7\n", "")
            with (
                patch("local_ai.artifacts.arch", return_value="amd64"),
                patch("local_ai.artifacts.run", return_value=result) as run,
                patch("local_ai.artifacts.fetch") as fetch,
            ):
                value = install(root / "assets", binary=self.binary(root))
                self.assertEqual(value["manifest"]["version"], "9.8.7")
                run.reset_mock()
                again = install(root / "assets")
                self.assertEqual(again["manifest"]["version"], "9.8.7")
                self.assertEqual(again["status"], "already-present")
                run.assert_not_called()
                fetch.assert_not_called()

    def test_explicit_import_version_must_match_actual_binary(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = subprocess.CompletedProcess([], 0, "9.8.7\n", "")
            with (
                patch("local_ai.artifacts.arch", return_value="amd64"),
                patch("local_ai.artifacts.run", return_value=result),
                self.assertRaisesRegex(ValueError, "differs from requested"),
            ):
                install(root / "assets", binary=self.binary(root), version="9.8.6")
