"""Exercise the real JS plugin and Python RPC without a model or Linux workers."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from local_ai import execution as e


@unittest.skipUnless(shutil.which("node"), "Node is needed for the plugin regression harness")
class TaskNotificationTests(unittest.TestCase):
    def test_completed_output_does_not_trigger_redundant_model_replies(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            jobs = e.private(root / "execution")
            e.private(jobs / "jobs")
            states = ["completed", "completed", "failed", "completed", "completed"]
            for index, state in enumerate(states):
                job_id = "job_" + str(index) * 32
                e.directory(jobs, job_id, create=True)
                e.save(
                    jobs,
                    {
                        "id": job_id,
                        "uid": os.getuid(),
                        "session": "ses_test",
                        "project": str(root.resolve()),
                        "state": state,
                        "exit_code": 1 if state == "failed" else 0,
                        "created": index,
                        "notify": True,
                    },
                )
                (jobs / "jobs" / job_id / "output.log").write_text("result")
            result = subprocess.run(
                [
                    shutil.which("node"),
                    str(Path(__file__).with_name("task_notifications.mjs")),
                    str(root),
                    sys.executable,
                    str(Path(e.__file__).resolve()),
                ],
                capture_output=True,
                text=True,
                timeout=40,
            )
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(result.stdout), {"toasts": 5, "prompts": 1})

    def test_output_observation_requires_contiguous_terminal_pages(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job_id = "job_" + "a" * 32
            e.directory(root, job_id, create=True)
            job = {
                "id": job_id,
                "uid": os.getuid(),
                "session": "ses_test",
                "project": str(root.resolve()),
                "state": "completed",
                "exit_code": 0,
            }
            e.save(root, job)
            (root / "jobs" / job_id / "output.log").write_text("abcdef")

            def read(begin, end, **changes):
                page = dict(
                    id=job_id,
                    state="completed",
                    offset=begin,
                    next_offset=end,
                    total_bytes=6,
                    all_output_delivered=end == 6,
                    truncated=False,
                )
                page.update(changes)
                return e.perform(root, "notice_read", job_id=job_id, page=page)["observed"]

            self.assertFalse(read(4, 6))  # A final page alone leaves an unread prefix.
            self.assertFalse(read(0, 2))
            self.assertFalse(read(4, 6))  # A gap must not be hidden.
            self.assertTrue(read(2, 6))
            self.assertFalse(read(0, 6, state="failed"))
            self.assertFalse(read(0, 6, total_bytes=7))
            with self.assertRaisesRegex(ValueError, "different session"):
                e.perform(
                    root,
                    "notice_read",
                    job_id=job_id,
                    session="ses_other",
                    project=str(root.resolve()),
                    page={},
                )
            job["state"] = "running"
            e.save(root, job)
            self.assertFalse(read(0, 6, state="running"))
            job = e.load(root, job_id)
            job.update(state="completed", exit_code=0)
            e.save(root, job)
            self.assertTrue(read(6, 6))  # Prefix read while running remains visible.
            (root / "jobs" / job_id / "output.log").write_text("abcdefg")
            self.assertFalse(
                read(6, 7, total_bytes=7)
            )  # Changed terminal output invalidates receipts.

    def test_zero_byte_terminal_output_still_requires_an_actual_read(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            job_id = "job_" + "b" * 32
            e.directory(root, job_id, create=True)
            e.save(
                root,
                {"id": job_id, "uid": os.getuid(), "state": "completed", "exit_code": 0},
            )
            page = e.perform(root, "output", job_id=job_id)
            self.assertNotIn("notification", e.load(root, job_id))
            self.assertTrue(e.perform(root, "notice_read", job_id=job_id, page=page)["observed"])
