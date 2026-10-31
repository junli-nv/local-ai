"""Small stdlib-only primitives; no subprocesses run at import time."""

import hashlib
import json
import os
import platform
import subprocess
import tempfile
import time
from pathlib import Path

from . import installlog


def arch(value=None):
    value = (value or platform.machine()).lower()
    aliases = {"x86_64": "amd64", "amd64": "amd64", "aarch64": "arm64", "arm64": "arm64"}
    if value not in aliases:
        raise ValueError("Unsupported CPU architecture: " + value)
    return aliases[value]


def run(command, check=True, timeout=30, **kwargs):
    result = (
        installlog.run(
            command,
            timeout=timeout,
            probe=(not check and str(command[0]) == "docker" and "inspect" in command[:3]),
            **kwargs,
        )
        if installlog.active()
        else subprocess.run(command, capture_output=True, text=True, timeout=timeout, **kwargs)
    )
    if check and result.returncode:
        raise RuntimeError("Command failed: " + command[0] + "\n" + result.stderr.strip())
    return result


def atomic_json(path, value, mode=0o600):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp = tempfile.mkstemp(prefix="." + path.name + ".", dir=path.parent)
    try:
        os.fchmod(fd, mode)
        with os.fdopen(fd, "w") as stream:
            json.dump(value, stream, indent=2)
            stream.write("\n")
        os.replace(temp, path)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)


def fingerprint(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def sha256(path):
    h = hashlib.sha256()
    total = Path(path).stat().st_size
    size = 0
    started = last = time.monotonic()
    if installlog.active():
        installlog.event("CHECKSUM START SHA256 path=%s total_bytes=%d" % (path, total))
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
            size += len(chunk)
            now = time.monotonic()
            if installlog.active() and now - last >= 15:
                installlog.event(
                    "CHECKSUM RUNNING bytes=%d/%d elapsed=%.1fs" % (size, total, now - started)
                )
                last = now
    value = h.hexdigest()
    if installlog.active():
        installlog.event(
            "CHECKSUM DONE SHA256=%s elapsed=%.2fs" % (value, time.monotonic() - started)
        )
    return value


def private_dir(path):
    path = Path(path).expanduser().resolve()
    if path in {Path("/"), Path.home().resolve()}:
        raise ValueError("Use a dedicated private state directory")
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    if path.stat().st_uid != os.getuid():
        raise ValueError("State directory belongs to another user")
    path.chmod(0o700)
    return path


def client_home():
    return Path(os.environ.get("XDG_STATE_HOME", str(Path.home() / ".local/state"))) / "local-ai"


def verify_elf(path, expected):
    with Path(path).open("rb") as f:
        header = f.read(20)
    if len(header) < 20 or header[:4] != b"\x7fELF" or header[4] != 2:
        raise ValueError("Expected a 64-bit Linux ELF executable")
    endian = "little" if header[5] == 1 else "big"
    machine = int.from_bytes(header[18:20], endian)
    found = {62: "amd64", 183: "arm64"}.get(machine)
    if found != arch(expected):
        raise ValueError("Executable architecture mismatch: " + str(found) + " != " + expected)
    return found
