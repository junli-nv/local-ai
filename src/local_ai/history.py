"""User-local history identity independent of inference endpoints and installations."""

import contextlib
import fcntl
import json
import re
import sqlite3
import tempfile
from pathlib import Path

from .common import atomic_json, fingerprint, private_dir
from .endpoint import endpoint_url
from .paths import root


def installation_key():
    return fingerprint(str(root()))[:20]


def endpoint_key(endpoint):
    return fingerprint({"endpoint": endpoint_url(endpoint)})[:20]


def binding_path(state_root):
    return Path(state_root) / "history-bindings.json"


def load(state_root):
    path = binding_path(state_root)
    value = (
        json.loads(path.read_text())
        if path.exists()
        else {"version": 1, "defaults": {}, "endpoints": {}}
    )
    if not isinstance(value, dict) or value.get("version") != 1:
        raise ValueError("Unsupported history binding format")
    for field in ("defaults", "endpoints"):
        mapping = value.get(field)
        if not isinstance(mapping, dict) or any(
            not isinstance(k, str) or not isinstance(v, str) or not re.fullmatch(r"[0-9a-f]{20}", v)
            for k, v in mapping.items()
        ):
            raise ValueError("Invalid history binding keys")
    active = value.get("active")
    if active is not None and (
        not isinstance(active, str) or not re.fullmatch(r"[0-9a-f]{20}", active)
    ):
        raise ValueError("Invalid active history identity")
    connections = value.get("connections", {})
    if not isinstance(connections, dict) or any(
        not re.fullmatch(r"[0-9a-f]{20}", key)
        or not isinstance(addresses, list)
        or any(not isinstance(address, str) for address in addresses)
        for key, addresses in connections.items()
    ):
        raise ValueError("Invalid history connection records")
    return value


def selected_key(value):
    if value.get("active"):
        return value["active"]
    legacy = set(value["defaults"].values())
    if len(legacy) == 1:
        return next(iter(legacy))
    if not legacy:
        return None
    if installation_key() in value["defaults"]:
        return value["defaults"][installation_key()]
    raise ValueError(
        "Multiple legacy histories found; inspect client history list before selecting one"
    )


@contextlib.contextmanager
def locked(state_root):
    directory = private_dir(state_root)
    with (directory / ".history.lock").open("a") as stream:
        fcntl.flock(stream, fcntl.LOCK_EX)
        yield


def session_count(state):
    data = Path(state) / "data/opencode"
    db = data / "opencode.db"
    if db.exists():
        try:
            with contextlib.closing(
                sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True, timeout=3)
            ) as connection:
                return connection.execute("select count(*) from session").fetchone()[0]
        except sqlite3.Error as error:
            raise ValueError("Cannot safely inspect target history: " + str(db)) from error
    return sum(1 for _ in (data / "storage/session").rglob("*.json"))


def resolve(state_root, endpoint, default_endpoint=None):
    value = load(state_root)
    selected = selected_key(value)
    if selected:
        return selected
    base = endpoint_url(default_endpoint or endpoint)
    legacy = value["endpoints"].get(base, endpoint_key(base))
    if session_count(Path(state_root) / "services" / legacy):
        return legacy
    return fingerprint({"history": "user-default"})[:20]


def remember_history(state_root, endpoint, key, default_endpoint=None):
    with locked(state_root):
        value = load(state_root)
        if resolve(state_root, endpoint, default_endpoint) != key:
            raise ValueError("History selection changed during startup; retry chat")
        updated = json.loads(json.dumps(value))
        updated["active"] = key
        connections = updated.setdefault("connections", {})
        connections[key] = sorted(set(connections.get(key, [])) | {endpoint_url(endpoint)})
        if updated != value:
            atomic_json(binding_path(state_root), updated)


def _plan(options):
    from .profiles import client_options
    from .resume import context_for

    state_root = Path(options.state_dir).expanduser().resolve()
    old, new = endpoint_url(options.old_endpoint), endpoint_url(options.endpoint)
    if old == new:
        raise ValueError("Source and destination endpoints must differ")
    value = load(state_root)
    source_key = value["endpoints"].get(old, endpoint_key(old))
    target_key = value["endpoints"].get(new, endpoint_key(new))
    source = state_root / "services" / source_key
    target = state_root / "services" / target_key
    count = session_count(source)
    if not count:
        raise ValueError("No sessions found for the source endpoint")
    if source_key != target_key and session_count(target):
        raise ValueError(
            "Destination already contains sessions; refusing to hide or overwrite them"
        )
    context = context_for(source)
    if not context:
        raise ValueError("Source connection metadata not found")
    model = getattr(options, "model", None) or context["model"]
    updated_context = {
        **context,
        "state": str(source),
        "state_dir": str(state_root),
        "endpoint": new,
        "model": model,
        "client_options": client_options(model),
    }
    updated = json.loads(json.dumps(value))
    updated["endpoints"].update({old: source_key, new: source_key})
    updated["active"] = source_key
    connections = updated.setdefault("connections", {})
    connections[source_key] = sorted(set(connections.get(source_key, [])) | {old, new})
    result = {
        "old_endpoint": old,
        "endpoint": new,
        "history_directory": str(source),
        "sessions": count,
        "database_copied": False,
        "history_selected": True,
        "changed": updated != value or updated_context != context,
    }
    return state_root, source, updated, updated_context, result


def update_endpoint(options):
    if getattr(options, "dry_run", False):
        return {**_plan(options)[-1], "dry_run": True}
    state_root = Path(options.state_dir).expanduser().resolve()
    if not state_root.is_dir():
        raise ValueError("Client state directory does not exist")
    with locked(state_root):
        state_root, source, value, context, result = _plan(options)
        if not result["changed"]:
            return result
        destination = binding_path(state_root)
        connection = source / "connection.json"
        originals = {
            path: path.read_bytes() if path.exists() else None for path in (destination, connection)
        }
        backup = Path(
            tempfile.mkdtemp(
                prefix="update-endpoint-", dir=private_dir(state_root / "endpoint-backups")
            )
        )
        for path, data in originals.items():
            if data is not None:
                file = backup / path.name
                file.write_bytes(data)
                file.chmod(0o600)
        atomic_json(backup / "plan.json", result)
        try:
            atomic_json(connection, context)
            atomic_json(destination, value)
        except BaseException:
            for path, data in originals.items():
                if data is None:
                    path.unlink(missing_ok=True)
                else:
                    atomic_json(path, json.loads(data))
            raise
        return {**result, "backup_directory": str(backup)}


def current_context(context, settings):
    selected = selected_key(load(context["state_dir"]))
    if selected and selected != Path(context["state"]).name:
        raise ValueError(
            "Session belongs to another legacy history; inspect client history list before selecting it"
        )
    if selected:
        if not settings.get("endpoint"):
            raise ValueError(
                "Set the current endpoint with config set endpoint, or use chat --endpoint URL --session ID"
            )
        return {
            **context,
            "endpoint": endpoint_url(settings["endpoint"]),
            "model": settings.get("model") or context["model"],
        }
    return context


def list_histories(state_root, default_endpoint=None):
    """List local connection metadata and counts without contacting any server."""
    from .resume import context_for

    state_root = Path(state_root).expanduser().resolve()
    value = load(state_root)
    try:
        selected = selected_key(value)
    except ValueError:
        selected = None
    if selected is None and default_endpoint:
        base = endpoint_url(default_endpoint)
        selected = value["endpoints"].get(base, endpoint_key(base))
    services = state_root / "services"
    states = {p for p in services.glob("*") if p.is_dir()}
    states.update(services / key for key in value["endpoints"].values())
    states.update(services / key for key in value["defaults"].values())
    states.update(services / key for key in value.get("connections", {}))
    if value.get("active"):
        states.add(services / value["active"])
    result = []
    for state in sorted(states):
        item = {
            "history_directory": str(state),
            "history_id": state.name,
            "endpoints": sorted(
                {k for k, v in value["endpoints"].items() if v == state.name}
                | set(value.get("connections", {}).get(state.name, []))
            ),
            "sessions": None,
            "default": state.name == selected,
            "model": None,
            "error": None,
        }
        try:
            if not state.is_dir():
                raise ValueError("History directory is missing")
            context = context_for(state)
            if context:
                item["model"] = context.get("model")
                if context.get("endpoint"):
                    item["endpoints"] = sorted(
                        set(item["endpoints"]) | {endpoint_url(context["endpoint"])}
                    )
            item["sessions"] = session_count(state)
        except (OSError, ValueError) as error:
            item["error"] = str(error)
        result.append(item)
    return result
