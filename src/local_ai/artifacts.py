"""Client assets only: no model weights, credentials or user databases."""

import base64
import hashlib
import hmac
import json
import os
import re
import shutil
import tarfile
import tempfile
import time
import urllib.request
from pathlib import Path

from . import installlog
from .common import arch, atomic_json, private_dir, run, sha256, verify_elf

VERSION = "1.19.5"


def verify_integrity(path, integrity):
    algorithm, encoded = integrity.split("-", 1)
    if algorithm not in {"sha256", "sha512"}:
        raise ValueError("Require SHA256/SHA512 package integrity")
    h = hashlib.new(algorithm)
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(chunk)
    if not hmac.compare_digest(h.digest(), base64.b64decode(encoded, validate=True)):
        raise ValueError("Package integrity mismatch")


def fetch(url, destination):
    if not url.startswith("https://"):
        raise ValueError("Download URL must use HTTPS")
    req = urllib.request.Request(url, headers={"User-Agent": "cluster-local-ai/0.1"})
    with urllib.request.urlopen(req, timeout=60) as response, Path(destination).open("wb") as out:
        total = int(response.headers.get("Content-Length", 0))
        received = 0
        started = last = time.monotonic()
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            out.write(chunk)
            received += len(chunk)
            now = time.monotonic()
            if now - last >= 15:
                progress = (" percent=%.1f" % (100 * received / total)) if total else ""
                installlog.event(
                    "DOWNLOAD RUNNING bytes=%d total=%s elapsed=%.1fs%s"
                    % (received, total or "unknown", now - started, progress)
                )
                last = now
        if total and received != total:
            raise OSError("Incomplete download: received %d of %d bytes" % (received, total))
        installlog.event(
            "DOWNLOAD DONE bytes=%d elapsed=%.2fs" % (received, time.monotonic() - started)
        )


def extract_binary(archive, destination):
    with tarfile.open(archive, "r:gz") as tar:
        entry = tar.getmember("package/bin/opencode")
        if not entry.isfile() or entry.size > 512 * 1024 * 1024:
            raise ValueError("Invalid binary archive member")
        with tar.extractfile(entry) as source, Path(destination).open("wb") as out:
            shutil.copyfileobj(source, out, 1024 * 1024)


def seed_cache(source, destination, expected_arch):
    """Copy only the known public models catalog and tool binaries."""
    source = Path(source)
    if not source.is_dir():
        raise ValueError("Cache seed directory does not exist")
    destination = Path(destination)
    for name in ["opencode/models.json", "opencode/bin"]:
        item = source / name
        if item.is_symlink():
            raise ValueError("Cache seed must not contain symbolic links")
        if not item.exists():
            continue
        members = list(item.rglob("*")) if item.is_dir() else [item]
        for f in members:
            if f.is_symlink():
                raise ValueError("Cache seed must not contain symbolic links")
            if f.is_file():
                with f.open("rb") as stream:
                    is_elf = stream.read(4) == b"\x7fELF"
                if is_elf:
                    verify_elf(f, expected_arch)
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)


def install(root, binary=None, seed=None, version=None, expected_sha256=None):
    if version is not None and not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Use an explicit numeric OpenCode release")
    root = private_dir(root)
    cpu = arch()
    if version is None and binary is None:
        version = validate(root)["version"] if (root / "manifest.json").is_file() else VERSION
    installlog.event(
        "CHECK native client; architecture="
        + cpu
        + "; expected_version="
        + (version or "detect-from-local-binary")
    )
    if binary is None and seed is None and (root / "manifest.json").is_file():
        existing = validate(root)
        if existing["version"] == version:
            installlog.event("REUSE verified native client; no NPM access")
            return {
                "client_dir": str(root),
                "manifest": existing,
                "status": "already-present",
                "network": False,
            }

    (root / "bin").mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="install-", dir=root) as directory:
        temp = Path(directory)
        target = temp / "opencode"
        source = "imported"
        if binary:
            installlog.event("IMPORT local client binary: " + str(binary))
            if expected_sha256 and sha256(binary) != expected_sha256:
                raise ValueError("Imported binary SHA256 mismatch")
            shutil.copy2(binary, target)
        else:
            package = "opencode-linux-" + ("x64" if cpu == "amd64" else "arm64")
            metadata = "https://registry.npmjs.org/" + package + "/" + version
            req = urllib.request.Request(metadata, headers={"User-Agent": "cluster-local-ai/0.1"})
            installlog.event("DOWNLOAD NPM metadata: " + metadata)
            with urllib.request.urlopen(req, timeout=30) as response:
                info = json.load(response)
            if info["name"] != package or info["version"] != version:
                raise ValueError("NPM package identity mismatch")
            archive = temp / "client.tgz"
            installlog.event("DOWNLOAD client archive: " + info["dist"]["tarball"])
            fetch(info["dist"]["tarball"], archive)
            installlog.event("VERIFY NPM integrity; bytes=" + str(archive.stat().st_size))
            verify_integrity(archive, info["dist"]["integrity"])
            extract_binary(archive, target)
            source = {"registry": metadata, "integrity": info["dist"]["integrity"]}
        installlog.event("VERIFY ELF architecture and requested binary version")
        verify_elf(target, cpu)
        target.chmod(0o755)
        actual_version = run([str(target), "--version"]).stdout.strip()
        if not re.fullmatch(r"\d+\.\d+\.\d+", actual_version):
            raise ValueError("Local OpenCode binary did not report a numeric release")
        if version is not None and actual_version != version:
            raise ValueError("Client version differs from requested release")
        version = actual_version
        os.replace(target, root / "bin/opencode")
    cache = root / "seed-cache"
    cache.mkdir(exist_ok=True)
    if seed:
        seed_cache(seed, cache, cpu)
    value = {
        "version": version,
        "arch": cpu,
        "sha256": sha256(root / "bin/opencode"),
        "source": source,
    }
    atomic_json(root / "manifest.json", value)
    installlog.event("INSTALL native client complete; SHA256=" + value["sha256"])
    return {"client_dir": str(root), "manifest": value}


def validate(root):
    root = Path(root)
    value = json.loads((root / "manifest.json").read_text())
    if value["arch"] != arch():
        raise ValueError("Installed client assets belong to another CPU architecture")
    verify_elf(root / "bin/opencode", value["arch"])
    if sha256(root / "bin/opencode") != value["sha256"]:
        raise ValueError("Client binary changed since installation")
    return value


def export_client(root, output):
    root = Path(root)
    validate(root)
    output = Path(output)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tarfile.open(output, "w:gz", compresslevel=1) as tar:
        for name in ["bin", "seed-cache", "manifest.json"]:
            tar.add(root / name, arcname="client/" + name)
    Path(str(output) + ".sha256").write_text(sha256(output) + "  " + output.name + "\n")
    return {"archive": str(output), "sha256_file": str(output) + ".sha256"}
