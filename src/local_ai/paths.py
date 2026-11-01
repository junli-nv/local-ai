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
            value = json.loads(path.read_text())
            return value.get("installation", value)
    return {}


def client_assets(cpu):
    return root() / "clients" / cpu
