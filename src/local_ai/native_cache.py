"""Reuse genuine native SDK installations while preserving per-launch config isolation."""

import fcntl
import json
import shutil
import tempfile
from pathlib import Path

from .common import fingerprint


def complete(path, version):
    try:
        package = json.loads((path / "package.json").read_text())
        lock = json.loads((path / "package-lock.json").read_text())
        installed = json.loads((path / "node_modules/@opencode-ai/plugin/package.json").read_text())
        return (
            package.get("dependencies") == {"@opencode-ai/plugin": version}
            and not any(
                package.get(k)
                for k in ("devDependencies", "optionalDependencies", "peerDependencies")
            )
            and lock["packages"][""]["dependencies"].get("@opencode-ai/plugin") == version
            and lock["packages"]["node_modules/@opencode-ai/plugin"]["version"] == version
            and installed.get("version") == version
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def copy(source, destination):
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("package.json", "package-lock.json"):
        shutil.copyfile(source / name, destination / name)
    shutil.copytree(source / "node_modules", destination / "node_modules", symlinks=True)


def prime(state, assets, session):
    try:
        manifest = json.loads((assets / "manifest.json").read_text())
        version = manifest["version"]
        if not isinstance(version, str) or not version:
            return False
    except (OSError, ValueError, KeyError):
        return False
    key = fingerprint({"version": version, "binary": manifest.get("sha256")})[:20]
    parent = state / "cache/local-ai-native-dependencies"
    parent.mkdir(parents=True, exist_ok=True)
    cached = parent / key
    with (state / ".native-dependencies.lock").open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        if not complete(cached, version):
            candidates = sorted((state / "logs").glob("*/config/opencode"), reverse=True)
            source = next((p for p in candidates if complete(p, version)), None)
            if source is None:
                return False
            temporary = Path(tempfile.mkdtemp(prefix=".native-", dir=parent))
            try:
                copy(source, temporary)
                if cached.exists():
                    # Invalid cache is retained for diagnosis, not treated as a valid installation.
                    cached.rename(parent / (key + "-invalid-" + temporary.name))
                temporary.rename(cached)
            finally:
                if temporary.exists():
                    shutil.rmtree(temporary)
        destination = session / "config/opencode"
        if not destination.exists():
            copy(cached, destination)
        return complete(destination, version)
