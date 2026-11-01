"""One append-only installation journal; importing it has no side effects."""

import contextlib
import datetime
import fcntl
import os
import platform
import selectors
import shlex
import socket
import stat
import subprocess
import sys
import time
import traceback
import uuid
from pathlib import Path

_current = None


class Journal:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if self.path.exists() and not self.path.is_file():
            raise ValueError("Installation log must be a regular file: " + str(self.path))
        fd = os.open(
            self.path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK, 0o600
        )
        try:
            if not stat.S_ISREG(os.fstat(fd).st_mode):
                raise ValueError("Installation log must be a regular file")
            os.fchmod(fd, 0o600)
            self.stream = os.fdopen(fd, "a", buffering=1)
        except BaseException:
            os.close(fd)
            raise
        self.identifier = uuid.uuid4().hex[:8]
        self.step = 0

    def write(self, message, level="INFO", console=True):
        stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        lines = str(message).replace("\r", "\n").splitlines() or [""]
        text = "".join(f"{stamp} [{self.identifier}] {level} {line}\n" for line in lines)
        fcntl.flock(self.stream, fcntl.LOCK_EX)
        try:
            self.stream.write(text)
            self.stream.flush()
        finally:
            fcntl.flock(self.stream, fcntl.LOCK_UN)
        if console:
            summary = lines[0]
            if len(summary) > 240:
                summary = summary[:240] + "... (full command/output in installation log)"
            print(f"{level}: [{self.identifier}] {summary}", file=sys.stderr, flush=True)


def active():
    return _current is not None


def path():
    return _current.path if _current else None


def event(message, level="INFO"):
    if _current:
        _current.write(message, level)


@contextlib.contextmanager
def session(options):
    global _current
    group, action = options.group, getattr(options, "action", None)
    enabled = (
        (group == "image")
        or (group == "model")
        or (group == "client" and action in {"install", "export"})
        or (group == "server" and action == "start")
    )
    if not enabled:
        yield
        return
    root = getattr(options, "data_dir", None) or getattr(options, "client_dir", None)
    logfile = options.install_log or Path(root) / "install.log"
    journal = Journal(logfile)
    previous, _current = _current, journal
    started = time.monotonic()
    try:
        journal.write(f"BEGIN {group} {action}; installation log={journal.path}")
        journal.write(
            f"host={socket.gethostname()} user_uid={os.getuid()} "
            f"platform={platform.platform()} architecture={platform.machine()} "
            f"python={platform.python_version()} cwd={Path.cwd()}"
        )
        for key, value in vars(options).items():
            if value is not None:
                journal.write(f"OPTION {key}={value}", console=False)
        yield
    except BaseException as error:
        journal.write(
            f"FAIL {group} {action}; elapsed={time.monotonic() - started:.2f}s; {error}", "ERROR"
        )
        journal.write(traceback.format_exc(), "TRACEBACK", console=False)
        journal.write(
            f"Inspect the failed command and error summary. Complete installation log: {journal.path}",
            "ERROR",
        )
        if group == "server":
            journal.write(
                f"Model loading output: {Path(root) / 'instances' / options.name / 'server.log'}",
                "ERROR",
            )
        raise
    else:
        journal.write(f"DONE {group} {action}; elapsed={time.monotonic() - started:.2f}s; exit=0")
    finally:
        _current = previous
        journal.stream.close()


def artifact_progress(command):
    if "--output" not in command:
        return ""
    position = command.index("--output") + 1
    if position >= len(command):
        return ""
    target = Path(command[position])
    try:
        candidates = [target, *target.parent.glob(".tmp-" + target.name + "*")]
        snapshots = []
        for candidate in candidates:
            try:
                info = candidate.stat()
            except OSError:
                continue
            if stat.S_ISREG(info.st_mode):
                snapshots.append((info.st_mtime, str(candidate), info.st_size))
        if snapshots:
            _, name, size = max(snapshots)
            return "; output_file=%s; output_bytes=%d" % (name, size)
    except OSError:
        return "; output_progress=temporarily_unavailable"
    return "; output_file_pending=" + str(target)


def run(command, timeout=30, probe=False, **kwargs):
    """Capture each stream for callers while journaling it live."""
    journal = _current
    journal.step += 1
    step = journal.step
    started = heartbeat = time.monotonic()
    rendered = shlex.join([str(x) for x in command])
    journal.write(f"STEP {step} START command={rendered}; timeout={timeout}")
    quiet_output = str(command[0]) == "docker" and "inspect" in command[:3]
    buffers = {"stdout": bytearray(), "stderr": bytearray()}
    try:
        process = subprocess.Popen(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE, **kwargs
        )
    except OSError as error:
        journal.write(f"STEP {step} FAIL launching command: {error}", "ERROR")
        raise
    try:
        with selectors.DefaultSelector() as selector:
            selector.register(process.stdout, selectors.EVENT_READ, "stdout")
            selector.register(process.stderr, selectors.EVENT_READ, "stderr")
            while selector.get_map():
                now = time.monotonic()
                if timeout is not None and now - started > timeout:
                    process.kill()
                    extra_out, extra_err = process.communicate()
                    buffers["stdout"].extend(extra_out)
                    buffers["stderr"].extend(extra_err)
                    raise subprocess.TimeoutExpired(
                        command, timeout, bytes(buffers["stdout"]), bytes(buffers["stderr"])
                    )
                for key, _ in selector.select(timeout=0.5):
                    chunk = os.read(key.fileobj.fileno(), 8192)
                    if not chunk:
                        selector.unregister(key.fileobj)
                        continue
                    buffers[key.data].extend(chunk)
                    if not (quiet_output and key.data == "stdout"):
                        journal.write(
                            chunk.decode("utf-8", errors="replace"), key.data.upper(), console=False
                        )
                if now - heartbeat >= 15:
                    journal.write(
                        f"STEP {step} RUNNING elapsed={now - started:.1f}s; stdout_bytes={len(buffers['stdout'])}; stderr_bytes={len(buffers['stderr'])}"
                    )
                    progress = artifact_progress(command)
                    if progress:
                        journal.write(f"STEP {step} FILE_PROGRESS{progress}")
                    heartbeat = now
        code = process.wait()
        if quiet_output:
            journal.write(
                f"STEP {step} inspect stdout retained in memory ({len(buffers['stdout'])} bytes); environment values omitted from journal",
                console=False,
            )
        status = "DONE" if code == 0 else ("LOOKUP_RESULT" if probe else "FAIL")
        journal.write(
            f"STEP {step} {status} exit={code}; elapsed={time.monotonic() - started:.2f}s",
            "INFO" if code == 0 or probe else "ERROR",
        )
        if code and not probe:
            detail = buffers["stderr"].decode(errors="replace").strip()
            source = "STDERR"
            if not detail and not quiet_output:
                detail = buffers["stdout"].decode(errors="replace").strip()
                source = "STDOUT"
            lines = detail.splitlines()
            for line in lines[-5:]:
                summary = line if len(line) <= 180 else line[:70] + " ... " + line[-100:]
                journal.write(f"STEP {step} {source}: {summary}", "ERROR")
            if len(lines) > 5:
                journal.write(f"STEP {step} full output: {journal.path}", "ERROR")
        return subprocess.CompletedProcess(
            command,
            code,
            buffers["stdout"].decode(errors="replace"),
            buffers["stderr"].decode(errors="replace"),
        )
    except BaseException as error:
        if process.poll() is None:
            process.kill()
        process.wait()
        journal.write(
            f"STEP {step} FAIL elapsed={time.monotonic() - started:.2f}s; {type(error).__name__}: {error}",
            "ERROR",
        )
        raise
    finally:
        process.stdout.close()
        process.stderr.close()
