#!/usr/bin/env python3
"""Standalone local-ai program updates; Python 3.10+, no resource preparation."""

import argparse
import contextlib
import datetime
import fcntl
import hashlib
import json
import os
import re
import shlex
import shutil
import sys
import tarfile
import tempfile
import urllib.request
from pathlib import Path, PurePosixPath

PROGRAM = (
    "local-ai",
    "install.sh",
    "pyproject.toml",
    "MANIFEST.in",
    ".gitignore",
    "README.md",
    "README.en.md",
    "AGENTS.md",
    "LICENSE",
    "LICENSE.md",
    "src",
    "docs",
    "templates",
    "scripts",
    "tests",
    ".github",
)
PROTECTED = {
    "models",
    "images",
    "clients",
    "instances",
    "dist",
    "config",
    "installation.json",
    "bundle.json",
    "install.log",
}
VERSION = re.compile(r'__version__\s*=\s*["\']([^"\']+)["\']')


def client_activity(root, proc=Path("/proc")):
    """Best-effort Linux snapshot; never return prompts, environment or signals."""
    result = {"supported": False, "processes": [], "unreadable": 0}
    try:
        entries = list(proc.iterdir())
    except OSError:
        return result
    result["supported"] = True
    root = root.resolve()
    for entry in entries:
        if not entry.name.isdigit() or int(entry.name) == os.getpid():
            continue
        try:
            executable = Path(os.readlink(entry / "exe").removesuffix(" (deleted)"))
            kind = None
            if executable.name == "opencode" and executable.is_relative_to(root / "clients"):
                kind = "opencode"
            else:
                with (entry / "cmdline").open("rb") as stream:
                    args = stream.read(65536).decode(errors="replace").split("\0")
                cwd = (entry / "cwd").resolve(strict=True)
                interpreter = executable.name in {
                    "bash",
                    "sh",
                    "dash",
                } or executable.name.startswith("python")
                for arg in args[:3] if interpreter else []:
                    if arg and (cwd / arg).resolve() == root / "local-ai":
                        kind = "launcher"
                if any(args[i : i + 2] == ["-m", "local_ai.cli"] for i in range(len(args) - 1)):
                    with (entry / "environ").open("rb") as stream:
                        environment = stream.read(1 << 20).split(b"\0")
                    pythonpath = next(
                        (x.partition(b"=")[2] for x in environment if x.startswith(b"PYTHONPATH=")),
                        b"",
                    ).decode(errors="replace")
                    if any(
                        (cwd / x).resolve() == root / "src"
                        for x in pythonpath.split(os.pathsep)
                        if x
                    ):
                        kind = "launcher"
            if kind:
                result["processes"].append(
                    {
                        "pid": int(entry.name),
                        "kind": kind,
                        "executable": str(executable),
                        "uid": entry.stat().st_uid,
                    }
                )
        except PermissionError:
            result["unreadable"] += 1
        except (OSError, ValueError):
            continue
    result["processes"].sort(key=lambda item: item["pid"])
    return result


def check_activity(root, allow=False):
    report = client_activity(root)
    if not report["supported"] or report["unreadable"]:
        print(
            "WARNING: Client process visibility is incomplete; check other users, "
            "external client directories and remote hosts manually.",
            file=sys.stderr,
        )
    if report["processes"]:
        pids = ", ".join(str(item["pid"]) for item in report["processes"])
        if not allow:
            raise RuntimeError(
                "Active client processes for this installation: PID "
                + pids
                + ". Exit these clients first, or explicitly use --allow-active-clients "
                "for a program-only update/rollback. No processes were stopped."
            )
        print(
            "WARNING: Proceeding with active clients (PID "
            + pids
            + "); they are not stopped or restarted. Reopen them later to load changes.",
            file=sys.stderr,
        )
    return report


def recovery(root, backup):
    return {
        "rollback_command": [
            sys.executable,
            str(backup / "update.py"),
            "--root",
            str(root),
            "--rollback",
            str(backup),
        ],
        "backup_scope": "program-and-installation-metadata",
        "history_backed_up": False,
        "native_client_changed": False,
    }


def version(root):
    match = VERSION.search((root / "src/local_ai/__init__.py").read_text())
    if not match:
        raise ValueError("Program version is missing")
    return match.group(1)


def atomic_json(path, value):
    previous = path.stat() if path.exists() else None
    with tempfile.NamedTemporaryFile("w", dir=path.parent, delete=False) as stream:
        pending = Path(stream.name)
        json.dump(value, stream, indent=2)
        stream.write("\n")
    try:
        if previous is not None:
            pending.chmod(previous.st_mode & 0o777)
            if os.geteuid() == 0:
                os.chown(pending, previous.st_uid, previous.st_gid)
        os.replace(pending, path)
    finally:
        pending.unlink(missing_ok=True)


def remove(path):
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def copy(source, destination):
    if source.is_dir() and not source.is_symlink():
        shutil.copytree(source, destination, symlinks=True)
    else:
        shutil.copy2(source, destination, follow_symlinks=False)


@contextlib.contextmanager
def locked(root):
    with (root / ".update.lock").open("a") as stream:
        try:
            fcntl.flock(stream, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise RuntimeError("Another program update is running") from error
        yield


def unpack(archive, stage):
    seen, top = set(), None
    with tarfile.open(archive, "r:*") as source:
        for member in source:
            path = PurePosixPath(member.name)
            if path.is_absolute() or ".." in path.parts or not path.parts:
                raise ValueError("Unsafe archive path: " + member.name)
            if top is None:
                top = path.parts[0]
            if path.parts[0] != top:
                raise ValueError("Expected one top-level source directory")
            if not member.isdir() and not member.isfile():
                raise ValueError("Archive links and special files are not allowed")
            relative = path.parts[1:]
            if not relative:
                if not member.isdir():
                    raise ValueError("Expected a source directory")
                continue
            if relative[0] in PROTECTED:
                raise ValueError("Use a source archive, not a model/image deployment bundle")
            if relative[0] not in PROGRAM:
                continue
            name = "/".join(relative)
            if name in seen:
                raise ValueError("Duplicate archive member: " + name)
            seen.add(name)
            target = stage.joinpath(*relative)
            if member.isdir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with source.extractfile(member) as incoming, target.open("wb") as output:
                    shutil.copyfileobj(incoming, output)
                target.chmod(member.mode & 0o777)
    for name in ("local-ai", "src/local_ai/cli.py", "src/local_ai/profiles.json"):
        if not (stage / name).is_file():
            raise ValueError("Incomplete source archive: " + name)
    return version(stage)


def log(root, result):
    stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    with (root / "install.log").open("a") as stream:
        stream.write(stamp + " UPDATE " + json.dumps(result) + "\n")


def restore(root, backup):
    record = json.loads((backup / "update.json").read_text())
    if record.get("format") != 1 or record.get("root") != str(root):
        raise ValueError("Backup belongs to another installation")
    original = record.get("original")
    if not isinstance(original, list) or any(name not in PROGRAM for name in original):
        raise ValueError("Invalid program backup manifest")
    for name in PROGRAM:
        saved, target = backup / "program" / name, root / name
        if saved.exists() or saved.is_symlink():
            remove(target)
            copy(saved, target)
        elif name not in original:
            remove(target)
    for name in ("installation.json", "bundle.json"):
        target, saved = root / name, backup / "metadata" / name
        if saved.is_file():
            shutil.copy2(saved, target)
        elif not record.get(name + "_existed"):
            target.unlink(missing_ok=True)
    return record


def write_settings(root, target_version):
    path = root / "installation.json"
    if path.is_file():
        settings = json.loads(path.read_text())
        if not isinstance(settings, dict):
            raise ValueError("installation.json must contain an object")
        settings["version"] = target_version
        settings.pop("bundle_sha256", None)
        atomic_json(path, settings)


def apply(root, stage, target_version, archive_sha):
    old_version = version(root)
    for name in ("installation.json", "bundle.json"):
        path = root / name
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise ValueError("Expected regular metadata file: " + name)
    if (root / "installation.json").is_file():
        settings = json.loads((root / "installation.json").read_text())
        if not isinstance(settings, dict):
            raise ValueError("installation.json must contain an object")
    original = [name for name in PROGRAM if (root / name).exists() or (root / name).is_symlink()]
    for name in original:
        if (root / name).is_symlink():
            raise ValueError("Program paths must be ordinary files/directories: " + name)
    backup = Path(tempfile.mkdtemp(prefix="local-ai-backup-", dir=root.parent))
    (backup / "program").mkdir()
    (backup / "metadata").mkdir()
    shutil.copy2(Path(__file__).resolve(), backup / "update.py")
    record = {
        "format": 1,
        "root": str(root),
        "from_version": old_version,
        "to_version": target_version,
        "archive_sha256": archive_sha,
        "original": original,
        "state": "prepared",
    }
    for name in ("installation.json", "bundle.json"):
        path = root / name
        record[name + "_existed"] = path.exists()
        if path.exists():
            if not path.is_file() or path.is_symlink():
                raise ValueError("Expected regular metadata file: " + name)
            shutil.copy2(path, backup / "metadata" / name)
    atomic_json(backup / "update.json", record)
    print("Program backup: " + str(backup), file=sys.stderr, flush=True)
    try:
        for name in original:
            os.replace(root / name, backup / "program" / name)
        for name in PROGRAM:
            if (stage / name).exists():
                os.replace(stage / name, root / name)
        write_settings(root, target_version)
        (root / "bundle.json").unlink(missing_ok=True)
        record["state"] = "completed"
        atomic_json(backup / "update.json", record)
        result = {
            "state": "updated",
            "root": str(root),
            "version": target_version,
            "previous_version": old_version,
            "backup": str(backup),
            "archive_sha256": archive_sha,
            "resources_changed": False,
            "service_restarted": False,
            **recovery(root, backup),
        }
        print("Rollback: " + shlex.join(result["rollback_command"]), file=sys.stderr)
        log(root, result)
        return result
    except BaseException:
        restore(root, backup)
        record["state"] = "failed-restored"
        atomic_json(backup / "update.json", record)
        print(
            "Update failed; previous program restored; backup: " + str(backup),
            file=sys.stderr,
            flush=True,
        )
        raise


def execute(args):
    root = Path(args.root).expanduser().resolve()
    if root == root.parent or not root.is_dir():
        raise ValueError("--root must name an existing installation directory")
    if not args.rollback:
        if not (root / "local-ai").is_file():
            raise ValueError("--root must name an existing local-ai installation")
        version(root)
    if args.check:
        activity = client_activity(root)
        return {
            "state": "checked",
            "root": str(root),
            "version": version(root),
            "ready": (
                not activity["processes"] and activity["unreadable"] == 0
                if activity["supported"]
                else None
            ),
            "activity_check": activity,
            "backup_scope": "program-and-installation-metadata",
            "history_backed_up": False,
            "native_client_changed": False,
        }
    with locked(root):
        check_activity(root, args.allow_active_clients)
        if args.rollback:
            backup = Path(args.rollback).expanduser().resolve()
            record = restore(root, backup)
            result = {
                "state": "rolled-back",
                "root": str(root),
                "version": record["from_version"],
                "backup": str(backup),
                "resources_changed": False,
                "service_restarted": False,
                "native_client_changed": False,
                "history_backed_up": False,
            }
            log(root, result)
            return result
        with tempfile.TemporaryDirectory(prefix=".local-ai-update-", dir=root.parent) as work:
            temporary = Path(work)
            if args.archive:
                archive = Path(args.archive).expanduser().resolve()
            else:
                selected = args.version.removeprefix("v")
                if not re.fullmatch(r"[0-9]+\.[0-9]+\.[0-9]+", selected):
                    raise ValueError(
                        "--version must be a numeric tag, in the form vMAJOR.MINOR.PATCH"
                    )
                url = (
                    "https://github.com/junli-nv/local-ai/archive/refs/tags/v"
                    + selected
                    + ".tar.gz"
                )
                archive = temporary / "source.tar.gz"
                print("Downloading program source: " + url, file=sys.stderr, flush=True)
                with urllib.request.urlopen(url, timeout=30) as incoming, archive.open("wb") as out:
                    shutil.copyfileobj(incoming, out)
            digest = hashlib.sha256()
            with archive.open("rb") as stream:
                for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                    digest.update(chunk)
            actual = digest.hexdigest()
            if args.sha256 and args.sha256.lower() != actual:
                raise ValueError("Source archive SHA256 mismatch")
            stage = temporary / "program"
            stage.mkdir()
            target_version = unpack(archive, stage)
            if args.version and target_version != args.version.removeprefix("v"):
                raise ValueError("Source version does not match the selected tag")
            helper = stage / "scripts/update.py"
            if not helper.is_file():
                helper.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(Path(__file__).resolve(), helper)
            # Recheck after download/unpack; a client may have started meanwhile.
            activity = check_activity(root, args.allow_active_clients)
            result = apply(root, stage, target_version, actual)
            result["activity_check"] = activity
            return result


def parser():
    result = argparse.ArgumentParser(
        description="Update local-ai program files only; never download models/images/clients."
    )
    result.add_argument("--root", required=True, help="Existing unpacked installation directory")
    source = result.add_mutually_exclusive_group(required=True)
    source.add_argument(
        "--version", help="Download an explicit Git tag, in the form vMAJOR.MINOR.PATCH"
    )
    source.add_argument("--archive", help="Local source tar archive; no network access")
    source.add_argument("--rollback", help="Restore a backup printed by a previous update")
    source.add_argument(
        "--check",
        action="store_true",
        help="Read-only activity check; no download or replacement; exit 3 if not ready",
    )
    result.add_argument(
        "--allow-active-clients",
        action="store_true",
        help="Explicitly permit program-only update/rollback with detected active clients; "
        "never stop processes or upgrade OpenCode",
    )
    result.add_argument("--sha256", help="Optional expected SHA256 of the source archive")
    return result


def main(argv=None):
    arguments = parser().parse_args(argv)
    if (arguments.rollback or arguments.check) and arguments.sha256:
        parser().error("--sha256 applies only to source archives")
    try:
        result = execute(arguments)
        print(json.dumps(result, indent=2))
        return 3 if arguments.check and result["ready"] is not True else 0
    except KeyboardInterrupt:
        print("Update interrupted", file=sys.stderr)
        return 130
    except Exception as error:
        print("ERROR: " + str(error), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
