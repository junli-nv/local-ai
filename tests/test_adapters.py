import base64
import json
import os
import signal
import sys
import tempfile
import time
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from local_ai import adapters as a
from local_ai import execution as e


@unittest.skipUnless(Path("/proc/self/stat").exists(), "Linux process groups required")
class AdapterTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.root = self.base / "execution"
        self.project = self.base / "project"
        self.project.mkdir()
        self.ids = []

    def tearDown(self):
        for identity in self.ids:
            try:
                if e.load(self.root, identity)["state"] not in e.TERMINAL:
                    e.perform(self.root, "stop", job_id=identity)
            except (OSError, ValueError, RuntimeError):
                pass
        end = time.monotonic() + 6
        while time.monotonic() < end:
            values = [e.load(self.root, k) for k in self.ids]
            if all(j["state"] in e.TERMINAL for j in values):
                break
            time.sleep(0.1)
        for identity in self.ids:
            job = e.load(self.root, identity)
            pid = job.get("controller_pid")
            if pid and e.stamp(pid) == job.get("controller_start"):
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
        for path in self.base.glob("remote/.local/state/local-ai-remote/*/jobs/*/job.json"):
            try:
                e.perform(path.parents[2], "stop", job_id=path.parent.name)
            except (OSError, ValueError, RuntimeError):
                pass
        time.sleep(0.15)
        self.temp.cleanup()

    def reserve(self, adapter, **args):
        job = a.start(
            self.root,
            "ses_adapter",
            str(self.project),
            ["/bin/bash", "-lc", "echo done"],
            "operation",
            adapter,
            timeout=30,
            **args,
        )
        self.ids.append(job["id"])
        return job

    def wait(self, identity, predicate, timeout=12):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            value = e.perform(self.root, "status", job_id=identity)
            if predicate(value):
                return value
            time.sleep(0.05)
        self.fail("Adapter state not confirmed: " + str(value))

    def test_real_remote_protocol_survives_controller_launcher_and_controls_owned_group(self):
        binary = self.base / "bin"
        binary.mkdir()
        shim = binary / "ssh"
        shim.write_text(
            "#!" + sys.executable + "\nimport os,sys\n"
            "os.environ['HOME']=os.environ['LOCAL_AI_TEST_REMOTE_HOME']\n"
            "os.execv('/bin/bash',['/bin/bash','-c',sys.argv[-1]])\n"
        )
        shim.chmod(0o700)
        remote = self.base / "remote"
        remote.mkdir()
        with patch.dict(
            os.environ,
            {
                "PATH": str(binary) + os.pathsep + os.environ["PATH"],
                "LOCAL_AI_TEST_REMOTE_HOME": str(remote),
            },
        ):
            job = a.start(
                self.root,
                "ses_adapter",
                str(self.project),
                [
                    sys.executable,
                    "-u",
                    "-c",
                    "import time\nprint('remote started',flush=True)\ntime.sleep(20)",
                ],
                "remote-once",
                "ssh",
                host="fixture",
                remote_project=str(self.project),
                timeout=30,
            )
            self.ids.append(job["id"])
            self.wait(job["id"], lambda r: r["state"] == "running" and r.get("output_bytes", 0) > 0)
            self.assertIsNotNone(e.load(self.root, job["id"]).get("remote_id"))
            original = e.load(self.root, job["id"])
            os.killpg(original["controller_pid"], signal.SIGKILL)
            deadline = time.monotonic() + 3
            while a.controller_alive(e.load(self.root, job["id"])) and time.monotonic() < deadline:
                time.sleep(0.03)
            self.assertFalse(a.controller_alive(e.load(self.root, job["id"])))
            with ThreadPoolExecutor(max_workers=2) as pool:
                attempts = list(
                    pool.map(lambda _: e.perform(self.root, "recover", job_id=job["id"]), range(2))
                )
            self.assertEqual(sum(bool(r.get("controller_restarted")) for r in attempts), 1)
            recovered = e.load(self.root, job["id"])
            self.assertNotEqual(recovered["controller_pid"], original["controller_pid"])
            self.assertEqual(recovered["remote_id"], original["remote_id"])
            self.assertEqual(recovered["request_id"], original["request_id"])

            e.perform(self.root, "pause", job_id=job["id"])
            self.wait(job["id"], lambda r: r["state"] == "paused")
            e.perform(self.root, "resume", job_id=job["id"])
            self.wait(job["id"], lambda r: r["state"] == "running" and r.get("output_bytes", 0) > 0)
            e.perform(self.root, "stop", job_id=job["id"])
            final = self.wait(job["id"], lambda r: r["terminal"])
            self.assertEqual(final["state"], "cancelled")
            output = e.perform(self.root, "output", job_id=job["id"])
            self.assertIn("remote started", output["text"])
            self.assertTrue(output["all_output_delivered"])
            with patch.object(
                a, "run", side_effect=AssertionError("offline: must use cached result")
            ):
                cached = e.perform(self.root, "status", job_id=job["id"])
                page = e.perform(self.root, "output", job_id=job["id"], limit=3)
                self.assertEqual(cached["state"], "cancelled")
                self.assertEqual(cached["source"], "cache")
                self.assertEqual(page["source"], "cache")
                self.assertFalse(page["all_output_delivered"])
                rest = e.perform(self.root, "output", job_id=job["id"], offset=page["next_offset"])
                self.assertTrue(rest["all_output_delivered"])
                self.assertEqual(page["text"] + rest["text"], output["text"])

            again = a.start(
                self.root,
                "ses_adapter",
                str(self.project),
                [
                    sys.executable,
                    "-u",
                    "-c",
                    "import time\nprint('remote started',flush=True)\ntime.sleep(20)",
                ],
                "remote-once",
                "ssh",
                host="fixture",
                remote_project=str(self.project),
                timeout=30,
            )
            self.assertTrue(again["reused"])
            self.assertEqual(again["id"], job["id"])

    def test_slurm_stop_requires_matching_identity_and_verified_terminal_record(self):
        state = {"value": "RUNNING"}
        calls = []

        def run(argv, host=None, **kwargs):
            calls.append(argv)
            if argv[0] == "sbatch":
                return b"12345\n"
            if argv[:3] == ["scontrol", "show", "job"]:
                job = e.load(self.root, self.ids[0])
                return (
                    "JobId=12345 JobName="
                    + job["name"]
                    + " UserId=test("
                    + str(os.getuid())
                    + ") JobState="
                    + state["value"]
                    + " ExitCode=0:0"
                ).encode()
            if argv[0] == "scancel":
                state["value"] = "CANCELLED"
                return b""
            if argv[:2] == ["scontrol", "suspend"]:
                state["value"] = "SUSPENDED"
                return b""
            if argv[:2] == ["scontrol", "resume"]:
                state["value"] = "RUNNING"
                return b""
            raise AssertionError(argv)

        with patch.object(a, "spawn_monitor"), patch.object(a, "run", side_effect=run):
            job = self.reserve("slurm")
            a.submit_once(self.root, job)
            e.perform(self.root, "pause", job_id=job["id"])
            self.assertEqual(e.perform(self.root, "status", job_id=job["id"])["state"], "paused")
            e.perform(self.root, "resume", job_id=job["id"])
            e.perform(self.root, "stop", job_id=job["id"])
            self.assertEqual(e.perform(self.root, "status", job_id=job["id"])["state"], "cancelled")
            self.assertEqual(sum(cmd[0] == "sbatch" for cmd in calls), 1)
            self.assertIn(["scancel", "12345"], calls)

    def test_missing_scheduler_accounting_is_unknown_and_never_resubmits(self):
        with patch.object(a, "spawn_monitor"), patch.object(a, "run", return_value=b"") as run:
            job = self.reserve("slurm")
            for _ in range(2):
                status = e.perform(self.root, "status", job_id=job["id"])
                self.assertFalse(status["terminal"])
                self.assertTrue(status["uncertain"])
            self.assertFalse(any(c.args[0][0] == "sbatch" for c in run.call_args_list))
        with e.guard(self.root):
            saved = e.load(self.root, job["id"])
            saved["state"] = "lost"
            e.save(self.root, saved)

    def test_container_label_mismatch_cannot_cancel_unrelated_container(self):
        calls = []

        def run(argv, host=None, **kwargs):
            calls.append(argv)
            if argv[:2] == ["docker", "inspect"]:
                return json.dumps(
                    [{"Id": "a" * 64, "Config": {"Labels": {"io.local-ai.job": "other"}}}]
                ).encode()
            raise AssertionError(argv)

        with patch.object(a, "spawn_monitor"), patch.object(a, "run", side_effect=run):
            job = self.reserve("container", image="prepared:latest")
            value = e.perform(self.root, "stop", job_id=job["id"])
            self.assertFalse(value["terminal"])
            self.assertTrue(value["uncertain"])
            self.assertFalse(any(cmd[:2] == ["docker", "stop"] for cmd in calls))
        with e.guard(self.root):
            saved = e.load(self.root, job["id"])
            saved["state"] = "lost"
            e.save(self.root, saved)

    def test_recovery_never_submits_an_unverified_operation(self):
        with patch.object(a, "spawn_monitor") as spawn:
            job = self.reserve("ssh", host="fixture")
            spawn.reset_mock()
            with self.assertRaisesRegex(ValueError, "cannot submit"):
                e.perform(self.root, "recover", job_id=job["id"])
            with e.guard(self.root):
                value = e.load(self.root, job["id"])
                value["submission_attempted"] = True
                e.save(self.root, value)
            with patch.object(a, "run", side_effect=OSError("link down")):
                result = e.perform(self.root, "recover", job_id=job["id"])
            self.assertEqual(result["recovery"], "backend_unverified")
            spawn.assert_not_called()
        with e.guard(self.root):
            value = e.load(self.root, job["id"])
            value["state"] = "lost"
            e.save(self.root, value)

    def test_partial_cache_never_claims_complete_or_loses_confirmed_state(self):
        with patch.object(a, "spawn_monitor"):
            job = self.reserve("ssh", host="fixture")
        value = e.load(self.root, job["id"])
        value.update(state="completed", exit_code=0, terminal_confirmed_at=time.time())
        a.remember_output(
            self.root,
            value,
            {
                "offset": 0,
                "next_offset": 3,
                "total_bytes": 9,
                "data_base64": base64.b64encode(b"abc").decode(),
            },
        )
        with e.guard(self.root):
            e.save(self.root, value)
        with patch.object(a, "run", side_effect=OSError("link down")):
            page = e.perform(self.root, "output", job_id=job["id"])
            self.assertEqual(page["text"], "abc")
            self.assertTrue(page["coverage_gap"])
            self.assertFalse(page["all_output_delivered"])
            self.assertEqual(e.perform(self.root, "status", job_id=job["id"])["state"], "completed")
            with self.assertRaisesRegex(RuntimeError, "coverage ends"):
                e.perform(self.root, "output", job_id=job["id"], offset=3)
        self.assertIsNotNone(e.load(self.root, job["id"]).get("cache_error"))

    def test_cached_prefix_rejects_changed_bytes_and_gaps(self):
        with patch.object(a, "spawn_monitor"):
            job = self.reserve("ssh", host="fixture")
        value = e.load(self.root, job["id"])

        def page(offset, data):
            return {
                "offset": offset,
                "next_offset": offset + len(data),
                "total_bytes": 10,
                "data_base64": base64.b64encode(data).decode(),
            }

        a.remember_output(self.root, value, page(0, b"abc"))
        a.remember_output(self.root, value, page(5, b"gap"))
        self.assertEqual(value["output_cache"]["bytes"], 3)
        with self.assertRaisesRegex(RuntimeError, "coverage is inconsistent"):
            a.remember_output(self.root, value, page(0, b"xyz"))
        with e.guard(self.root):
            value["state"] = "lost"
            e.save(self.root, value)

    def test_cancel_before_submission_has_confirmed_empty_output_offline(self):
        with patch.object(a, "spawn_monitor"):
            job = self.reserve("ssh", host="fixture")
        with e.guard(self.root):
            value = e.load(self.root, job["id"])
            value["control"] = "stop"
            e.save(self.root, value)
        with patch.object(a, "run", side_effect=AssertionError("no backend submission permitted")):
            a.submit_once(self.root, value)
            status = e.perform(self.root, "status", job_id=job["id"])
            self.assertEqual(status["state"], "cancelled")
            self.assertFalse(status.get("submission_attempted", False))
            page = e.perform(self.root, "output", job_id=job["id"])
            self.assertEqual(page["text"], "")
            self.assertTrue(page["all_output_delivered"])
            self.assertEqual(
                e.perform(self.root, "recover", job_id=job["id"])["recovery"], "already_complete"
            )
