"""Bounded real-model steering and private-history recovery acceptance."""

import argparse
import contextlib
import importlib.util
import json
import os
import shlex
import socket
import subprocess
import time
from pathlib import Path
from unittest.mock import patch
from urllib.parse import quote

from local_ai import __version__, execution, portability, resume
from local_ai.client import prepare
from local_ai.common import atomic_json, private_dir
from local_ai.tasks import stop

SPEC = importlib.util.spec_from_file_location(
    "execution_probe", Path(__file__).with_name("check-execution.py")
)
shared = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(shared)
request = shared.probe.request


def check(options):
    output = Path(options.output).resolve()
    output.mkdir(parents=True, mode=0o700, exist_ok=False)
    project = private_dir(output / "project")
    state_root = private_dir(output / "state")
    assets = Path(options.client_dir).resolve()
    deadline = time.monotonic() + 90
    backends = []
    directories = {}
    context = {"session": None, "task_root": state_root / "execution"}
    result = {
        "state": "running",
        "local_ai_version": __version__,
        "real_model": True,
        "endpoint": options.endpoint,
        "model": options.model,
        "checks": {},
        "steps": [],
    }
    fixture = project / "fixture.py"
    fixture.write_text(
        "from pathlib import Path\nimport time\n"
        "with Path('starts').open('a') as f:f.write('ONCE\\n')\n"
        "print('LIVE_STARTED',flush=True)\n"
        "while True:\n"
        " Path('heartbeat').write_text(str(time.time_ns()))\n"
        " time.sleep(.1)\n"
    )
    argv = [os.sys.executable, "-u", str(fixture)]
    finite = project / "finite.py"
    finite.write_text("import time; time.sleep(2); print('FINITE_RESULT_42', flush=True)")
    finite_argv = [os.sys.executable, "-u", str(finite)]

    def wait(predicate, label):
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(0.05)
        raise RuntimeError("Deadline waiting for " + label)

    def launch(root, key, workdir=None):
        workdir = workdir or project
        state = private_dir(root / "services" / key)
        run = private_dir(state / "logs" / ("live-" + str(time.time_ns())))
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(output / "personal")}):
            env = prepare(state, assets, run, options.endpoint, options.model, workdir)
        cfg = json.loads(env["OPENCODE_CONFIG_CONTENT"])
        cfg["permission"] = {
            "*": "deny",
            "local_ai_task": "allow",
            "read": "allow",
            "glob": "allow",
            "external_directory": {str(workdir) + "/*": "allow"},
            "bash": {"*": "deny", shlex.join(argv): "allow", shlex.join(finite_argv): "allow"},
        }
        atomic_json(Path(env["OPENCODE_CONFIG"]), cfg)
        env["OPENCODE_CONFIG_CONTENT"] = json.dumps(cfg)
        env["OPENCODE_DISABLE_CLAUDE_CODE"] = "true"
        env["OPENCODE_DISABLE_EXTERNAL_SKILLS"] = "true"
        for keyname in ("OPENCODE_SERVER_PASSWORD", "OPENCODE_SERVER_USERNAME"):
            env.pop(keyname, None)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        with (run / "backend.log").open("wb") as log:
            backend = subprocess.Popen(
                [
                    str(assets / "bin/opencode"),
                    "serve",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=workdir,
                env=env,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        backends.append(backend)
        base = "http://127.0.0.1:" + str(port)

        def ready():
            if backend.poll() is not None:
                raise RuntimeError("Native backend exited")
            try:
                return request(base + "/global/health", timeout=1)
            except OSError:
                return False

        wait(ready, "native readiness")
        if not (state / "connection.json").exists():
            atomic_json(
                state / "connection.json",
                {
                    "state": str(state),
                    "state_dir": str(root),
                    "client_dir": str(assets),
                    "project": str(workdir),
                    "endpoint": options.endpoint,
                    "model": options.model,
                },
            )
        directories[base] = str(workdir)
        return base

    def step(base, session, prompt, label):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise RuntimeError("Acceptance deadline exceeded")
        value = request(
            base
            + "/session/"
            + session
            + "/message?directory="
            + quote(directories[base], safe=""),
            {
                "model": {"providerID": "local-deepseek", "modelID": options.model},
                "parts": [{"type": "text", "text": prompt}],
            },
            timeout=min(25, remaining),
        )
        text = "".join(p.get("text", "") for p in value.get("parts", []) if p.get("type") == "text")
        result["steps"].append(label)
        atomic_json(output / "result.json", result)
        print("LIVE_STEP", label, flush=True)
        return text

    try:
        base = launch(state_root, "6" * 20)
        session = request(base + "/session", {"title": "local-ai live acceptance"}, timeout=15)[
            "id"
        ]
        context["session"] = session
        step(
            base,
            session,
            "这是隔离验收。请用 local_ai_task start 启动下面参数数组，request_id 固定为 live-once，timeout=120。"
            "参数必须原样使用，不要读取个人文件，不要执行其他命令。启动后立即返回任务 ID，不要轮询，等待我下一条消息。argv="
            + json.dumps(argv),
            "start",
        )
        jobs = execution.perform(
            context["task_root"], "list", session=session, project=str(project)
        )
        target = [j for j in jobs if not j["terminal"]]
        if len(target) != 1:
            raise RuntimeError("Real model did not start exactly one managed task")
        identity = target[0]["id"]

        def status():
            return execution.perform(context["task_root"], "status", job_id=identity)

        wait(lambda: (project / "heartbeat").exists(), "live heartbeat")
        text = step(
            base, session, "保持后台任务运行。先回答 6*7，只回复结果，不执行工具。", "followup"
        )
        if "42" not in text or status()["terminal"]:
            raise RuntimeError("Side question was not answered during the live task")
        result["checks"]["followup_during_task"] = True
        step(
            base,
            session,
            "现在暂停本会话的任务。使用 pause_session，并查询确认 paused，不要启动新步骤。",
            "pause",
        )
        wait(lambda: status()["state"] == "paused", "confirmed pause")
        if not execution.perform(
            context["task_root"], "gate", session=session, project=str(project)
        )["paused"]:
            raise RuntimeError("Real pause did not close the session gate")
        before = (project / "heartbeat").read_text()
        text = step(
            base,
            session,
            "继续保持暂停，不要恢复。不要执行任何新工具，只回答：当前是否暂停？",
            "paused_question",
        )
        if before != (project / "heartbeat").read_text():
            raise RuntimeError("Paused task continued writing")
        result["checks"]["pause_freezes_task"] = True
        step(
            base,
            session,
            "现在我明确要求恢复本会话，使用 resume_session。继续同一任务，禁止重复启动原命令。",
            "resume",
        )
        wait(
            lambda: status()["state"] == "running"
            and (project / "heartbeat").read_text() != before,
            "confirmed resume",
        )
        result["checks"]["resume_same_task"] = True
        step(
            base,
            session,
            "停止本会话的测试任务。使用 stop_session，再查询确认任务已经退出，不要自动恢复或启动后续工作。",
            "stop",
        )
        wait(lambda: status()["terminal"], "confirmed stop")
        if status()["state"] != "cancelled":
            raise RuntimeError("Real model did not cancel the requested task")
        if (project / "starts").read_text().splitlines() != ["ONCE"]:
            raise RuntimeError("Original command was replayed")
        result["checks"].update(stop_confirmed=True, command_runs_once=True)
        finite_session = request(
            base + "/session", {"title": "Automatic completion acceptance"}, timeout=10
        )["id"]
        step(
            base,
            finite_session,
            "请用 local_ai_task start 启动以下参数数组，request_id 固定 finite-once，timeout=30。"
            "启动后立即返回任务ID，不要轮询。任务完成的系统通知到达后，读取完整输出并报告实际结果。不要重复执行。argv="
            + json.dumps(finite_argv),
            "finite_start",
        )

        def automatic_answer():
            messages = request(base + "/session/" + finite_session + "/message", timeout=2)
            notice_ids = {
                m.get("info", {}).get("id")
                for m in messages
                if "LOCAL_AI_TASK_EVENT:" in str(m.get("parts"))
            }
            return any(
                m.get("info", {}).get("role") == "assistant"
                and m.get("info", {}).get("parentID") in notice_ids
                and any(
                    p.get("type") == "text" and "FINITE_RESULT_42" in p.get("text", "")
                    for p in m.get("parts", [])
                )
                for m in messages
            )

        wait(automatic_answer, "real model automatic completion summary")
        result["checks"]["automatic_completion_summary"] = True
        print("LIVE_STEP", "automatic_completion_summary", flush=True)
        archive = output / "private-history.zip"
        portability.backup(state_root, archive)
        restored_root = output / "restored-state"
        relocated = private_dir(output / "relocated-project")
        (project / "migration-marker.txt").write_text("OLD_DIRECTORY")
        (relocated / "migration-marker.txt").write_text("NEW_DIRECTORY_MARKER")
        restored = portability.restore(
            restored_root, archive, assets, options.endpoint, project=relocated
        )
        restored_base = launch(
            restored_root, restored["histories"][0]["history_id"], workdir=relocated
        )
        prior = request(restored_base + "/session/" + session + "/message", timeout=10)
        if not any("6*7" in str(m.get("parts")) for m in prior):
            raise RuntimeError("Restored public session API did not retain earlier messages")
        text = step(
            restored_base,
            session,
            "只根据之前的对话，6*7 的结果是多少？只回复结果，不执行工具。",
            "restored_session",
        )
        if "42" not in text:
            raise RuntimeError("Restored session could not continue earlier context")
        result["checks"]["history_restore_same_session"] = True
        with patch.object(resume, "client_home", return_value=restored_root):
            located, target_project = resume.locate(session)
        if Path(target_project) != relocated:
            raise RuntimeError("Resume launcher did not retain the restored project mapping")
        text = step(
            restored_base,
            session,
            "请只读当前项目的 migration-marker.txt，报告内容。不要读旧项目目录，不执行任何写操作。",
            "restored_project",
        )
        if "NEW_DIRECTORY_MARKER" not in text:
            raise RuntimeError("Restored session did not use the new project")
        result["checks"]["history_restore_project_override"] = True
        result["session_id"] = session
        result["state"] = "passed"
        return result
    except BaseException as error:
        result.update(state="failed", error=type(error).__name__ + ": " + str(error))
        raise
    finally:
        if context["session"]:
            with contextlib.suppress(Exception):
                execution.perform(
                    context["task_root"],
                    "stop_session",
                    session=context["session"],
                    project=str(project),
                )
                end = time.monotonic() + 4
                while time.monotonic() < end:
                    jobs = execution.perform(
                        context["task_root"],
                        "list",
                        session=context["session"],
                        project=str(project),
                    )
                    if all(j["terminal"] for j in jobs):
                        break
                    time.sleep(0.05)
        for backend in backends:
            stop(backend)
        atomic_json(output / "result.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-dir", type=Path, required=True)
    parser.add_argument("--endpoint", required=True)
    parser.add_argument("--model", required=True)
    parser.add_argument("--output", type=Path, required=True)
    print(json.dumps(check(parser.parse_args())))
