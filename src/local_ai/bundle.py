"""Portable project/resource archives with relative paths and checksums."""

import hashlib
import io
import json
import os
import tarfile
import tempfile
import time
from pathlib import Path

from . import __version__, installlog
from .common import arch, sha256, verify_elf
from .deployment import ensure_archive
from .paths import root, settings
from .profiles import profile, require_deployable
from .program import source_files


def verify(base):
    base = Path(base).resolve()
    manifest = json.loads((base / "bundle.json").read_text())
    if manifest.get("format") != 1 or not isinstance(manifest.get("files"), dict):
        raise ValueError("Unsupported or incomplete offline bundle manifest")
    for name, expected in manifest["files"].items():
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts or name in {"", "."}:
            raise ValueError("Unsafe offline bundle path: " + name)
        path = base / relative
        if not path.resolve().is_relative_to(base) or not path.is_file():
            raise ValueError("Missing or unsafe offline file: " + name)
        if sha256(path) != expected:
            raise ValueError("Offline file checksum mismatch: " + name)
    installlog.event("Offline bundle checksums verified")
    return manifest


def tree(directory):
    directory = Path(directory)
    seen = set()
    for current, dirs, names in os.walk(directory, followlinks=True):
        resolved = Path(current).resolve()
        if resolved in seen:
            raise ValueError("Cyclic or duplicate linked directory: " + str(current))
        seen.add(resolved)
        dirs[:] = sorted(d for d in dirs if d not in {"__pycache__", ".cache"})
        for name in sorted(names):
            path = Path(current) / name
            if not path.is_file():
                raise ValueError("Nonregular deployment asset: " + str(path))
            yield str(path.relative_to(directory)), path


class HashStream:
    def __init__(self, stream, label):
        self.stream = stream
        self.digest = hashlib.sha256()
        self.size = 0
        self.last = time.monotonic()
        self.label = label

    def update(self, data):
        self.digest.update(data)
        self.size += len(data)
        now = time.monotonic()
        if now - self.last >= 15:
            installlog.event("EXPORT RUNNING file=%s bytes=%d" % (self.label, self.size))
            self.last = now

    def read(self, size=-1):
        data = self.stream.read(size)
        self.update(data)
        return data

    def write(self, data):
        written = self.stream.write(data)
        self.update(data[:written])
        return written


def export(options):
    base = root()
    data = Path(options.data_dir).expanduser().resolve()
    output = Path(options.output).expanduser().resolve()
    for directory in {base, data}:
        if output.is_relative_to(directory) and not output.is_relative_to(directory / "dist"):
            raise ValueError(
                "Export inside an installation must use dist/; other paths must be outside"
            )
    selected = options.profile or settings().get("profiles", [])
    for name in selected:
        require_deployable(profile(name))
    files = source_files(base)
    profiles = sorted(set(selected))
    for name in profiles:
        policy = profile(name)
        from .images import cached_model

        if cached_model(data, policy) is None:
            raise ValueError("Complete the local model before exporting: " + name)
        archive = ensure_archive(data, policy)
        for item in [archive, Path(str(archive) + ".lock.json")]:
            files["images/" + item.name] = item
    if (data / "models").is_dir():
        if not profiles:
            raise ValueError("Use --profile for existing server resources before exporting")
        files.update({"models/" + name: path for name, path in tree(data / "models")})
    clients = []
    candidates = list((base / "clients").glob("*/manifest.json"))
    if options.client_dir:
        candidates.append(Path(options.client_dir).expanduser().resolve() / "manifest.json")
    for manifest in candidates:
        client = manifest.parent
        value = json.loads(manifest.read_text())
        cpu = arch(value["arch"])
        if cpu in clients:
            if not options.client_dir or client != Path(options.client_dir).expanduser().resolve():
                raise ValueError("More than one client selected for architecture " + cpu)
            files = {
                name: path
                for name, path in files.items()
                if not name.startswith("clients/" + cpu + "/")
            }
            clients.remove(cpu)
        verify_elf(client / "bin/opencode", cpu)
        if sha256(client / "bin/opencode") != value["sha256"]:
            raise ValueError("Client binary changed before export")
        clients.append(cpu)
        files["clients/" + cpu + "/manifest.json"] = manifest
        for folder in ["bin", "seed-cache/opencode/bin"]:
            files.update(
                {
                    "clients/" + cpu + "/" + folder + "/" + name: path
                    for name, path in tree(client / folder)
                }
            )
        public_catalog = client / "seed-cache/opencode/models.json"
        if public_catalog.is_file():
            files["clients/" + cpu + "/seed-cache/opencode/models.json"] = public_catalog
    if not profiles and not clients:
        raise ValueError("Run install first, or select legacy --profile / --client-dir resources")
    catalog = os.environ.get("LOCAL_AI_CATALOG")
    catalog = Path(catalog).expanduser().resolve() if catalog else base / "config/catalog.json"
    if catalog.is_file():
        files["config/catalog.json"] = catalog
    role = "both" if profiles and clients else ("server" if profiles else "client")
    installation = {"format": 1, "version": __version__, "role": role, "profiles": profiles}
    selected_default = settings().get("default_profile")
    if profiles:
        selected_default = selected_default if selected_default in profiles else profiles[0]
        installation["default_profile"] = selected_default
        installation["model"] = profile(selected_default)["served_name"]
    elif settings().get("model"):
        installation["model"] = settings()["model"]
    output.parent.mkdir(parents=True, exist_ok=True)
    hashes = {}
    with tempfile.TemporaryDirectory(prefix=".local-ai-export-", dir=output.parent) as temporary:
        pending = Path(temporary) / "archive"
        with pending.open("wb") as raw:
            stream = HashStream(raw, str(output))
            mode = "w|gz" if output.name.endswith((".gz", ".tgz")) else "w|"
            with tarfile.open(
                fileobj=stream,
                mode=mode,
                dereference=True,
                bufsize=1024 * 1024,
                copybufsize=1024 * 1024,
            ) as tar:
                directory = tarfile.TarInfo("local-ai")
                directory.type, directory.mode = tarfile.DIRTYPE, 0o755
                tar.addfile(directory)
                for name, path in sorted(files.items()):
                    before = path.stat()
                    info = tar.gettarinfo(str(path), arcname="local-ai/" + name)
                    if not info.isfile():
                        raise ValueError("Only regular files belong in the offline bundle")
                    info.uid = info.gid = 0
                    info.uname = info.gname = ""
                    with path.open("rb") as asset:
                        reader = HashStream(asset, name)
                        tar.addfile(info, reader)
                        hashes[name] = reader.digest.hexdigest()
                    after = path.stat()
                    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
                        raise ValueError("File changed during export: " + name)
                manifest = {
                    "format": 1,
                    "version": __version__,
                    "installation": installation,
                    "clients": sorted(clients),
                    "files": hashes,
                }
                content = (json.dumps(manifest, indent=2) + "\n").encode()
                info = tarfile.TarInfo("local-ai/bundle.json")
                info.size, info.mode = len(content), 0o644
                tar.addfile(info, io.BytesIO(content))
            raw.flush()
            os.fsync(raw.fileno())
        digest = stream.digest.hexdigest()
        os.replace(pending, output)
    checksum = Path(str(output) + ".sha256")
    checksum.write_text(digest + "  " + output.name + "\n")
    return {
        "archive": str(output),
        "sha256_file": str(checksum),
        "directory": "local-ai",
        "profiles": profiles,
        "clients": sorted(clients),
        "files": len(hashes),
        "excluded": ["instances", "logs", "cache", "user histories", "credentials"],
    }
