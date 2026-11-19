"""Private durable noninteractive tasks; Python stdlib, Linux process-group ownership."""

import base64
import contextlib
import fcntl
import hashlib
import json
import math
import os
import re
import selectors
import shutil
import signal
import subprocess
import sys
import tempfile
import threading
import time
import uuid
from pathlib import Path

TERMINAL = {"completed", "failed", "cancelled", "timed_out", "output_limit", "lost"}
ID = re.compile(r"job_[a-f0-9]{32}\Z")


def private(path):
    path = Path(path).absolute()
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    st = path.lstat()
    if path.is_symlink() or not path.is_dir() or st.st_uid != os.getuid() or st.st_mode & 0o077:
        raise ValueError("Task state must be a private directory owned by the current user")
    return path


def atomic(path, value):
    fd, name = tempfile.mkstemp(prefix=".next-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as out:
            json.dump(value, out)
            out.write("\n")
            out.flush()
            os.fsync(out.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


@contextlib.contextmanager
def guard(root):
    root = private(root)
    fd = os.open(root / ".lock", os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield root


def stamp(pid):
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        return fields[19]
    except (OSError, IndexError):
        return None


def members(pgid):
    result = {}
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            f = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            if int(f[2]) == pgid and entry.stat().st_uid == os.getuid():
                result[entry.name] = {"start": f[19], "state": f[0]}
        except (OSError, IndexError, ValueError):
            continue
    return result


def directory(root, job_id, create=False):
    if not isinstance(job_id, str) or not ID.fullmatch(job_id):
        raise ValueError("Invalid task ID")
    path = root / "jobs" / job_id
    if not create and not path.exists():
        raise ValueError("Task does not exist")
    return private(path)


def load(root, job_id):
    path = directory(root, job_id) / "job.json"
    if path.is_symlink():
        raise ValueError("Unsafe task metadata")
    data = json.loads(path.read_text())
    if data["id"] != job_id or data["uid"] != os.getuid():
        raise ValueError("Task ownership mismatch")
    return data


def save(root, job):
    atomic(directory(root, job["id"]) / "job.json", job)


def session_file(root, session, project):
    key = hashlib.sha256((session + "\0" + project).encode()).hexdigest()
    return private(root / "sessions") / (key + ".json")


def gate(root, session, project):
    path = session_file(root, session, project)
    return json.loads(path.read_text()) if path.exists() else {"paused": False}


def scoped(job, session, project):
    if session is not None and (job["session"] != session or job["project"] != project):
        raise ValueError("Task belongs to a different session or project")


def view(root, job, include_command=True):
    result = dict(job)
    result.pop("members", None)
    if not include_command:
        result.pop("argv", None)
    log = directory(root, job["id"]) / "output.log"
    result["output_bytes"] = log.stat().st_size if log.exists() else 0
    result["terminal"] = job["state"] in TERMINAL
    if not result["terminal"] and job.get("worker_pid"):
        if stamp(job["worker_pid"]) != job.get("worker_start"):
            result["state"] = "orphaned"
            result["error"] = "Worker lost; never replay automatically. Inspect or stop this task."
    return result


def start(root, session, project, argv, request_id, timeout=3600, max_bytes=64 << 20, cwd=None):
    if not isinstance(session, str) or not session or len(session) > 256:
        raise ValueError("A session identity is required")
    if not isinstance(request_id, str) or not 0 < len(request_id) <= 128:
        raise ValueError("request_id must be a stable nonempty key, at most 128 characters")
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(x, str) or "\0" in x for x in argv)
    ):
        raise ValueError("argv must contain command arguments")
    if len(json.dumps(argv)) > 65536:
        raise ValueError("Command arguments exceed 64 KiB")
    if not math.isfinite(timeout) or not 0 < timeout <= 604800:
        raise ValueError("timeout must be positive and at most seven days")
    if not isinstance(max_bytes, int) or not 1024 <= max_bytes <= 1 << 30:
        raise ValueError("Output limit must be 1 KiB to 1 GiB")
    project = str(Path(project).resolve(strict=True))
    cwd = str((Path(project) / (cwd or ".")).resolve(strict=True))
    if not Path(cwd).is_dir():
        raise ValueError("Working directory is not a directory")
    with guard(root) as root:
        key = hashlib.sha256((session + "\0" + project + "\0" + request_id).encode()).hexdigest()
        index = private(root / "requests") / (key + ".json")
        if index.exists():
            old = json.loads(index.read_text())
            if old.get("removed"):
                raise ValueError("This request was removed; do not replay it with the same key")
            job = load(root, old["id"])
            if (job["argv"], job["cwd"], job["timeout"], job["max_bytes"]) != (
                argv,
                cwd,
                timeout,
                max_bytes,
            ):
                raise ValueError("request_id already identifies a different operation")
            return {**view(root, job), "reused": True}
        if gate(root, session, project)["paused"]:
            raise ValueError("Session is paused; explicitly resume before starting new work")
        live = [
            p
            for p in private(root / "jobs").glob("*/job.json")
            if json.loads(p.read_text())["state"] not in TERMINAL
        ]
        if len(live) >= 32:
            raise ValueError("At most 32 unfinished managed tasks are allowed per state root")
        job_id = "job_" + uuid.uuid4().hex
        folder = directory(root, job_id, create=True)
        job = {
            "schema": 1,
            "id": job_id,
            "uid": os.getuid(),
            "session": session,
            "project": project,
            "cwd": cwd,
            "argv": argv,
            "request_id": request_id,
            "request_key": key,
            "timeout": timeout,
            "max_bytes": max_bytes,
            "created": time.time(),
            "state": "queued",
            "control": None,
            "members": {},
        }
        save(root, job)
        atomic(index, {"id": job_id})
        child = None
        try:
            shutil.copy2(Path(__file__).resolve(), folder / "worker.py")
            with (folder / "worker.log").open("xb") as log:
                child = subprocess.Popen(
                    [sys.executable, str(folder / "worker.py"), "_worker", str(root), job_id],
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                )
            job.update(worker_pid=child.pid, worker_start=stamp(child.pid))
            save(root, job)
            threading.Thread(target=child.wait, daemon=True).start()
        except Exception as error:
            # The worker is still behind our state lock; stop it before it can launch work.
            if child is not None:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait(timeout=3)
            job.update(state="failed", error=str(error), ended=time.time())
            save(root, job)
            raise
        return view(root, job)


def signal_group(job, sig):
    current = members(job["pgid"])
    known = job.get("members", {})
    if not current:
        return
    if not any(
        pid in known and known[pid]["start"] == value["start"] for pid, value in current.items()
    ):
        raise RuntimeError("Process-group ownership cannot be verified; refusing to signal")
    with contextlib.suppress(ProcessLookupError):
        os.killpg(job["pgid"], sig)


def stop_orphaned(root, job):
    if view(root, job)["state"] != "orphaned":
        return False
    if not job.get("pgid"):
        raise ValueError("Lost worker has no verified command process group")
    signal_group(job, signal.SIGCONT)
    signal_group(job, signal.SIGKILL)
    job.update(
        state="stopping",
        stop_requested=True,
        error="Worker lost; inspect process exit before cleanup",
    )
    return True


def reconcile(root, job):
    if job["state"] not in TERMINAL and job.get("worker_pid"):
        if stamp(job["worker_pid"]) != job.get("worker_start"):
            current = members(job["pgid"]) if job.get("pgid") else {}
            if not any(v["state"] not in {"Z", "X"} for v in current.values()):
                job.update(
                    state="cancelled" if job.get("stop_requested") else "lost",
                    error="Worker lost; final exit/output may be incomplete; never replay automatically",
                    output_truncated=True,
                    ended=time.time(),
                )
                save(root, job)
    return job


def perform(root, action, session=None, project=None, job_id=None, offset=0, limit=16384, **args):
    root = Path(root).absolute()
    if project is not None:
        project = str(Path(project).resolve(strict=True))
    if action == "start":
        return start(root, session, project, **args)
    with guard(root) as root:
        if action == "gate":
            return gate(root, session, project)
        if action in {"pause_session", "resume_session", "stop_session"}:
            if not session or not project:
                raise ValueError("Session controls require an explicit session and project")
            paused = action != "resume_session"
            atomic(session_file(root, session, project), {"paused": paused, "updated": time.time()})
            selected = []
            for p in private(root / "jobs").glob("*/job.json"):
                job = reconcile(root, load(root, p.parent.name))
                if (
                    job["session"] != session
                    or job["project"] != project
                    or job["state"] in TERMINAL
                ):
                    continue
                if action == "stop_session" and stop_orphaned(root, job):
                    save(root, job)
                    selected.append(job["id"])
                    continue
                if view(root, job)["state"] == "orphaned":
                    raise ValueError("Lost worker; only verified stop is supported")
                if action == "resume_session" and job.get("pause_source") != "session":
                    continue
                if action == "pause_session" and job["state"] == "paused":
                    continue
                job["control"] = {
                    "pause_session": "pause",
                    "resume_session": "resume",
                    "stop_session": "stop",
                }[action]
                if action == "pause_session":
                    job["pause_source"] = "session"
                save(root, job)
                selected.append(job["id"])
            return {
                "session": session,
                "paused": paused,
                "requested_tasks": selected,
                "state": "control_requested",
            }
        if action == "list":
            jobs = []
            for p in private(root / "jobs").glob("*/job.json"):
                job = reconcile(root, load(root, p.parent.name))
                if session is None or (job["session"] == session and job["project"] == project):
                    jobs.append(view(root, job, False))
            return sorted(jobs, key=lambda x: x["created"], reverse=True)[:100]
        job = reconcile(root, load(root, job_id))
        scoped(job, session, project)
        if action == "status":
            return view(root, job)
        if action == "output":
            if (
                not isinstance(offset, int)
                or offset < 0
                or not isinstance(limit, int)
                or not 1 <= limit <= 65536
            ):
                raise ValueError("offset must be nonnegative and limit must be 1..65536")
            log = directory(root, job_id) / "output.log"
            size = log.stat().st_size if log.exists() else 0
            if offset > size:
                raise ValueError("Output cursor is beyond available bytes")
            data = b""
            if log.exists():
                with log.open("rb") as stream:
                    stream.seek(offset)
                    data = stream.read(limit)
            return {
                "id": job_id,
                "state": view(root, job)["state"],
                "offset": offset,
                "next_offset": offset + len(data),
                "total_bytes": size,
                "text": data.decode(errors="replace"),
                "data_base64": base64.b64encode(data).decode(),
                "all_output_delivered": job["state"] in TERMINAL and offset + len(data) == size,
                "truncated": job.get("output_truncated", False),
            }
        if action == "remove":
            if job["state"] not in TERMINAL:
                raise ValueError("Only terminal tasks can be removed")
            atomic(
                root / "requests" / (job["request_key"] + ".json"), {"id": job_id, "removed": True}
            )
            shutil.rmtree(directory(root, job_id))
            return {"id": job_id, "state": "removed"}
        if action not in {"pause", "resume", "stop"}:
            raise ValueError("Unknown managed task action")
        if job["state"] in TERMINAL:
            return view(root, job)
        if action == "resume" and gate(root, job["session"], job["project"])["paused"]:
            raise ValueError("Resume the session before resuming an individual task")
        if view(root, job)["state"] == "orphaned":
            if action != "stop" or not job.get("pgid"):
                raise ValueError("Lost worker; only verified stop is supported")
            stop_orphaned(root, job)
        else:
            job["control"] = action
            if action == "pause":
                job["pause_source"] = "task"
        save(root, job)
        return {**view(root, job), "control_requested": action}


def worker(root, job_id):
    """Only this detached worker owns/waits for its command process group."""
    child = None
    ending = None
    stop_at = None
    try:
        queued_deadline = time.monotonic()
        while True:
            with guard(root) as root:
                job = load(root, job_id)
                if job["state"] in TERMINAL:
                    return
                job.update(worker_pid=os.getpid(), worker_start=stamp(os.getpid()))
                if (
                    job.get("control") == "stop"
                    or time.monotonic() - queued_deadline >= job["timeout"]
                ):
                    job.update(
                        state="cancelled" if job.get("control") == "stop" else "timed_out",
                        ended=time.time(),
                        control=None,
                        exit_code=None,
                    )
                    save(root, job)
                    return
                held = gate(root, job["session"], job["project"])["paused"]
                if job.get("control") == "resume":
                    job["state"] = "queued"
                    job["control"] = None
                if job.get("control") == "pause" or held or job["state"] == "paused":
                    job.update(state="paused", control=None)
                    save(root, job)
                else:
                    child = subprocess.Popen(
                        job["argv"],
                        cwd=job["cwd"],
                        stdin=subprocess.DEVNULL,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        start_new_session=True,
                    )
                    # Retain a leader identity even if the first /proc group scan fails.
                    job.update(
                        pgid=child.pid,
                        child_pid=child.pid,
                        members={str(child.pid): {"start": stamp(child.pid), "state": "R"}},
                    )
                    job.update(
                        state="running",
                        started=time.time(),
                        pgid=child.pid,
                        child_pid=child.pid,
                        members=members(child.pid),
                    )
                    save(root, job)
                    break
            time.sleep(0.05)
        deadline = queued_deadline + job["timeout"]
        written = 0
        with (directory(root, job_id) / "output.log").open("xb") as log:
            os.chmod(log.name, 0o600)
            with selectors.DefaultSelector() as selector:
                selector.register(child.stdout, selectors.EVENT_READ)
                while True:
                    for key, _ in selector.select(timeout=0.05):
                        data = os.read(key.fileobj.fileno(), 65536)
                        if not data:
                            selector.unregister(key.fileobj)
                            continue
                        remaining = job["max_bytes"] - written
                        log.write(data[:remaining])
                        log.flush()
                        written += min(len(data), remaining)
                        if len(data) > remaining:
                            ending = "output_limit"
                    with guard(root):
                        job = load(root, job_id)
                        current = members(child.pid)
                        # A known member must anchor every signal; never trust a reused PID.
                        if current:
                            if job["members"] and not any(
                                pid in job["members"] and job["members"][pid]["start"] == v["start"]
                                for pid, v in current.items()
                            ):
                                raise RuntimeError(
                                    "Lost process-group identity; refusing to signal"
                                )
                            job["members"] = current
                        live = [v for v in current.values() if v["state"] not in {"Z", "X"}]
                        control = job.pop("control", None)
                        if control == "stop":
                            ending = "cancelled"
                        if time.monotonic() >= deadline and ending is None:
                            ending = "timed_out"
                        if ending and live:
                            if stop_at is None:
                                signal_group(job, signal.SIGTERM)
                                signal_group(job, signal.SIGCONT)
                                stop_at = time.monotonic()
                            elif time.monotonic() - stop_at >= 1:
                                signal_group(job, signal.SIGKILL)
                            job["state"] = "stopping"
                        elif (
                            control == "pause"
                            or (job["state"] == "pausing" and control != "resume")
                        ) and live:
                            signal_group(job, signal.SIGSTOP)
                            stopped = members(job["pgid"])
                            job["state"] = (
                                "paused"
                                if all(v["state"] in {"T", "t", "Z", "X"} for v in stopped.values())
                                else "pausing"
                            )
                        elif control == "resume" and live:
                            signal_group(job, signal.SIGCONT)
                            job["state"] = "running"
                            job.pop("pause_source", None)
                        job["output_bytes"] = written
                        save(root, job)
                    code = child.poll()
                    if code is not None and not live and not selector.get_map():
                        break
                log.flush()
                os.fsync(log.fileno())
        with guard(root):
            job = load(root, job_id)
            job.update(
                state=ending or ("completed" if code == 0 else "failed"),
                exit_code=code,
                ended=time.time(),
                control=None,
                output_truncated=ending == "output_limit",
                members={},
            )
            save(root, job)
    except BaseException as error:
        # Keep the in-memory ownership proof if metadata persistence itself failed.
        owned = dict(job) if child is not None else None
        if owned:
            with contextlib.suppress(ProcessLookupError, RuntimeError):
                signal_group(owned, signal.SIGCONT)
                signal_group(owned, signal.SIGKILL)
            with contextlib.suppress(subprocess.TimeoutExpired):
                child.wait(timeout=3)
        with guard(root):
            persisted = load(root, job_id)
            if owned:
                for name in ["pgid", "child_pid", "members"]:
                    if name in owned:
                        persisted[name] = owned[name]
            live = members(persisted["pgid"]) if persisted.get("pgid") else {}
            persisted.update(
                state="orphaned"
                if any(v["state"] not in {"Z", "X"} for v in live.values())
                else "failed",
                error=type(error).__name__ + ": " + str(error),
                output_truncated=True,
                ended=time.time(),
            )
            save(root, persisted)
        raise
    finally:
        if child is not None:
            if child.poll() is not None:
                child.wait()
            if child.stdout:
                child.stdout.close()


def rpc():
    try:
        request = json.loads(sys.stdin.read(1 << 20))
        result = perform(Path(sys.argv[2]), **request)
        print(json.dumps({"ok": True, "result": result}), flush=True)
        return 0
    except Exception as error:
        print(
            json.dumps({"ok": False, "error": type(error).__name__ + ": " + str(error)}), flush=True
        )
        return 1


if __name__ == "__main__":
    if len(sys.argv) == 4 and sys.argv[1] == "_worker":
        worker(Path(sys.argv[2]), sys.argv[3])
    elif len(sys.argv) == 3 and sys.argv[1] == "_rpc":
        raise SystemExit(rpc())
    else:
        raise SystemExit("Use local-ai client job --help")
