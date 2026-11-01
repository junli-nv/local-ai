"""Paths follow the unpacked program directory, never the terminal cwd."""

import json
import os
from pathlib import Path


def root():
    return (
        Path(os.environ.get("LOCAL_AI_ROOT", Path(__file__).resolve().parents[2]))
        .expanduser()
        .resolve()
    )


def data_root():
    return Path(os.environ.get("LOCAL_AI_DATA_DIR", root())).expanduser().resolve()


def settings():
    for name in ["installation.json", "bundle.json"]:
        path = root() / name
        if path.is_file():
            try:
                value = json.loads(path.read_text())
            except ValueError as error:
                raise ValueError(
                    "Invalid JSON settings file " + str(path) + ": " + str(error)
                ) from error
            if not isinstance(value, dict):
                raise ValueError("Settings must be a JSON object: " + str(path))
            value = value.get("installation", value)
            if not isinstance(value, dict):
                raise ValueError("Installation settings must be a JSON object: " + str(path))
            for key in ("endpoint", "model"):
                if value.get(key) is not None and not isinstance(value[key], str):
                    raise ValueError(key + " must be a string in settings file " + str(path))
            return value
    return {}


def client_assets(cpu):
    return root() / "clients" / cpu
