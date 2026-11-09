"""Pinned public Hugging Face files, downloaded with the host Python standard library."""

import hashlib
import json
import os
import re
import time
import urllib.request
from pathlib import Path, PurePosixPath
from urllib.parse import quote

from . import installlog


def metadata(policy):
    revision = policy["revision"]
    if not re.fullmatch(r"[0-9a-fA-F]{40}", revision):
        raise ValueError("Media preparation requires a full pinned model commit")
    repo = quote(policy["repo"], safe="/")
    url = "https://huggingface.co/api/models/" + repo + "/revision/" + revision + "?blobs=true"
    with urllib.request.urlopen(url, timeout=60) as response:
        value = json.load(response)
    if value.get("sha") != revision:
        raise ValueError("Hub revision differs from the pinned model commit")
    entries = value.get("siblings")
    if not isinstance(entries, list) or not entries:
        raise ValueError("Hub returned no model files")
    seen = set()
    for entry in entries:
        name = entry.get("rfilename", "")
        path = PurePosixPath(name)
        if (
            not name
            or name == "."
            or path.is_absolute()
            or ".." in path.parts
            or "\\" in name
            or str(path) != name
            or path.parts[0] == ".cache"
            or name == "model.lock.json"
            or name in seen
        ):
            raise ValueError("Unsafe or duplicate Hub model path: " + name)
        size = entry.get("size")
        if type(size) is not int or size < 0:
            raise ValueError("Missing model file length: " + name)
        digest = entry.get("lfs", {}).get("sha256") or entry.get("blobId")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", digest):
            raise ValueError("Missing model content identity: " + name)
        entry["digest"] = digest
        seen.add(name)
    return entries


def safe_path(base, relative):
    path = base / relative
    if not path.resolve().is_relative_to(base.resolve()):
        raise ValueError("Model path escapes its directory")
    for item in [path, *path.parents]:
        if item == base.parent:
            break
        if item.is_symlink():
            raise ValueError("Model download paths must not contain symbolic links")
    return path


def content_matches(path, entry):
    if not path.is_file() or path.stat().st_size != entry["size"]:
        return False
    digest = entry["digest"]
    check = hashlib.sha256() if len(digest) == 64 else hashlib.sha1()
    if len(digest) == 40:
        check.update(("blob " + str(entry["size"]) + "\0").encode())
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            check.update(chunk)
    return check.hexdigest() == digest


def download_file(base, policy, entry):
    target = safe_path(base, entry["rfilename"])
    if content_matches(target, entry):
        return
    target.parent.mkdir(parents=True, exist_ok=True)
    partial = safe_path(
        base,
        ".cache/local-ai-prepare/"
        + policy["revision"]
        + "/"
        + hashlib.sha256(entry["rfilename"].encode()).hexdigest()
        + ".part",
    )
    partial.parent.mkdir(parents=True, exist_ok=True)
    url = (
        "https://huggingface.co/"
        + quote(policy["repo"], safe="/")
        + "/resolve/"
        + policy["revision"]
        + "/"
        + quote(entry["rfilename"], safe="/")
    )
    for attempt in range(3):
        try:
            transfer(url, partial, entry["size"])
            if not content_matches(partial, entry):
                partial.unlink(missing_ok=True)
                raise ValueError("Model content checksum mismatch: " + entry["rfilename"])
            os.replace(partial, target)
            return
        except (OSError, ValueError):
            if attempt == 2:
                raise
            time.sleep(2**attempt)


def transfer(url, partial, size):
    offset = partial.stat().st_size if partial.exists() else 0
    if offset > size:
        partial.unlink()
        offset = 0
    if offset == size:
        partial.touch(exist_ok=True)
        return
    headers = {"Range": "bytes=%d-" % offset} if offset else {}
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=60) as response:
        status = response.status
        if status == 206:
            match = re.fullmatch(
                r"bytes (\d+)-(\d+)/(\d+)", response.headers.get("Content-Range", "")
            )
            if not match or int(match[1]) != offset or int(match[3]) != size:
                raise ValueError("Invalid resumed model response")
        elif status == 200:
            offset = 0
        else:
            raise ValueError("Unexpected model HTTP status: " + str(status))
        last = time.monotonic()
        with partial.open("ab" if offset else "wb") as stream:
            while chunk := response.read(1024 * 1024):
                stream.write(chunk)
                offset += len(chunk)
                if offset > size:
                    raise ValueError("Model response exceeds expected file length")
                if time.monotonic() - last >= 15:
                    installlog.event("MODEL DOWNLOAD bytes=%d total=%d" % (offset, size))
                    last = time.monotonic()
        if offset != size:
            raise OSError("Incomplete model download: %d of %d bytes" % (offset, size))


def download_model(root, policy, force=False):
    from concurrent.futures import ThreadPoolExecutor, as_completed

    from .common import atomic_json
    from .images import cached_model
    from .server import validate_model

    if not force:
        cached = cached_model(root, policy)
        if cached is not None and cached["revision_verified"]:
            return cached
    base = Path(root).resolve() / "models" / policy["model_directory"]
    safe_path(Path(root).resolve(), "models/" + policy["model_directory"])
    base.mkdir(parents=True, exist_ok=True)
    entries = metadata(policy)
    installlog.event("DOWNLOAD model with host Python; repo=" + policy["repo"])
    lock = base / "model.lock.json"
    if lock.is_symlink():
        raise ValueError("Model revision lock must not be a symbolic link")
    lock.unlink(missing_ok=True)
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(download_file, base, policy, entry) for entry in entries]
        for i, future in enumerate(as_completed(futures), 1):
            future.result()
            installlog.event("MODEL FILES complete=%d total=%d" % (i, len(entries)))
    validate_model(root, policy)
    atomic_json(lock, {"repo": policy["repo"], "revision": policy["revision"]})
    return {
        "model": str(base),
        "status": "downloaded",
        "network": True,
        "revision_verified": True,
        "log": str(installlog.path()) if installlog.path() else None,
    }
