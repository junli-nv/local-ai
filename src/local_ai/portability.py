"""Private, version-checked history snapshots; never merge or overwrite databases."""

import contextlib
import hashlib
import json
import os
import re
import shutil
import sqlite3
import tempfile
import time
import zipfile
from pathlib import Path

from . import history
from .artifacts import validate
from .common import atomic_json, fingerprint, private_dir
from .endpoint import endpoint_url
from .resume import context_for

KEY = re.compile(r"[0-9a-f]{20}")
MAX_SIZE = 8 << 30


def digest(path):
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def select(state_root, key):
    if not KEY.fullmatch(key):
        raise ValueError("Invalid history identity")
    state_root = Path(state_root).expanduser().resolve()
    with history.locked(state_root):
        state = state_root / "services" / key
        if not state.is_dir() or not history.session_count(state):
            raise ValueError("History is missing or empty")
        value = history.load(state_root)
        value["active"] = key
        atomic_json(history.binding_path(state_root), value)
    return {"state": "selected", "history_id": key, "database_merged": False}


def backup_context(state):
    context = context_for(state)
    if context:
        return context
    # Pre-endpoint clients recorded the selected provider in their launch config.
    # This is historical metadata only; never reconnect to a saved tunnel URL.
    for path in sorted((state / "logs").glob("*/invocation.json"), reverse=True):
        config_path = path.parent / "opencode.json"
        if not config_path.is_file():
            continue
        invocation = json.loads(path.read_text())
        cfg = json.loads(config_path.read_text())
        provider, separator, model = cfg.get("model", "").partition("/")
        command = invocation.get("command")
        project = invocation.get("project")
        if (
            not separator
            or not model
            or not isinstance(command, list)
            or not command
            or not isinstance(command[0], str)
            or not Path(command[0]).is_absolute()
            or not isinstance(project, str)
            or not Path(project).is_absolute()
        ):
            continue
        base = cfg.get("provider", {}).get(provider, {}).get("options", {}).get("baseURL")
        if not isinstance(base, str):
            continue
        return {
            "client_dir": str(Path(command[0]).parent.parent),
            "project": project,
            "model": model,
            "endpoint": endpoint_url(base),
            "metadata_source": "legacy-launch-config",
        }
    return None


def backup(state_root, output):
    state_root = Path(state_root).expanduser().resolve()
    output = Path(output).expanduser().absolute()
    if output.exists() or output.is_symlink():
        raise ValueError("Backup output must not exist")
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {
        "schema": 1,
        "created": time.time(),
        "histories": [],
        "files": {},
        "contains_private_conversations": True,
        "execution_restored": False,
    }
    with (
        history.locked(state_root),
        tempfile.TemporaryDirectory(prefix="local-ai-history-") as temp,
    ):
        temp = Path(temp)
        binding = history.load(state_root)
        manifest["selected"] = history.selected_key(binding)
        for state in sorted((state_root / "services").glob("*")):
            if not KEY.fullmatch(state.name) or state.is_symlink():
                continue
            database = state / "data/opencode/opencode.db"
            if not database.is_file():
                continue
            if database.is_symlink():
                raise ValueError("Symlink history database is not supported")
            context = backup_context(state)
            if not context:
                raise ValueError("Missing connection metadata for history " + state.name)
            version = validate(Path(context["client_dir"]))["version"]
            target = temp / (state.name + ".db")
            with contextlib.closing(
                sqlite3.connect(database.as_uri() + "?mode=ro", uri=True, timeout=10)
            ) as src:
                with contextlib.closing(sqlite3.connect(target)) as dst:
                    src.backup(dst, pages=256, sleep=0.02)
                    if dst.execute("pragma quick_check").fetchone()[0] != "ok":
                        raise ValueError("History snapshot integrity check failed")
            target.chmod(0o600)
            name = "histories/" + state.name + ".db"
            manifest["histories"].append(
                {
                    "id": state.name,
                    "file": name,
                    "client_version": version,
                    "endpoint": context["endpoint"],
                    "model": context["model"],
                    "project": context["project"],
                    "project_overrides": context.get("project_overrides", {}),
                    "metadata_source": context.get("metadata_source", "connection"),
                }
            )
            manifest["files"][name] = {"sha256": digest(target), "size": target.stat().st_size}
        if not manifest["histories"]:
            raise ValueError(
                "No SQLite session histories found; legacy JSON histories need native migration first"
            )
        fd, pending = tempfile.mkstemp(prefix=".history-", dir=output.parent)
        try:
            os.fchmod(fd, 0o600)
            with (
                os.fdopen(fd, "wb") as raw,
                zipfile.ZipFile(raw, "w", compression=zipfile.ZIP_STORED) as z,
            ):
                z.writestr("manifest.json", json.dumps(manifest))
                for row in manifest["histories"]:
                    z.write(temp / (row["id"] + ".db"), row["file"])
            os.link(pending, output)
        finally:
            Path(pending).unlink(missing_ok=True)
    return {
        "state": "backed_up",
        "archive": str(output),
        "sha256": digest(output),
        "histories": len(manifest["histories"]),
        "contains_private_conversations": True,
        "auth_files_included": False,
        "transcripts_redacted": False,
        "jobs_included": False,
    }


def _restore(state_root, archive, assets, endpoint, choose=False, project=None):
    state_root = Path(state_root).expanduser().resolve()
    archive = Path(archive).expanduser().resolve(strict=True)
    endpoint = endpoint_url(endpoint)
    version = validate(Path(assets))["version"]
    identity = digest(archive)
    with zipfile.ZipFile(archive) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or sum(i.file_size for i in z.infolist()) > MAX_SIZE:
            raise ValueError("Duplicate entries or oversized history archive")
        if "manifest.json" not in names or z.getinfo("manifest.json").file_size > 1 << 20:
            raise ValueError("Missing or oversized history manifest")
        m = json.loads(z.read("manifest.json"))
        if m.get("schema") != 1 or not isinstance(m.get("histories"), list) or not m["histories"]:
            raise ValueError("Unsupported or empty history archive")
        expected = {"manifest.json"}
        source_ids = set()
        for row in m["histories"]:
            key = row.get("id", "")
            if not KEY.fullmatch(key) or key in source_ids:
                raise ValueError("Invalid or duplicate archived history identity")
            source_ids.add(key)
            name = "histories/" + key + ".db"
            if row.get("file") != name or row.get("client_version") != version:
                raise ValueError("Restore requires the same native client version as the snapshot")
            expected.add(name)
            if m.get("files", {}).get(name, {}).get("size") != z.getinfo(name).file_size:
                raise ValueError("Snapshot size mismatch")
        if set(names) != expected:
            raise ValueError("Unexpected archive entries; refusing extraction")
        with history.locked(state_root):
            imports_path = state_root / "history-imports.json"
            imports = json.loads(imports_path.read_text()) if imports_path.exists() else {}
            if identity in imports:
                prior = imports[identity]
                if any(
                    not (
                        state_root / "services" / r["history_id"] / "data/opencode/opencode.db"
                    ).is_file()
                    for r in prior["histories"]
                ):
                    raise ValueError(
                        "Previously imported history is missing; inspect it before restoring again"
                    )
                current = history.load(state_root)
                if choose:
                    preferred = next(
                        (
                            r["history_id"]
                            for r in prior["histories"]
                            if r["source_id"] == m.get("selected")
                        ),
                        prior["histories"][0]["history_id"],
                    )
                    current["active"] = preferred
                    atomic_json(history.binding_path(state_root), current)
                return {**prior, "selected": current.get("active"), "reused": True}
            services = private_dir(state_root / "services")
            old_binding = history.load(state_root)
            with tempfile.TemporaryDirectory(prefix=".restore-", dir=services) as temporary:
                temporary = Path(temporary)
                restored = []
                for row in m["histories"]:
                    key = fingerprint({"archive": identity, "history": row["id"]})[:20]
                    if (services / key).exists():
                        raise ValueError(
                            "Restore target already exists; no history was overwritten"
                        )
                    folder = private_dir(temporary / key)
                    destination = private_dir(folder / "data/opencode") / "opencode.db"
                    with z.open(row["file"]) as src, destination.open("xb") as dst:
                        shutil.copyfileobj(src, dst, 1 << 20)
                    destination.chmod(0o600)
                    if digest(destination) != m["files"][row["file"]]["sha256"]:
                        raise ValueError("Snapshot checksum mismatch")
                    with contextlib.closing(
                        sqlite3.connect(destination.as_uri() + "?mode=ro", uri=True)
                    ) as db:
                        if db.execute("pragma quick_check").fetchone()[0] != "ok":
                            raise ValueError("Snapshot database integrity check failed")
                    context = {
                        "state": str(services / key),
                        "state_dir": str(state_root),
                        "client_dir": str(Path(assets).resolve()),
                        "endpoint": endpoint,
                        "model": row["model"],
                        "project": str(Path(project or row["project"]).resolve()),
                        "project_overrides": {
                            **{
                                old: str(Path(project).resolve())
                                if project is not None and target == row["project"]
                                else target
                                for old, target in row.get("project_overrides", {}).items()
                            },
                            **(
                                {row["project"]: str(Path(project).resolve())}
                                if project is not None
                                else {}
                            ),
                        },
                    }
                    atomic_json(folder / "connection.json", context)
                    restored.append(
                        {"source_id": row["id"], "history_id": key, "project": context["project"]}
                    )
                value = json.loads(json.dumps(old_binding))
                preferred = next(
                    (r["history_id"] for r in restored if r["source_id"] == m.get("selected")),
                    restored[0]["history_id"],
                )
                if choose or history.selected_key(value) is None:
                    value["active"] = preferred
                for row in restored:
                    value.setdefault("connections", {})[row["history_id"]] = [endpoint]
                result = {
                    "state": "restored",
                    "histories": restored,
                    "selected": value.get("active"),
                    "database_merged": False,
                    "jobs_restored": False,
                    "archive_sha256": identity,
                }
                moved = []
                try:
                    for row in restored:
                        key = row["history_id"]
                        (temporary / key).rename(services / key)
                        moved.append(services / key)
                    imports[identity] = result
                    atomic_json(imports_path, imports)
                    atomic_json(history.binding_path(state_root), value)
                except BaseException:
                    imports.pop(identity, None)
                    atomic_json(imports_path, imports)
                    atomic_json(history.binding_path(state_root), old_binding)
                    for path in moved:
                        shutil.rmtree(path)
                    raise
                return result


def restore(state_root, archive, assets, endpoint, choose=False, project=None):
    try:
        return _restore(state_root, archive, assets, endpoint, choose, project)
    except (zipfile.BadZipFile, sqlite3.Error, KeyError, TypeError, AttributeError) as error:
        raise ValueError("Invalid history snapshot: " + type(error).__name__) from error
