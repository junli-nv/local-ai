"""Manage client defaults without installing resources or contacting a service."""

from .common import atomic_json
from .endpoint import endpoint_url
from .paths import root, settings

KEYS = ("endpoint", "model")


def show():
    current = settings()
    return {
        "file": str(root() / "installation.json"),
        "endpoint": current.get("endpoint"),
        "model": current.get("model"),
    }


def update(key, value=None, remove=False):
    if key not in KEYS:
        raise ValueError("Configuration key must be endpoint or model")
    if not remove:
        if key == "endpoint":
            value = endpoint_url(value)
        elif not isinstance(value, str) or not value.strip():
            raise ValueError("Model ID must be a nonempty string")
    current = dict(settings())
    if remove:
        current.pop(key, None)
    else:
        current[key] = value
    atomic_json(root() / "installation.json", current, mode=0o644)
    return show()
