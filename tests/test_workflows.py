import argparse
import json
import math
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from local_ai.workflows import run


def options(path, **values):
    return argparse.Namespace(
        **{
            "case": "diagnose",
            "timeout": 1,
            "output": path,
            "endpoint": "http://unused/v1",
            "model": "m",
            "client_dir": Path("/unused"),
            **values,
        }
    )


class WorkflowTests(unittest.TestCase):
    def test_existing_output_is_never_overwritten_or_executed(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            marker = root / "keep"
            marker.write_text("original")
            with patch(
                "local_ai.workflows.subprocess.run", side_effect=AssertionError("no execution")
            ):
                with self.assertRaises(FileExistsError):
                    run(options(root))
            self.assertEqual(marker.read_text(), "original")

    def test_invalid_deadline_creates_no_output_or_subprocess(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "output"
            for value in (0, -1, math.nan, math.inf, 3601):
                with self.assertRaises(ValueError):
                    run(options(target, timeout=value))
            self.assertFalse(target.exists())

    def test_failure_retains_result_without_claiming_success(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "output"
            with patch(
                "local_ai.workflows.subprocess.run", return_value=SimpleNamespace(returncode=1)
            ):
                result = run(options(target))
            self.assertEqual(result["state"], "failed")
            self.assertEqual(result["turns"][0]["exit_code"], 1)
            self.assertEqual(json.loads((target / "result.json").read_text())["state"], "failed")
            self.assertEqual(target.stat().st_mode & 0o777, 0o700)

    def test_unknown_case_rejected_before_files(self):
        with tempfile.TemporaryDirectory() as root:
            target = Path(root) / "output"
            with self.assertRaises(ValueError):
                run(options(target, case="unknown"))
            self.assertFalse(target.exists())
