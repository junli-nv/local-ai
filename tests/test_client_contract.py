import json
import subprocess
import unittest
from pathlib import Path
from unittest.mock import patch

from local_ai.resume import native_sessions


class ClientContractTests(unittest.TestCase):
    def test_public_session_metadata_and_private_data_location(self):
        sessions = [{"id": "ses_example", "directory": "/tmp/project", "future_field": True}]
        result = subprocess.CompletedProcess([], 0, json.dumps(sessions), "")
        with (
            patch("local_ai.resume.validate"),
            patch("local_ai.resume.subprocess.run", return_value=result) as run,
        ):
            self.assertEqual(
                native_sessions(
                    Path("/tmp/private"),
                    {
                        "client_dir": "/assets",
                        "endpoint": "http://gpu:18000/v1",
                        "model": "example",
                        "project": "/tmp",
                    },
                ),
                sessions,
            )
        self.assertEqual(run.call_args.args[0][-4:], ["session", "list", "--format", "json"])
        self.assertEqual(run.call_args.kwargs["env"]["XDG_DATA_HOME"], "/tmp/private/data")

    def test_cli_or_metadata_changes_report_the_failing_capability(self):
        for code, output in [(1, ""), (0, "{}"), (0, '[{"id":"s"}]'), (0, "not json")]:
            with self.subTest(code=code, output=output):
                result = subprocess.CompletedProcess([], code, output, "unsupported format")
                with (
                    patch("local_ai.resume.validate"),
                    patch("local_ai.resume.subprocess.run", return_value=result),
                    self.assertRaisesRegex((ValueError, RuntimeError), "session list"),
                ):
                    native_sessions(
                        Path("/tmp/private"),
                        {
                            "client_dir": "/assets",
                            "endpoint": "http://gpu:18000/v1",
                            "model": "example",
                            "project": "/tmp",
                        },
                    )
