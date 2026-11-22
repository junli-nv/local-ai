"""Reuse genuine native SDK installations while preserving per-launch config isolation."""

import fcntl
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from . import installlog
from .common import atomic_json, fingerprint, run

SDK = "@opencode-ai/plugin"


def public_path(assets, version):
    if not isinstance(version, str) or not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Invalid OpenCode SDK version")
    return assets / "plugin-dependencies" / version


def complete(path, version):
    try:
        package = json.loads((path / "package.json").read_text())
        lock = json.loads((path / "package-lock.json").read_text())
        packages = lock["packages"]
        return (
            isinstance(packages, dict)
            and package.get("dependencies") == {SDK: version}
            and not any(
                package.get(k)
                for k in ("devDependencies", "optionalDependencies", "peerDependencies")
            )
            and packages[""]["dependencies"] == {SDK: version}
            and packages["node_modules/" + SDK]["version"] == version
            and all(
                name.startswith("node_modules/")
                and ".." not in Path(name).parts
                and (
                    entry.get("optional", False)
                    and name != "node_modules/" + SDK
                    or json.loads((path / name / "package.json").read_text()).get("version")
                    == entry["version"]
                )
                for name, entry in packages.items()
                if name
            )
        )
    except (OSError, ValueError, KeyError, TypeError):
        return False


def prepare_public(assets, version):
    """Materialize only the public SDK dependency tree for an offline export."""
    target = public_path(assets, version)
    if complete(target, version):
        return target
    if target.exists():
        raise ValueError("Incomplete OpenCode SDK assets: " + str(target))
    npm = shutil.which("npm")
    if not npm:
        raise ValueError(
            "Export needs the OpenCode " + version + " plugin SDK. "
            "Prepare this client on a connected host with npm before exporting."
        )
    target.parent.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".prepare-", dir=target.parent) as directory:
        temporary = Path(directory)
        atomic_json(temporary / "package.json", {"private": True, "dependencies": {SDK: version}})
        installlog.event("PREPARE OpenCode plugin SDK " + version)
        run(
            [
                npm,
                "install",
                "--offline=false",
                "--omit=dev",
                "--omit=optional",
                "--ignore-scripts",
                "--no-audit",
                "--no-fund",
                "--no-bin-links",
            ],
            cwd=temporary,
            env={**os.environ, "npm_config_offline": "false"},
            timeout=180,
        )
        if not complete(temporary, version):
            raise ValueError("OpenCode SDK preparation produced incomplete dependencies")
        for path in (temporary, *temporary.rglob("*")):
            if path.is_symlink() or not (path.is_dir() or path.is_file()):
                raise ValueError("Invalid file in OpenCode SDK assets: " + str(path))
            path.chmod(0o755 if path.is_dir() else 0o644)
        try:
            temporary.rename(target)
        except OSError:
            if not complete(target, version):
                raise
    return target


def public_files(assets, version):
    directory = prepare_public(assets, version)
    for path in (directory, *directory.rglob("*")):
        if path.is_symlink() or not (path.is_dir() or path.is_file()):
            raise ValueError("Invalid file in OpenCode SDK assets: " + str(path))
        relative = path.relative_to(directory)
        if path.is_file() and relative.parts[0] in {
            "package.json",
            "package-lock.json",
            "node_modules",
        }:
            yield path


def copy(source, destination):
    destination.mkdir(parents=True, exist_ok=True)
    for name in ("package.json", "package-lock.json"):
        shutil.copyfile(source / name, destination / name)
    shutil.copytree(source / "node_modules", destination / "node_modules", symlinks=True)


def prime(state, assets, session):
    try:
        manifest = json.loads((assets / "manifest.json").read_text())
        version = manifest["version"]
        public = public_path(assets, version)
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
            source = next((p for p in [public, *candidates] if complete(p, version)), None)
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
