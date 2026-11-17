"""Durable launch status and bounded subprocess supervision; never automatically replay work."""

import json
import os
import selectors
import shlex
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path

from .common import atomic_json
from .telemetry import lines, report


def identity(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except OSError:
        return None


def stop(child):
    try:
        os.killpg(child.pid, signal.SIGTERM)
    except ProcessLookupError:
        return
    try:
        child.wait(timeout=3)
    except subprocess.TimeoutExpired:
        pass
    # The leader may exit while a tool descendant remains in the same process group.
    try:
        os.killpg(child.pid, signal.SIGKILL)
    except ProcessLookupError:
        pass
    child.wait(timeout=3)


class Terminated(BaseException):
    pass


def terminated(signum, frame):
    raise Terminated()


def execute(command, project, env, logfile, prompt):
    directory = logfile.parent
    path = directory / "run.json"
    context = json.loads(env.get("LOCAL_AI_CONTEXT", "{}"))
    record = {
        **context,
        "schema": 1,
        "pid": os.getpid(),
        "pid_identity": identity(os.getpid()),
        "dependencies_reused": env.get("LOCAL_AI_DEPENDENCIES_REUSED") == "true",
        "started": time.time(),
        "state": "starting",
    }
    atomic_json(path, record)
    timeout = float(env.get("LOCAL_AI_RUN_TIMEOUT", "0"))
    heartbeat = float(env.get("LOCAL_AI_HEARTBEAT", "15"))
    if prompt is None:
        command = ["script", "-q", "-e", "-f", str(logfile), "-c", shlex.join(command)]
    started = last = time.monotonic()
    child = None
    code = 1
    state = "failed"
    previous_term = None
    if threading.current_thread() is threading.main_thread():
        previous_term = signal.signal(signal.SIGTERM, terminated)
    try:
        with logfile.open("ab") as log, selectors.DefaultSelector() as selector:
            child = subprocess.Popen(
                command,
                cwd=project,
                env=env,
                start_new_session=True,
                stdout=subprocess.PIPE if prompt is not None else None,
                stderr=subprocess.STDOUT if prompt is not None else None,
            )
            record.update(state="running", child_pid=child.pid)
            atomic_json(path, record)
            if child.stdout:
                selector.register(child.stdout, selectors.EVENT_READ)
            while child.poll() is None or selector.get_map():
                now = time.monotonic()
                if timeout and now - started >= timeout:
                    state, code = "timed_out", 124
                    stop(child)
                    break
                if heartbeat and prompt is not None and now - last >= heartbeat:
                    print(
                        f"local-ai: running {now - started:.0f}s; status: {directory}",
                        file=sys.stderr,
                    )
                    last = now
                if selector.get_map():
                    for key, _ in selector.select(timeout=0.2):
                        chunk = os.read(key.fileobj.fileno(), 65536)
                        if not chunk:
                            selector.unregister(key.fileobj)
                            continue
                        log.write(chunk)
                        log.flush()
                        sys.stdout.buffer.write(chunk)
                        sys.stdout.buffer.flush()
                else:
                    time.sleep(0.1)
            else:
                code = child.wait()
                state = "completed" if code == 0 else "failed"
    except KeyboardInterrupt:
        state, code = "interrupted", 130
    except Terminated:
        state, code = "interrupted", 143
    finally:
        if child and child.poll() is None:
            stop(child)
        if child and child.stdout:
            child.stdout.close()
        if previous_term is not None:
            signal.signal(signal.SIGTERM, previous_term)
        events, malformed = lines(directory / "events.jsonl")
        if code == 0 and any(e.get("kind") == "error" for e in events):
            state, code = "failed", 1
        if (
            code == 0
            and prompt is not None
            and not any(e.get("kind") == "model_start" for e in events)
        ):
            record["observation_warning"] = "No model-start event; native plugin may be unavailable"
        record.update(
            state=state,
            exit_code=code,
            ended=time.time(),
            elapsed_seconds=time.monotonic() - started,
            malformed_events=malformed,
        )
        atomic_json(path, record)
        print(
            f"local-ai: {state}; report: "
            + shlex.join(
                [
                    context.get("launcher", "local-ai"),
                    "client",
                    "report",
                    "--run-dir",
                    str(directory),
                ]
            ),
            file=sys.stderr,
        )
    return code


def list_runs(state_root, limit=20):
    if limit < 1 or limit > 1000:
        raise ValueError("limit must be between 1 and 1000")
    files = sorted(
        Path(state_root).expanduser().glob("services/*/logs/*/run.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )[:limit]
    result = []
    for path in files:
        try:
            value = report(path.parent)
            meta = value["run"]
            result.append(
                {
                    "run_dir": str(path.parent),
                    **meta,
                    "sessions": value["sessions"],
                    "pending_tools": len(value["pending_tools"]),
                }
            )
        except (OSError, ValueError) as error:
            result.append(
                {
                    "run_dir": str(path.parent),
                    "state": "unreadable",
                    "error_type": type(error).__name__,
                }
            )
    return result
