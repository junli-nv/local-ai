import json
import os
import signal
import sys
import tempfile
import time
import unittest
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
