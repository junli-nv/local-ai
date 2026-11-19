"""Explicit SSH, Slurm and container ownership; uncertain submissions are never replayed."""

import base64
import hashlib
import json
import math
import os
import re
import shlex
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

from . import execution as e

HOST = re.compile(r"[A-Za-z0-9_][A-Za-z0-9_.@:\[\]-]{0,250}\Z")


def run(argv, host=None, payload=None, limit=64 << 20):
    if host:
        if not HOST.fullmatch(host):
            raise ValueError("Invalid SSH target")
        argv = [
            "ssh",
            "-oBatchMode=yes",
            "-oConnectTimeout=5",
            "--",
            host,
            "umask 077; exec " + shlex.join(argv),
        ]
    with tempfile.TemporaryFile() as out, tempfile.TemporaryFile() as err:
        result = subprocess.run(argv, input=payload, stdout=out, stderr=err, timeout=8, umask=0o077)
        out.seek(0)
        data = out.read(limit + 1)
        err.seek(0)
        error = err.read(8192)
    if len(data) > limit:
        raise ValueError("Adapter output exceeds capture limit; output is incomplete")
    if result.returncode:
        raise RuntimeError(
            "Adapter command failed ("
            + str(result.returncode)
            + "): "
            + error.decode(errors="replace")
        )
    return data


# The remote helper only operates inside a private per-controller namespace.
BOOTSTRAP = """
import base64,hashlib,importlib.util,json,os,pathlib,sys,tempfile
q=json.load(sys.stdin)
root=pathlib.Path.home()/".local/state/local-ai-remote"/q["namespace"]
root.mkdir(parents=True,exist_ok=True,mode=0o700)
st=root.lstat()
if root.is_symlink() or st.st_uid!=os.getuid() or st.st_mode&0o077:
 raise RuntimeError("Unsafe remote task root")
source=base64.b64decode(q["engine"])
name=root/("agent-"+hashlib.sha256(source).hexdigest()+".py")
if not name.exists():
 fd,pending=tempfile.mkstemp(prefix=".agent-",dir=root)
 try:
  with os.fdopen(fd,"wb") as f:f.write(source);f.flush();os.fsync(f.fileno())
  try:os.link(pending,name)
  except FileExistsError:pass
 finally:os.unlink(pending)
spec=importlib.util.spec_from_file_location("remote_engine",name)
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
r=q["request"]
if r["action"] in {"find","proxy"}:
 project=str(pathlib.Path(r["project"]).resolve())
 key=hashlib.sha256((r["session"]+"\\0"+project+"\\0"+r["request_id"]).encode()).hexdigest()
 index=root/"requests"/(key+".json")
 result=None
 if index.exists():
  identity=json.loads(index.read_text())["id"]
  if r["action"]=="proxy":
   before=m.perform(root,"status",job_id=identity)
   answer=m.perform(root,r["operation"],job_id=identity,**r.get("arguments",{}))
   if r.get("return_output"):
    answer=m.perform(root,"output",job_id=identity,**r["output_arguments"])
   result={"job":before if r["operation"]=="remove" else m.perform(root,"status",job_id=identity),"result":answer}
  else:
   result=m.perform(root,"status",job_id=identity)
else:
 result=m.perform(root,**r)
print(json.dumps(result))
"""


def ssh_request(root, job, request):
    namespace = hashlib.sha256(
        (str(root.resolve()) + ":" + str(os.getuid()) + ":" + os.uname().nodename).encode()
    ).hexdigest()[:32]
    payload = json.dumps(
        {
            "namespace": namespace,
            "engine": base64.b64encode(Path(e.__file__).read_bytes()).decode(),
            "request": request,
        }
    ).encode()
    return json.loads(run(["python3", "-c", BOOTSTRAP], host=job["host"], payload=payload))


def start(
    root,
    session,
    project,
    argv,
    request_id,
    adapter,
    host=None,
    remote_project=None,
    image=None,
    submit_args=None,
    timeout=3600,
    cwd=None,
    interactive=False,
    notify=True,
    **unused,
):
    if adapter not in {"ssh", "slurm", "container"}:
        raise ValueError("Unknown task adapter")
    if (
        not isinstance(request_id, str)
        or not 0 < len(request_id) <= 128
        or not isinstance(session, str)
        or not session
    ):
        raise ValueError("Adapter start requires session and stable request_id")
    if (
        not isinstance(argv, list)
        or not argv
        or any(not isinstance(a, str) or "\0" in a for a in argv)
    ):
        raise ValueError("argv must be an argument array")
    if not math.isfinite(timeout) or not 0 < timeout <= 604800 or interactive:
        raise ValueError("Adapter timeout must be 0..604800 seconds; remote PTYs are unsupported")
    if host and not HOST.fullmatch(host):
        raise ValueError("Invalid SSH target")
    if adapter == "ssh" and not host:
        raise ValueError("SSH tasks require --host")
    if adapter == "container" and (
        not image or image.startswith("-") or any(x.isspace() for x in image)
    ):
        raise ValueError("Container tasks require a prepared image")
    submit_args = submit_args or []
    if any(
        not re.fullmatch(
            r"--(?:partition|account|qos|constraint|cpus-per-task|mem|gres)=[A-Za-z0-9_.,:@/+:-]+",
            a,
        )
        for a in submit_args
    ):
        raise ValueError("Unsupported Slurm resource option")
    project = str(Path(project).resolve(strict=True))
    destination = remote_project or (str(Path(cwd).resolve()) if cwd else project)
    if not destination.startswith("/") or "\0" in destination:
        raise ValueError("Adapter working directory must be absolute")
    spec = {
        "adapter": adapter,
        "host": host,
        "remote_project": destination,
        "image": image,
        "submit_args": submit_args,
        "argv": argv,
        "timeout": timeout,
    }
    with e.guard(root) as root:
        key = hashlib.sha256((session + "\0" + project + "\0" + request_id).encode()).hexdigest()
        index = e.private(root / "requests") / (key + ".json")
        if index.exists():
            old = json.loads(index.read_text())
            if old.get("removed"):
                raise ValueError("Removed operation cannot be replayed")
            job = e.load(root, old["id"])
            if job.get("spec") != spec:
                raise ValueError("request_id identifies a different operation")
            return {**e.view(root, job), "reused": True}
        if e.gate(root, session, project)["paused"]:
            raise ValueError("Session paused")
        if (
            sum(
                json.loads(p.read_text())["state"] not in e.TERMINAL
                for p in e.private(root / "jobs").glob("*/job.json")
            )
            >= 32
        ):
            raise ValueError("At most 32 unfinished tasks are allowed")
        job_id = "job_" + uuid.uuid4().hex
        e.directory(root, job_id, create=True)
        job = {
            **spec,
            "spec": spec,
            "schema": 1,
            "id": job_id,
            "uid": os.getuid(),
            "session": session,
            "project": project,
            "cwd": project,
            "request_id": request_id,
            "request_key": key,
            "state": "submitting",
            "created": time.time(),
            "members": {},
            "notify": notify,
            "name": "lai-" + job_id[4:],
            "owner": hashlib.sha256(str(root).encode()).hexdigest()[:20],
        }
        e.save(root, job)
        e.atomic(index, {"id": job_id})
    spawn_monitor(root, job)
    return e.view(root, job)


def submit_once(root, job):
    with e.guard(root):
        job = e.load(root, job["id"])
        if job.get("submission_attempted"):
            return
        if job.get("control") == "stop":
            job.update(state="cancelled", ended=time.time(), exit_code=None, control=None)
            e.save(root, job)
            return
        held = (
            e.gate(root, job["session"], job["project"])["paused"]
            or job.get("control") == "pause"
            or (job["state"] == "paused" and job.get("control") != "resume")
        )
        if held:
            job.update(state="paused", control=None)
            e.save(root, job)
            return
        job["submission_attempted"] = True
        e.save(root, job)
    adapter, host = job["adapter"], job["host"]
    destination, image = job["remote_project"], job["image"]
    argv, submit_args, timeout = job["argv"], job["submit_args"], job["timeout"]
    job_id = job["id"]
    try:
        if adapter == "ssh":
            remote = ssh_request(
                root,
                job,
                {
                    "action": "start",
                    "session": job_id,
                    "project": destination,
                    "argv": argv,
                    "request_id": job_id,
                    "timeout": timeout,
                    "notify": False,
                },
            )
            job["remote_id"] = remote["id"]
        elif adapter == "slurm":
            uid = run(["id", "-u"], host).decode().strip() if host else str(os.getuid())
            if not uid.isdigit():
                raise RuntimeError("Cannot verify Slurm submitter UID")
            job["owner_uid"] = uid
            path = destination + "/." + job["name"] + ".out"
            job["log_path"] = path
            store(root, job)
            raw = (
                run(
                    [
                        "sbatch",
                        "--parsable",
                        "--job-name=" + job["name"],
                        "--chdir=" + destination,
                        "--output=" + path,
                        "--error=" + path,
                        "--time=" + str(max(1, math.ceil(timeout / 60))),
                        "--cpus-per-task=1",
                        *submit_args,
                        "--wrap",
                        shlex.join(argv),
                    ],
                    host,
                )
                .decode()
                .strip()
                .split(";")[0]
            )
            if not re.fullmatch(r"[0-9]+", raw):
                raise RuntimeError("Invalid sbatch identity")
            job["scheduler_id"] = raw
        else:
            raw = (
                run(
                    [
                        "docker",
                        "run",
                        "-d",
                        "--pull=never",
                        "-e",
                        "NVIDIA_VISIBLE_DEVICES=void",
                        "--name",
                        job["name"],
                        "--label",
                        "io.local-ai.job=" + job_id,
                        "--label",
                        "io.local-ai.owner=" + job["owner"],
                        "--entrypoint",
                        argv[0],
                        image,
                        *argv[1:],
                    ],
                    host,
                )
                .decode()
                .strip()
            )
            if not re.fullmatch(r"[a-f0-9]{64}", raw):
                raise RuntimeError("Invalid container identity")
            job["container_id"] = raw
        job.update(state="queued", updated=time.time())
        store(root, job)
        return e.view(root, job)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        job.update(state="unreachable", error=str(error), updated=time.time(), uncertain=True)
        store(root, job)
        return e.view(root, job)


def container_info(job):
    rows = json.loads(
        run(["docker", "inspect", job.get("container_id") or job["name"]], job["host"])
    )
    if len(rows) != 1:
        raise RuntimeError("Container identity is not unique")
    row = rows[0]
    labels = row.get("Config", {}).get("Labels") or {}
    if (
        labels.get("io.local-ai.job") != job["id"]
        or labels.get("io.local-ai.owner") != job["owner"]
    ):
        raise RuntimeError("Container ownership labels do not match")
    if job.get("container_id") and row["Id"] != job["container_id"]:
        raise RuntimeError("Container ID changed")
    job["container_id"] = row["Id"]
    return row


def slurm_info(job):
    host = job["host"]
    identity = job.get("scheduler_id")
    if not identity:
        candidates = run(["squeue", "-h", "--name", job["name"], "-o", "%A"], host).decode().split()
        if len(candidates) == 1 and candidates[0].isdigit():
            identity = candidates[0]
            job["scheduler_id"] = identity
        elif candidates:
            raise RuntimeError("Scheduler identity is ambiguous")
    if identity:
        try:
            text = run(["scontrol", "show", "job", "-o", identity], host).decode()
            fields = dict(re.findall(r"(\w+)=([^ ]+)", text))
            owner = re.search(r"\(([0-9]+)\)", fields.get("UserId", ""))
            if (
                fields.get("JobName") != job["name"]
                or fields.get("JobId") != identity
                or not owner
                or owner.group(1) != job.get("owner_uid")
            ):
                raise RuntimeError("Slurm job identity changed")
            return fields.get("JobState", "UNKNOWN"), fields.get("ExitCode", "0:0")
        except RuntimeError as error:
            if "identity changed" in str(error):
                raise
    since = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(job["created"] - 120))
    argv = ["sacct", "-n", "-P", "-S", since, "--format=JobIDRaw,State,ExitCode,JobName%80,UID"]
    argv += ["-j", identity] if identity else ["--name", job["name"]]
    rows = [r.strip().split("|") for r in run(argv, host).decode().splitlines() if r.strip()]
    rows = [
        r
        for r in rows
        if len(r) >= 5
        and r[0].isdigit()
        and r[3].strip() == job["name"]
        and r[4].strip() == job.get("owner_uid")
    ]
    if identity:
        rows = [r for r in rows if r[0] == identity]
    if len(rows) != 1:
        raise RuntimeError("No unique Slurm accounting record; completion is unknown")
    job["scheduler_id"] = rows[0][0]
    return rows[0][1].split()[0].rstrip("+"), rows[0][2]


def update_state(job):
    adapter = job["adapter"]
    if adapter == "container":
        row = container_info(job)
        state = row["State"]
        if state.get("Running"):
            job["state"] = "paused" if state.get("Paused") else "running"
        elif state.get("Status") in {"exited", "dead"}:
            code = state.get("ExitCode")
            job.update(
                state=job.get("ending") or ("completed" if code == 0 else "failed"),
                exit_code=code,
                ended=time.time(),
            )
        else:
            job["state"] = "queued" if state.get("Status") == "created" else "unknown"
    elif adapter == "slurm":
        state, code = slurm_info(job)
        mapping = {
            "COMPLETED": "completed",
            "CANCELLED": "cancelled",
            "FAILED": "failed",
            "TIMEOUT": "timed_out",
            "OUT_OF_MEMORY": "failed",
            "NODE_FAIL": "failed",
            "PREEMPTED": "failed",
            "BOOT_FAIL": "failed",
            "SUSPENDED": "paused",
            "RUNNING": "running",
            "PENDING": "queued",
            "CONFIGURING": "queued",
            "COMPLETING": "stopping",
        }
        job["state"] = mapping.get(state, "unknown")
        job["scheduler_state"] = state
        if job["state"] in e.TERMINAL:
            parts = code.split(":")
            job["exit_code"] = int(parts[0]) or (
                128 + int(parts[1]) if len(parts) > 1 and int(parts[1]) else 0
            )
            if job["state"] == "completed" and job["exit_code"]:
                job["state"] = "failed"
            job["ended"] = time.time()


def control_external(job, action):
    if job["adapter"] == "container":
        row = container_info(job)
        if action == "stop" and not row["State"].get("Running"):
            return
        if action == "stop" and row["State"].get("Paused"):
            run(["docker", "unpause", job["container_id"]], job["host"])
        operation = {"pause": ["pause"], "resume": ["unpause"], "stop": ["stop", "-t", "1"]}[action]
        if action == "resume" and row["State"].get("Status") == "created":
            operation = ["start"]
        run(["docker", *operation, job["container_id"]], job["host"])
    else:
        state, _ = slurm_info(job)
        if state in {"COMPLETED", "CANCELLED", "FAILED", "TIMEOUT", "OUT_OF_MEMORY", "NODE_FAIL"}:
            return
        argv = (
            ["scancel", job["scheduler_id"]]
            if action == "stop"
            else ["scontrol", "suspend" if action == "pause" else "resume", job["scheduler_id"]]
        )
        run(argv, job["host"])


def log_page(root, job, offset, limit):
    if (
        not isinstance(offset, int)
        or offset < 0
        or not isinstance(limit, int)
        or not 1 <= limit <= 65536
    ):
        raise ValueError("Output offset/limit are invalid")
    if job["adapter"] == "container":
        log = e.directory(root, job["id"]) / "output.log"
        # Docker writes container stderr to its own stderr; merge both descriptors.
        argv = ["docker", "logs", job["container_id"]]
        if job["host"]:
            argv = [
                "ssh",
                "-oBatchMode=yes",
                "-oConnectTimeout=5",
                "--",
                job["host"],
                "exec " + shlex.join(argv),
            ]
        with tempfile.TemporaryFile() as stream:
            response = subprocess.run(argv, stdout=stream, stderr=stream, timeout=8)
            stream.seek(0)
            data = stream.read((64 << 20) + 1)
        if response.returncode:
            raise RuntimeError("Container logs unavailable")
        if len(data) > 64 << 20:
            job["output_truncated"] = True
            data = data[: 64 << 20]
        previous = log.read_bytes() if log.exists() else b""
        if not data.startswith(previous):
            job["output_truncated"] = True
            raise RuntimeError("Container log rotation changed the output prefix; coverage gap")
        log.write_bytes(data)
        log.chmod(0o600)
        size = len(data)
        block = data[offset : offset + limit]
    else:
        path = job.get("log_path")
        if not path:
            raise RuntimeError("Slurm output path is unknown")
        if job["host"]:
            code = (
                "import base64,json,pathlib,sys;p=pathlib.Path(sys.argv[1]);"
                "s=p.stat().st_size if p.exists() else 0;"
                "f=p.open('rb') if p.exists() else None;"
                "f.seek(int(sys.argv[2])) if f else None;"
                "b=f.read(int(sys.argv[3])) if f else b'';"
                "print(json.dumps({'size':s,'exists':p.exists(),'data':base64.b64encode(b).decode()}))"
            )
            value = json.loads(
                run(["python3", "-c", code, path, str(offset), str(limit)], job["host"])
            )
            size, block = value["size"], base64.b64decode(value["data"])
            exists = value["exists"]
        else:
            path = Path(path)
            exists = path.exists()
            size = path.stat().st_size if exists else 0
            block = b""
            if exists:
                with path.open("rb") as stream:
                    stream.seek(offset)
                    block = stream.read(limit)
        if not exists and job["state"] in e.TERMINAL:
            job["output_truncated"] = True
    if offset > size:
        raise ValueError("Output cursor exceeds available bytes")
    job["output_bytes"] = size
    return {
        "id": job["id"],
        "state": job["state"],
        "offset": offset,
        "next_offset": offset + len(block),
        "total_bytes": size,
        "text": block.decode(errors="replace"),
        "data_base64": base64.b64encode(block).decode(),
        "all_output_delivered": job["state"] in e.TERMINAL and offset + len(block) == size,
        "truncated": job.get("output_truncated", False),
    }


def store(root, job, original_control=None, control_applied=False):
    protected = {
        "control",
        "notification",
        "notify",
        "pause_source",
        "controller_pid",
        "controller_start",
    }
    with e.guard(root):
        current = e.load(root, job["id"])
        current.update({k: v for k, v in job.items() if k not in protected})
        if "error" not in job:
            current.pop("error", None)
        if control_applied and current.get("control") == original_control:
            current["control"] = None
        e.save(root, current)
    return current


def operate(root, action, job, offset=0, limit=16384, **args):
    import fcntl

    lock = e.directory(root, job["id"]) / ".adapter.lock"
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        job = e.load(root, job["id"])
        if action not in {"status", "output", "pause", "resume", "stop", "remove"}:
            raise ValueError("Unsupported adapter operation")
        if action == "resume" and e.gate(root, job["session"], job["project"])["paused"]:
            raise ValueError("Resume the session before resuming this task")
        original_control = job.get("control")
        requested = action if action in {"pause", "resume", "stop"} else original_control
        applied = False
        if requested:
            if requested == "stop":
                job["ending"] = "cancelled"
            with e.guard(root):
                current = e.load(root, job["id"])
                current["control"] = requested
                if requested == "stop":
                    current["ending"] = "cancelled"
                e.save(root, current)
            original_control = requested
        try:
            if job["adapter"] == "ssh":
                operation = requested or ("output" if action == "output" else "status")
                answer = ssh_request(
                    root,
                    job,
                    {
                        "action": "proxy",
                        "session": job["id"],
                        "project": job["remote_project"],
                        "request_id": job["id"],
                        "operation": operation,
                        "return_output": action == "output" and operation != "output",
                        "output_arguments": {"offset": offset, "limit": limit},
                        "arguments": {"offset": offset, "limit": limit}
                        if operation == "output"
                        else {},
                    },
                )
                if answer is None:
                    raise RuntimeError(
                        "Remote submission not yet located; never replay automatically"
                    )
                remote = answer["job"]
                job["remote_id"] = remote["id"]
                for key in ["state", "exit_code", "ended", "output_bytes", "output_truncated"]:
                    if key in remote:
                        job[key] = remote[key]
                applied = bool(requested)
                value = answer["result"] if action == "output" else None
                if value is not None:
                    value = {**value, "id": job["id"]}
            else:
                update_state(job)
                if (
                    job["state"] not in e.TERMINAL
                    and time.time() - job["created"] >= job["timeout"]
                ):
                    requested = "stop"
                    job["ending"] = "timed_out"
                if requested and job["state"] not in e.TERMINAL:
                    control_external(job, requested)
                    update_state(job)
                    applied = True
                value = log_page(root, job, offset, limit) if action == "output" else None
            job.update(updated=time.time(), uncertain=False)
            job.pop("error", None)
            if action == "remove":
                if job["state"] not in e.TERMINAL:
                    raise ValueError("Only verified terminal jobs can be removed")
                if job["adapter"] == "ssh":
                    ssh_request(
                        root,
                        job,
                        {
                            "action": "proxy",
                            "session": job["id"],
                            "project": job["remote_project"],
                            "request_id": job["id"],
                            "operation": "remove",
                        },
                    )
                elif job["adapter"] == "container":
                    container_info(job)
                    run(["docker", "rm", job["container_id"]], job["host"])
                return e.perform(root, "remove", job_id=job["id"], _adapter_skip=True)
            job = store(root, job, original_control, applied)
            return (
                value
                if value is not None
                else {**e.view(root, job), "control_requested": requested}
            )
        except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
            job.update(state="unreachable", error=str(error), uncertain=True, updated=time.time())
            store(root, job)
            if action in {"output", "remove"}:
                raise
            return e.view(root, job)


def spawn_monitor(root, job):
    import threading

    folder = e.directory(root, job["id"]) / "controller"
    package = e.private(folder / "local_ai")
    (package / "__init__.py").write_text("")
    for name in ["execution.py", "adapters.py"]:
        (package / name).write_bytes(Path(__file__).with_name(name).read_bytes())
    runner = folder / "watch.py"
    runner.write_text(
        "import sys\nfrom pathlib import Path\nfrom local_ai import adapters as a\n"
        "a.monitor(Path(sys.argv[1]),sys.argv[2])\n"
    )
    with e.guard(root):
        with (folder / "controller.log").open("ab") as log:
            child = subprocess.Popen(
                [sys.executable, str(runner), str(root), job["id"]],
                stdin=subprocess.DEVNULL,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        current = e.load(root, job["id"])
        try:
            current.update(controller_pid=child.pid, controller_start=e.stamp(child.pid))
            e.save(root, current)
        except BaseException:
            child.kill()
            child.wait()
            raise
        threading.Thread(target=child.wait, daemon=True).start()


def monitor(root, identity):
    while True:
        with e.guard(root):
            job = e.load(root, identity)
            if job["state"] in e.TERMINAL:
                return
            pending = not job.get("submission_attempted")
            if pending:
                if job.get("control") == "stop" or time.time() - job["created"] >= job["timeout"]:
                    job.update(
                        state="cancelled" if job.get("control") == "stop" else "timed_out",
                        ended=time.time(),
                        exit_code=None,
                        control=None,
                    )
                    e.save(root, job)
                    return
                paused = e.gate(root, job["session"], job["project"])["paused"]
                held = (
                    paused
                    or job.get("control") == "pause"
                    or (job["state"] == "paused" and job.get("control") != "resume")
                )
                if held:
                    job.update(state="paused", control=None)
                    e.save(root, job)
        if pending:
            if held:
                time.sleep(0.1)
                continue
            submit_once(root, job)
            if not e.load(root, identity).get("submission_attempted"):
                continue
        value = operate(root, "status", e.load(root, identity))
        if value["terminal"] or time.time() - job["created"] > job["timeout"] + 30:
            return
        time.sleep(2)
