"""Explicit model-and-tool workflow acceptance in a new private workspace."""

import json
import math
import os
import subprocess
import sys
import time
from pathlib import Path

from . import __version__
from .common import atomic_json
from .telemetry import report

CASES = ("edit-test", "diagnose", "resume")


def run(options):
    if not math.isfinite(options.timeout) or options.timeout <= 0 or options.timeout > 3600:
        raise ValueError("timeout must be between 0 and 3600 seconds")
    if options.case not in CASES:
        raise ValueError("Unknown workflow case")
    output = Path(options.output).expanduser().resolve()
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    workspace = output / "workspace"
    workspace.mkdir()
    (output / "home").mkdir()
    (output / "config").mkdir()
    case = options.case
    if case == "edit-test":
        (workspace / "calc.py").write_text("def add(a, b):\n    return a - b\n")
        (workspace / "test_calc.py").write_text(
            "import unittest\nfrom calc import add\n"
            "class TestAdd(unittest.TestCase):\n"
            "    def test_positive(self): self.assertEqual(add(2, 3), 5)\n"
            "    def test_negative(self): self.assertEqual(add(-2, -3), -5)\n"
        )
        prompts = [
            "Fix calc.py so its addition tests pass. Do not modify test_calc.py. "
            "Run python3 -m unittest -v and report the actual result."
        ]
    elif case == "diagnose":
        (workspace / "service.log").write_text(
            "09:00 INFO model loaded\n09:01 ERROR bind 127.0.0.1:18000: Address already in use\n"
        )
        prompts = [
            "Read service.log. Write diagnosis.json with keys cause='port_conflict' "
            "and port=18000. Diagnose only; do not start or stop services."
        ]
    else:
        prompts = [
            "Use tools to create ledger.txt containing exactly one line: FIRST. Do not append twice.",
            "Continue the previous task. Read ledger.txt first. Preserve its FIRST line and append "
            "exactly one SECOND line if absent. Report the actual file contents.",
        ]
    original_test = (workspace / "test_calc.py").read_bytes() if case == "edit-test" else None
    env = dict(
        os.environ,
        HOME=str(output / "home"),
        XDG_CONFIG_HOME=str(output / "config"),
        XDG_STATE_HOME=str(output / "user-state"),
        PYTHONPATH=os.pathsep.join(sys.path),
    )
    result = {
        "schema": 1,
        "local_ai_version": __version__,
        "case": case,
        "endpoint": options.endpoint,
        "model": options.model,
        "started": time.time(),
        "state": "running",
        "turns": [],
        "checks": {},
    }
    atomic_json(output / "result.json", result)
    session_id = None
    try:
        for index, prompt in enumerate(prompts):
            command = [
                sys.executable,
                "-c",
                "from local_ai.cli import main; raise SystemExit(main())",
                "chat",
                "--endpoint",
                options.endpoint,
                "--model",
                options.model,
                "--client-dir",
                str(options.client_dir),
                "--state-dir",
                str(output / "state"),
                "--project",
                str(workspace),
                "--format",
                "json",
                "--run-timeout",
                str(options.timeout),
                "--run",
                prompt,
            ]
            if session_id:
                command += ["--session", session_id]
            started = time.monotonic()
            with (
                (output / f"turn-{index}.jsonl").open("wb") as stdout,
                (output / f"turn-{index}.stderr").open("wb") as stderr,
            ):
                child = subprocess.run(command, env=env, stdout=stdout, stderr=stderr)
            paths = sorted(
                (output / "state").glob("services/*/logs/*/run.json"),
                key=lambda p: p.stat().st_mtime,
            )
            diagnostics = report(paths[-1].parent) if paths else {}
            sessions = diagnostics.get("sessions", [])
            if session_id is None and len(sessions) == 1:
                session_id = sessions[0]
            result["turns"].append(
                {
                    "exit_code": child.returncode,
                    "elapsed_seconds": time.monotonic() - started,
                    "run_dir": str(paths[-1].parent) if paths else None,
                    "request_count": len(diagnostics.get("requests", [])),
                    "client_version": diagnostics.get("run", {}).get("client_version"),
                    "tool_count": len(diagnostics.get("tool_calls", [])),
                    "sessions": sessions,
                }
            )
            if child.returncode or (len(prompts) > 1 and not session_id):
                raise RuntimeError("Workflow turn failed or unique session ID unavailable")
        if case == "edit-test":
            check = subprocess.run(
                [sys.executable, "-m", "unittest", "-v"],
                cwd=workspace,
                capture_output=True,
                text=True,
                timeout=15,
            )
            (output / "verification.txt").write_text(check.stdout + check.stderr)
            result["checks"] = {
                "tests_pass": check.returncode == 0,
                "tests_unchanged": (workspace / "test_calc.py").read_bytes() == original_test,
            }
        elif case == "diagnose":
            value = json.loads((workspace / "diagnosis.json").read_text())
            result["checks"] = {
                "cause_correct": value.get("cause") == "port_conflict",
                "port_correct": value.get("port") == 18000,
            }
        else:
            result["checks"] = {
                "exactly_once": (workspace / "ledger.txt").read_text().splitlines()
                == ["FIRST", "SECOND"],
                "same_session": all(t["sessions"] == [session_id] for t in result["turns"]),
            }
        result["checks"]["tools_observed"] = all(t["tool_count"] > 0 for t in result["turns"])
        result["state"] = "passed" if all(result["checks"].values()) else "failed"
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        result["state"] = "failed"
        result["error_type"] = type(error).__name__
    except KeyboardInterrupt:
        result["state"] = "interrupted"
        raise
    finally:
        result["ended"] = time.time()
        result["elapsed_seconds"] = result["ended"] - result["started"]
        atomic_json(output / "result.json", result)
    return result
