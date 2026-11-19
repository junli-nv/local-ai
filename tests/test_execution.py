import base64
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from local_ai import execution as e


@unittest.skipUnless(Path("/proc/self/stat").exists(), "Linux process identity is required")
class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name) / "execution"
        self.project = Path(self.tmp.name) / "project"
        self.project.mkdir()
        self.ids = []

    def tearDown(self):
        for task in self.ids:
            try:
                e.perform(self.root, "stop", job_id=task)
                self.wait(task, lambda x: x["terminal"], timeout=6)
            except (OSError, ValueError):
                pass
        self.tmp.cleanup()

    def launch(self, code, key=None, session="ses_test", **kwargs):
        result = e.start(
            self.root,
            session,
            str(self.project),
            [sys.executable, "-u", "-c", code],
            key or str(len(self.ids)),
            **kwargs,
        )
        if result["id"] not in self.ids:
            self.ids.append(result["id"])
        return result

    def wait(self, task, predicate, timeout=5):
        deadline = time.monotonic() + timeout
        result = None
        while time.monotonic() < deadline:
            result = e.perform(self.root, "status", job_id=task)
            if predicate(result):
                return result
            time.sleep(0.03)
        self.fail("Task did not reach expected state: " + str(result))

    def test_async_idempotent_and_complete_byte_cursor(self):
        code = (
            "from pathlib import Path; import time\n"
            "Path('once').open('a').write('x')\n"
            "while not Path('release').exists(): time.sleep(.02)\n"
            "print('你好'*150)"
        )
        # Completion depends on a file created only AFTER start has returned.
        # A synchronous implementation reaches timeout and fails, regardless of CPU speed.
        result = self.launch(code, key="once", timeout=5)
        same = self.launch(code, key="once", timeout=5)
        self.assertEqual(result["id"], same["id"])
        (self.project / "release").touch()
        final = self.wait(result["id"], lambda x: x["terminal"])
        self.assertEqual(final["state"], "completed")
        got = bytearray()
        offset = 0
        while True:
            page = e.perform(self.root, "output", job_id=result["id"], offset=offset, limit=17)
            got.extend(base64.b64decode(page["data_base64"]))
            offset = page["next_offset"]
            if page["all_output_delivered"]:
                break
        self.assertEqual(got, ("你好" * 150 + "\n").encode())
        self.assertEqual(self.launch(code, key="once", timeout=5)["id"], result["id"])
        with self.assertRaisesRegex(ValueError, "different operation"):
            self.launch("print('different')", key="once")
        self.assertEqual((self.project / "once").read_text(), "x")

    def test_pause_resume_stop_and_unrelated_process_survives(self):
        other = subprocess.Popen(
            [sys.executable, "-c", "import time; time.sleep(60)"], start_new_session=True
        )
        try:
            task = self.launch(
                "import time\nwhile True:\n print('tick',flush=True); time.sleep(.02)"
            )["id"]
            self.wait(task, lambda x: x["output_bytes"] > 10)
            e.perform(self.root, "pause", job_id=task)
            self.wait(task, lambda x: x["state"] == "paused")
            size = e.perform(self.root, "status", job_id=task)["output_bytes"]
            time.sleep(0.15)
            self.assertEqual(e.perform(self.root, "status", job_id=task)["output_bytes"], size)
            e.perform(self.root, "resume", job_id=task)
            self.wait(task, lambda x: x["output_bytes"] > size)
            result = e.perform(self.root, "stop", job_id=task)
            self.assertIn(result["control_requested"], ["stop"])
            final = self.wait(task, lambda x: x["terminal"])
            self.assertEqual(final["state"], "cancelled")
            self.assertFalse(
                [x for x in e.members(final["pgid"]).values() if x["state"] not in {"Z", "X"}]
            )
            self.assertIsNone(other.poll())
        finally:
            other.terminate()
            other.wait(timeout=5)

    def test_session_gate_and_independently_paused_task(self):
        a = self.launch("import time; time.sleep(60)")["id"]
        b = self.launch("import time; time.sleep(60)")["id"]
        for task in [a, b]:
            self.wait(task, lambda x: x["state"] == "running")
        e.perform(self.root, "pause", job_id=a)
        self.wait(a, lambda x: x["state"] == "paused")
        opts = {"session": "ses_test", "project": str(self.project)}
        e.perform(self.root, "pause_session", **opts)
        self.wait(b, lambda x: x["state"] == "paused")
        with self.assertRaisesRegex(ValueError, "paused"):
            self.launch("print('must not run')", key="blocked")
        with self.assertRaisesRegex(ValueError, "Resume the session"):
            e.perform(self.root, "resume", job_id=b)
        e.perform(self.root, "resume_session", **opts)
        self.wait(b, lambda x: x["state"] == "running")
        self.assertEqual(e.perform(self.root, "status", job_id=a)["state"], "paused")
        e.perform(self.root, "stop_session", **opts)
        for task in [a, b]:
            self.assertEqual(self.wait(task, lambda x: x["terminal"])["state"], "cancelled")
        self.assertTrue(e.perform(self.root, "gate", **opts)["paused"])

    def test_stop_cleans_inherited_descendant_and_timeout(self):
        task = self.launch(
            "import subprocess,sys,time\nsubprocess.Popen([sys.executable,'-c','import time;time.sleep(60)'])\ntime.sleep(60)",
            timeout=0.3,
        )["id"]
        final = self.wait(task, lambda x: x["terminal"])
        self.assertEqual(final["state"], "timed_out")
        self.assertFalse(
            [x for x in e.members(final["pgid"]).values() if x["state"] not in {"Z", "X"}]
        )

    def test_overflow_and_nonzero_are_not_success(self):
        task = self.launch("import os; os.write(1,b'x'*20000)", max_bytes=1024)["id"]
        final = self.wait(task, lambda x: x["terminal"])
        self.assertEqual(final["state"], "output_limit")
        page = e.perform(self.root, "output", job_id=task)
        self.assertTrue(page["truncated"])
        self.assertEqual(page["total_bytes"], 1024)
        failed = self.launch("raise SystemExit(7)")["id"]
        self.assertEqual(self.wait(failed, lambda x: x["terminal"])["exit_code"], 7)

    def test_session_scope_and_stale_pid_refuse_signals(self):
        task = self.launch("import time;time.sleep(60)")["id"]
        self.wait(task, lambda x: x["state"] == "running")
        with self.assertRaisesRegex(ValueError, "different session"):
            e.perform(self.root, "stop", job_id=task, session="other", project=str(self.project))
        with patch.object(e, "members", return_value={"123": {"start": "new", "state": "S"}}):
            with patch("os.killpg", side_effect=AssertionError("must not signal")):
                with self.assertRaisesRegex(RuntimeError, "ownership"):
                    e.signal_group(
                        {"pgid": 123, "members": {"123": {"start": "old"}}}, signal.SIGKILL
                    )

    def test_worker_loss_is_visible_and_owned_stop_is_confirmed(self):
        task = self.launch("import time;time.sleep(60)")["id"]
        running = self.wait(task, lambda x: x["state"] == "running")
        os.kill(running["worker_pid"], signal.SIGKILL)
        self.wait(task, lambda x: x["state"] == "orphaned")
        e.perform(self.root, "stop", job_id=task)
        final = self.wait(task, lambda x: x["terminal"])
        self.assertEqual(final["state"], "cancelled")
        self.assertTrue(final["output_truncated"])

    def test_survives_launching_process_exit_and_removed_key_is_not_replayed(self):
        request = {
            "action": "start",
            "session": "ses_test",
            "project": str(self.project),
            "argv": [sys.executable, "-c", "import time;time.sleep(.3);print('survived')"],
            "request_id": "driver",
        }
        result = subprocess.run(
            [sys.executable, e.__file__, "_rpc", str(self.root)],
            input=json.dumps(request),
            text=True,
            capture_output=True,
            check=True,
        )
        task = json.loads(result.stdout)["result"]["id"]
        self.ids.append(task)
        self.assertEqual(self.wait(task, lambda x: x["terminal"])["state"], "completed")
        e.perform(self.root, "remove", job_id=task)
        self.ids.remove(task)
        with self.assertRaisesRegex(ValueError, "removed"):
            e.perform(self.root, **request)

    def test_invalid_ids_output_cursor_and_symlink_root(self):
        with self.assertRaises(ValueError):
            e.perform(self.root, "status", job_id="../../outside")
        task = self.launch("print('a')")["id"]
        self.wait(task, lambda x: x["terminal"])
        with self.assertRaises(ValueError):
            e.perform(self.root, "output", job_id=task, offset=10000)
        alias = Path(self.tmp.name) / "alias"
        alias.symlink_to(self.root)
        with self.assertRaisesRegex(ValueError, "private"):
            e.perform(alias, "list")

    def test_launch_failure_is_durable(self):
        task = e.start(self.root, "ses_test", str(self.project), ["/no-such-program"], "missing")[
            "id"
        ]
        self.ids.append(task)
        final = self.wait(task, lambda x: x["terminal"])
        self.assertEqual(final["state"], "failed")
        self.assertIn("FileNotFoundError", final["error"])

    def test_checkpoint_failure_cannot_launch_an_unacknowledged_command(self):
        real = e.save
        saves = []

        def checkpoint(root, job):
            saves.append(job["state"])
            if len(saves) == 2:
                raise OSError("checkpoint write failed")
            real(root, job)

        with patch.object(e, "save", side_effect=checkpoint):
            with self.assertRaisesRegex(OSError, "checkpoint"):
                self.launch(
                    "from pathlib import Path;Path('unexpected').write_text('bad')",
                    key="failed-checkpoint",
                )
        time.sleep(0.1)
        self.assertFalse((self.project / "unexpected").exists())
        records = e.perform(self.root, "list")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["state"], "failed")

    def test_worker_copy_failure_is_durable_and_never_queued_forever(self):
        with patch.object(e.shutil, "copy2", side_effect=OSError("copy failed")):
            with self.assertRaisesRegex(OSError, "copy failed"):
                self.launch("print('must not run')", key="copy-failure")
        records = e.perform(self.root, "list")
        self.assertEqual(len(records), 1)
        self.assertEqual(records[0]["state"], "failed")
