"""Native managed-task controls and permission regression; mock model, private state."""

import argparse
import importlib.util
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from local_ai import execution
from local_ai.artifacts import validate
from local_ai.client import prepare
from local_ai.common import atomic_json, private_dir
from local_ai.tasks import stop

SPEC = importlib.util.spec_from_file_location(
    "steering_base", Path(__file__).with_name("check-steering.py")
)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class Model(probe.Model):
    def __init__(self, project):
        super().__init__(project, 5)
        self.project = project
        self.issued = set()
        self.notifications = 0

    def reply(self, payload):
        if not payload.get("tools"):
            return {"content": "Managed control probe"}, "stop"
        if any(
            "LOCAL_AI_TASK_EVENT:" in str(r.get("content", "")) for r in payload.get("messages", [])
        ):
            self.notifications += 1
            return {"content": "NOTIFIED_OK"}, "stop"
        marker = ""
        for row in reversed(payload.get("messages", [])):
            if row.get("role") == "user":
                match = re.search(
                    r"CONTROL_(START|PAUSE|NEW|BLOCKED|RESUME|AFTER|STOP|AUTO|POLICY|ALLOWED)",
                    str(row.get("content")),
                )
                if match:
                    marker = match.group(1)
                    break
        if not marker or marker in self.issued:
            return {"content": "CONTROL_ACK_" + marker}, "stop"
        self.issued.add(marker)
        tool = "local_ai_task"
        if marker == "ALLOWED":
            tool = "bash"
            args = {
                "command": "echo permitted > policy-allowed",
                "description": "Native allowed command remains usable",
            }
        elif marker == "POLICY":
            tool = "bash"
            args = {
                "command": "echo checking; printf forbidden > denied-policy",
                "description": "Compound command denial test",
            }
        elif marker == "AUTO":
            tool = "bash"
            args = {
                "command": "sleep 3; echo AUTO_FINISHED",
                "description": "Automatic Bash background test",
            }
        elif marker in {"START", "NEW"}:
            code = (
                "import time\nfrom pathlib import Path\n"
                "Path('starts').open('a').write('x')\n"
                "p=Path('heartbeat')\n"
                "while True:\n"
                " with p.open('a') as f: f.write('x')\n"
                " time.sleep(.02)\n"
            )
            args = {
                "action": "start",
                "argv": [sys.executable, "-u", "-c", code],
                "request_id": "control-" + marker,
                "timeout": 60,
            }
        elif marker in {"BLOCKED", "AFTER"}:
            tool = "bash"
            args = {
                "command": ("sleep 1; " if marker == "AFTER" else "")
                + "printf checked > "
                + marker.lower(),
                "description": "Harmless paused-session gate check",
            }
        else:
            args = {
                "action": {
                    "PAUSE": "pause_session",
                    "RESUME": "resume_session",
                    "STOP": "stop_session",
                }[marker]
            }
        return {
            "tool_calls": [
                {
                    "index": 0,
                    "id": "call_control_" + marker,
                    "type": "function",
                    "function": {"name": tool, "arguments": json.dumps(args)},
                }
            ]
        }, "tool_calls"


def run(assets, output, case):
    manifest = validate(assets)
    if output.exists():
        raise ValueError("--output must be a new private evidence directory")
    output.mkdir(parents=True, mode=0o700)
    result = {
        "client_version": manifest["version"],
        "case": case,
        "mock_model": True,
        "state": "running",
    }
    try:
        with tempfile.TemporaryDirectory(prefix="local-ai-managed-controls-") as temp:
            root = Path(temp)
            project = private_dir(root / "project")
            state = private_dir(root / "state")
            run_dir = private_dir(root / "run")
            model = Model(project)
            api = ThreadingHTTPServer(("127.0.0.1", 0), model.handler())
            api.daemon_threads = True
            api.probe_errors = []
            thread = threading.Thread(target=api.serve_forever, daemon=True)
            thread.start()
            backend = None
            session = None
            deadline = time.monotonic() + 65

            def wait(predicate, label):
                while time.monotonic() < deadline:
                    value = predicate()
                    if value:
                        return value
                    if api.probe_errors:
                        raise RuntimeError(str(api.probe_errors))
                    if backend is not None and backend.poll() is not None:
                        raise RuntimeError("Native backend exited; inspect private backend.log")
                    time.sleep(0.05)
                raise RuntimeError("Deadline waiting for " + label)

            try:
                with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(root / "personal")}):
                    env = prepare(
                        state,
                        assets,
                        run_dir,
                        f"http://127.0.0.1:{api.server_port}/v1",
                        probe.MODEL,
                        project,
                    )
                if case == "controls":
                    # Keep control sequencing isolated from unsolicited completion prompts.
                    # The enhanced case independently verifies real notification delivery.
                    env["LOCAL_AI_NOTIFICATIONS"] = "false"
                cfg = json.loads(env["OPENCODE_CONFIG_CONTENT"])
                cfg["permission"] = {"*": "allow"}
                if case == "denied":
                    cfg["permission"]["bash"] = "deny"
                if case == "policy":
                    cfg["permission"]["bash"] = {"*": "allow", "printf *": "deny"}

                atomic_json(Path(env["OPENCODE_CONFIG"]), cfg)
                env["OPENCODE_CONFIG_CONTENT"] = json.dumps(cfg)
                env["OPENCODE_DISABLE_CLAUDE_CODE"] = "true"
                env["OPENCODE_DISABLE_EXTERNAL_SKILLS"] = "true"
                for name in ["OPENCODE_SERVER_PASSWORD", "OPENCODE_SERVER_USERNAME"]:
                    env.pop(name, None)
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0))
                    port = sock.getsockname()[1]
                base = f"http://127.0.0.1:{port}"
                with (output / "backend.log").open("wb") as log:
                    backend = subprocess.Popen(
                        [
                            str(assets / "bin/opencode"),
                            "serve",
                            "--hostname",
                            "127.0.0.1",
                            "--port",
                            str(port),
                        ],
                        cwd=project,
                        env=env,
                        stdout=log,
                        stderr=log,
                        start_new_session=True,
                    )

                    def ready():
                        try:
                            return probe.request(base + "/global/health", timeout=1)
                        except OSError:
                            return False

                    wait(ready, "native startup")
                    session = probe.request(
                        base + "/session", {"title": "Managed execution controls"}, timeout=35
                    )["id"]
                    task_root = Path(env["LOCAL_AI_EXECUTION_DIR"])

                    def jobs():
                        return execution.perform(
                            task_root, "list", session=session, project=str(project)
                        )

                    def step(marker):
                        probe.request(
                            base + "/session/" + session + "/message",
                            {
                                "model": {"providerID": "local-deepseek", "modelID": probe.MODEL},
                                "parts": [{"type": "text", "text": "CONTROL_" + marker}],
                            },
                            timeout=max(0.1, deadline - time.monotonic()),
                        )
                        messages = probe.request(base + "/session/" + session + "/message")
                        parts = [
                            p
                            for m in messages
                            for p in m.get("parts", [])
                            if p.get("type") == "tool"
                            and p.get("callID") == "call_control_" + marker
                        ]
                        if len(parts) != 1:
                            raise RuntimeError("Missing native tool result for " + marker)
                        return parts[0]["state"]

                    started = step(
                        "AUTO" if case == "enhanced" else "POLICY" if case == "policy" else "START"
                    )
                    if case == "policy":
                        if (
                            started["status"] != "error"
                            or (project / "denied-policy").exists()
                            or jobs()
                        ):
                            raise RuntimeError("Compound command bypassed native Bash denial")
                        allowed = step("ALLOWED")
                        if (
                            allowed["status"] != "completed"
                            or (project / "policy-allowed").read_text().strip() != "permitted"
                            or jobs()
                        ):
                            raise RuntimeError(
                                "Scoped Bash did not retain the usable native parser"
                            )
                        result["native_allowed_command_works"] = True
                        result["compound_bash_denial_preserved"] = True
                    elif case == "enhanced":
                        if started["status"] != "completed":
                            raise RuntimeError("Bash adapter did not return a managed result")
                        launched = json.loads(started["output"])
                        job_id = launched["job_id"]
                        if launched["terminal"]:
                            raise RuntimeError("Long Bash call blocked until completion")
                        wait(
                            lambda: model.notifications > 0,
                            "automatic completion notification to model",
                        )
                        wait(
                            lambda: execution.perform(task_root, "status", job_id=job_id)[
                                "notification"
                            ].get("delivered"),
                            "durable notification acknowledgement",
                        )
                        final = execution.perform(task_root, "status", job_id=job_id)
                        page = execution.perform(task_root, "output", job_id=job_id)
                        if (
                            final["state"] != "completed"
                            or "AUTO_FINISHED" not in page["text"]
                            or not page["all_output_delivered"]
                        ):
                            raise RuntimeError("Automatic Bash completion/output failed")
                        result.update(
                            auto_bash_background=True,
                            completion_reached_model=True,
                            output_verified=True,
                        )
                    elif case == "denied":
                        if started["status"] != "error":
                            raise RuntimeError(
                                "Denied Bash permission did not reject managed execution"
                            )
                        if jobs() or (project / "heartbeat").exists():
                            raise RuntimeError("Denied command was executed")
                        result["bash_denial_preserved"] = True
                    else:
                        if started["status"] != "completed":
                            raise RuntimeError("Managed start failed: " + str(started))
                        job_id = json.loads(started["output"])["id"]
                        wait(lambda: (project / "heartbeat").exists(), "command heartbeat")
                        if step("PAUSE")["status"] != "completed":
                            raise RuntimeError("Session pause failed")
                        wait(
                            lambda: execution.perform(task_root, "status", job_id=job_id)["state"]
                            == "paused",
                            "process-group pause",
                        )
                        before = (project / "heartbeat").stat().st_size
                        blocked = step("BLOCKED")
                        if blocked["status"] != "error" or (project / "blocked").exists():
                            raise RuntimeError("Paused session started another native tool")
                        denied_start = step("NEW")
                        if denied_start["status"] != "error" or len(jobs()) != 1:
                            raise RuntimeError("Paused session started a managed command")
                        if (project / "heartbeat").stat().st_size != before:
                            raise RuntimeError("Paused command continued writing")
                        if step("RESUME")["status"] != "completed":
                            raise RuntimeError("Session resume failed")
                        wait(
                            lambda: (project / "heartbeat").stat().st_size > before,
                            "resumed heartbeat",
                        )
                        after = step("AFTER")
                        if after["status"] != "completed":
                            raise RuntimeError(
                                "Explicit resume did not release native tools: " + str(after)
                            )
                        after_job = json.loads(after["output"])["job_id"]
                        completed_after = wait(
                            lambda: (
                                value
                                if (
                                    value := execution.perform(
                                        task_root, "status", job_id=after_job
                                    )
                                )["terminal"]
                                else None
                            ),
                            "resumed asynchronous native command completion",
                        )
                        if (
                            completed_after["state"] != "completed"
                            or completed_after["exit_code"] != 0
                        ):
                            raise RuntimeError(
                                "Resumed native command failed: " + str(completed_after)
                            )
                        if (project / "after").read_text() != "checked":
                            raise RuntimeError(
                                "Resumed native command did not produce expected content"
                            )
                        result["resumed_native_task_async"] = True
                        if step("STOP")["status"] != "completed":
                            raise RuntimeError("Session stop failed")
                        wait(
                            lambda: execution.perform(task_root, "status", job_id=job_id)[
                                "terminal"
                            ],
                            "confirmed process exit",
                        )
                        final = execution.perform(
                            task_root,
                            "status",
                            session=session,
                            project=str(project),
                            job_id=job_id,
                        )
                        if final["state"] != "cancelled":
                            raise RuntimeError("Stopped task did not reach cancelled")
                        if any(
                            v["state"] not in {"Z", "X"}
                            for v in execution.members(final["pgid"]).values()
                        ):
                            raise RuntimeError("Owned process group survived stop")
                        if not execution.perform(
                            task_root, "gate", session=session, project=str(project)
                        )["paused"]:
                            raise RuntimeError("Stop unexpectedly reopened session execution")
                        result.update(
                            pause_freezes_task=True,
                            paused_native_tool_rejected=True,
                            paused_start_rejected=True,
                            explicit_resume=True,
                            stop_confirmed=True,
                            task_runs_once=(project / "starts").read_text() == "x",
                        )
            finally:
                cleanup_error = None
                try:
                    if session is not None:
                        task_root = Path(env["LOCAL_AI_EXECUTION_DIR"])
                        execution.perform(
                            task_root, "stop_session", session=session, project=str(project)
                        )
                        end = time.monotonic() + 5
                        while time.monotonic() < end:
                            remaining = execution.perform(
                                task_root, "list", session=session, project=str(project)
                            )
                            if all(j["terminal"] for j in remaining):
                                break
                            time.sleep(0.05)
                        else:
                            cleanup_error = "Managed fixture task did not stop"
                except Exception as error:
                    cleanup_error = str(error)
                finally:
                    if backend is not None:
                        stop(backend)
                    api.shutdown()
                    api.server_close()
                    thread.join(timeout=3)
                if cleanup_error:
                    raise RuntimeError(cleanup_error)
        result["state"] = "passed"
        return result
    except BaseException as error:
        result.update(state="failed", error=str(error))
        raise
    finally:
        atomic_json(output / "report.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument(
        "--case", choices=["controls", "denied", "enhanced", "policy"], required=True
    )
    args = parser.parse_args()
    print(json.dumps(run(args.client_dir.resolve(), args.output.absolute(), args.case)))
