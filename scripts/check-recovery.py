"""Explicit bounded SSH recovery acceptance in private state; no GPU work."""

import argparse
import json
import os
import signal
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from local_ai import adapters as a
from local_ai import execution as e


def check(host, output):
    output = Path(output).resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    project = output / "project"
    project.mkdir(mode=0o700)
    root = output / "execution"
    marker = "/tmp/local-ai-recovery-" + uuid.uuid4().hex
    code = (
        "from pathlib import Path;import time;"
        "p=Path(" + repr(marker) + ");p.mkdir(exist_ok=True);"
        "f=(p/'starts').open('a');f.write('ONCE\\n');f.close();"
        "print('STARTED',flush=True);time.sleep(10);"
        "assert (p/'starts').read_text().splitlines()==['ONCE'];"
        "print('RECOVERY_RESULT_42',flush=True)"
    )
    job = None
    result = {"host": host, "state": "running", "checks": {}}
    deadline = time.monotonic() + 55

    def wait(predicate, label):
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(0.1)
        raise RuntimeError("Deadline waiting for " + label)

    try:
        job = a.start(
            root,
            "ses_recovery_acceptance",
            str(project),
            ["python3", "-u", "-c", code],
            "run-once",
            "ssh",
            host=host,
            remote_project="/tmp",
            timeout=45,
        )
        identity = job["id"]
        wait(
            lambda: e.perform(root, "status", job_id=identity).get("output_bytes", 0) > 0,
            "remote command start",
        )
        before = e.load(root, identity)
        assert a.controller_alive(before)
        assert e.stamp(before["controller_pid"]) == before["controller_start"]
        os.killpg(before["controller_pid"], signal.SIGKILL)
        wait(lambda: not a.controller_alive(e.load(root, identity)), "controller exit")
        with patch.object(a, "run", side_effect=OSError("injected transport outage")):
            uncertain = e.perform(root, "status", job_id=identity)
        assert uncertain["uncertain"] and not uncertain["terminal"]
        with ThreadPoolExecutor(max_workers=2) as pool:
            answers = list(
                pool.map(lambda _: e.perform(root, "recover", job_id=identity), range(2))
            )
        assert sum(bool(v.get("controller_restarted")) for v in answers) == 1
        after = e.load(root, identity)
        assert after["remote_id"] == before["remote_id"]
        assert after["request_id"] == before["request_id"]
        final = wait(
            lambda: (v if (v := e.perform(root, "status", job_id=identity))["terminal"] else None),
            "confirmed completion",
        )
        assert final["state"] == "completed" and final["exit_code"] == 0
        wait(
            lambda: e.load(root, identity).get("output_cache", {}).get("complete"),
            "complete private output cache",
        )
        with patch.object(a, "run", side_effect=AssertionError("must not access SSH offline")):
            cached = e.perform(root, "status", job_id=identity)
            page = e.perform(root, "output", job_id=identity)
        assert cached["source"] == page["source"] == "cache"
        assert page["all_output_delivered"] and not page["truncated"]
        assert "RECOVERY_RESULT_42" in page["text"]
        count = (
            a.run(
                [
                    "python3",
                    "-c",
                    "from pathlib import Path;print(len(Path("
                    + repr(marker)
                    + ",'starts').read_text().splitlines()))",
                ],
                host,
            )
            .decode()
            .strip()
        )
        assert count == "1"
        result.update(state="passed", job_id=identity)
        result["checks"] = dict(
            controller_killed=True,
            transport_failure_recorded=True,
            concurrent_recovery_single_monitor=True,
            original_remote_identity=True,
            command_executed_once=True,
            completion_confirmed=True,
            offline_complete_output=True,
        )
        return result
    except BaseException as error:
        result.update(state="failed", error=type(error).__name__ + ": " + str(error))
        raise
    finally:
        cleanup_errors = []
        if job is not None:
            try:
                if e.load(root, job["id"])["state"] not in e.TERMINAL:
                    e.perform(root, "stop", job_id=job["id"])
                    until = time.monotonic() + 4
                    while time.monotonic() < until:
                        if e.perform(root, "status", job_id=job["id"])["terminal"]:
                            break
                        time.sleep(0.1)
                    else:
                        raise RuntimeError("Test task cancellation not confirmed")
            except (OSError, ValueError, RuntimeError) as error:
                cleanup_errors.append(str(error))
            try:
                a.run(
                    [
                        "python3",
                        "-c",
                        "from pathlib import Path;p=Path(" + repr(marker) + ");"
                        "(p/'starts').unlink(missing_ok=True);p.rmdir() if p.exists() else None",
                    ],
                    host,
                )
            except (OSError, ValueError, RuntimeError) as error:
                cleanup_errors.append(str(error))
        if cleanup_errors:
            result["cleanup_errors"] = cleanup_errors
        cleanup_failed = bool(cleanup_errors) and result["state"] == "passed"
        if cleanup_failed:
            result["state"] = "failed"
        e.atomic(output / "result.json", result)
        if cleanup_failed:
            raise RuntimeError("Acceptance cleanup failed; inspect private result.json")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(check(args.host, args.output), indent=2))
