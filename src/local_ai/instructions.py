"""Install a managed template block without replacing personal instructions."""

import fcntl
import os
import stat
import tempfile
from pathlib import Path

from . import installlog
from .paths import root

BEGIN = b"<!-- local-ai:instructions:begin -->"
END = b"<!-- local-ai:instructions:end -->"


def personal_path():
    config = Path(os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config")
    return config.expanduser().absolute() / "opencode/AGENTS.md"


def content(selection, language):
    if selection not in {"general", "bcm"} or language not in {"zh", "en"}:
        raise ValueError("Unknown instructions template or language")
    directory = root() / "templates/opencode"
    if language == "en":
        directory /= "en"
    names = ["general", "bcm"] if selection == "bcm" else ["general"]
    body = b"\n\n".join(
        (directory / ("AGENTS." + name + ".md")).read_bytes().rstrip() for name in names
    )
    return BEGIN + b"\n" + body + b"\n" + END


def merge(previous, block):
    if BEGIN not in previous and END not in previous:
        separator = b"" if not previous else (b"\n" if previous.endswith(b"\n") else b"\n\n")
        return previous + separator + block + b"\n"
    if previous.count(BEGIN) != 1 or previous.count(END) != 1:
        raise ValueError(
            "Malformed local-ai instructions markers; repair AGENTS.md or use --instructions none"
        )
    start, end = previous.index(BEGIN), previous.index(END)
    if start >= end:
        raise ValueError(
            "Reversed local-ai instructions markers; repair AGENTS.md or use --instructions none"
        )
    return previous[:start] + block + previous[end + len(END) :]


def apply(selection="general", language="zh"):
    if selection == "none":
        return {"status": "skipped"}
    block = content(selection, language)
    target = personal_path()
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    lock = target.parent / ".local-ai-instructions.lock"
    fd = os.open(lock, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    with os.fdopen(fd, "r+") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        if target.is_symlink():
            raise ValueError(
                "Personal AGENTS.md is a symlink; manage it manually with --instructions none"
            )
        exists = target.exists()
        if exists and (not target.is_file() or target.stat().st_uid != os.getuid()):
            raise ValueError("Personal AGENTS.md must be a regular file owned by the current user")
        previous = target.read_bytes() if exists else b""
        updated = merge(previous, block)
        result = {"path": str(target), "template": selection, "language": language}
        if updated == previous:
            return {**result, "status": "unchanged"}
        backup = None
        if exists:
            backup_fd, backup = tempfile.mkstemp(prefix="AGENTS.md.bak-", dir=target.parent)
            with os.fdopen(backup_fd, "wb") as saved:
                saved.write(previous)
        fd, temporary = tempfile.mkstemp(prefix=".AGENTS.md-", dir=target.parent)
        try:
            mode = stat.S_IMODE(target.stat().st_mode) & 0o600 if exists else 0o600
            os.fchmod(fd, mode)
            with os.fdopen(fd, "wb") as output:
                output.write(updated)
            if target.is_symlink() or target.exists() != exists:
                raise ValueError("Personal AGENTS.md changed during installation; retry")
            if exists and target.read_bytes() != previous:
                raise ValueError("Personal AGENTS.md changed during installation; retry")
            os.replace(temporary, target)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
        installlog.event("APPLY personal instructions: " + str(target))
        if backup:
            installlog.event("Personal instructions backup: " + backup)
        installlog.event("Exit and restart OpenCode to load the installed personal instructions")
        return {**result, "status": "updated" if exists else "created", "backup": backup}
