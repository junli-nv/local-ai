"""Hardware policy and deterministic vLLM argument construction."""

import json
import os
import re
from importlib.resources import files
from pathlib import Path

from .common import arch
from .paths import root


def catalog():
    path = os.environ.get("LOCAL_AI_CATALOG")
    if not path and (root() / "config/catalog.json").is_file():
        path = root() / "config/catalog.json"
    text = (
        Path(path).expanduser().read_text()
        if path
        else files("local_ai").joinpath("profiles.json").read_text()
    )
    data = json.loads(text)
    if "models" in data:
        default = data.get("default_model")
        if default not in data["models"]:
            raise ValueError("default_model must name a model in models")
        data["model"] = data["models"][default]
    return data


def profile(name):
    data = catalog()
    if name not in data["profiles"]:
        raise ValueError("Unknown profile: " + name)
    hardware = data["profiles"][name]
    model_key = hardware.get("model", data.get("default_model"))
    if model_key is not None:
        if model_key not in data.get("models", {}):
            raise ValueError("Unknown model recipe: " + str(model_key))
        model = data["models"][model_key]
    else:
        model = data["model"]
    directory = Path(model["model_directory"])
    if directory.is_absolute() or ".." in directory.parts or str(directory) in {"", "."}:
        raise ValueError("model_directory must be a relative directory below models")
    options = {**model.get("engine_options", {}), **hardware.get("engine_options", {})}
    return {**model, **hardware, "engine_options": options, "name": name}


def legacy_environment():
    # Historical launch environment: preserve old default instance fingerprints.
    bundled = json.loads(files("local_ai").joinpath("profiles.json").read_text())
    return bundled["legacy_environment"]


def legacy_model_identity():
    # Migration metadata, not an allowlist of model releases.
    bundled = json.loads(files("local_ai").joinpath("profiles.json").read_text())
    return bundled["legacy_model_identity"]


def client_options(served_name):
    data = catalog()
    models = data.get("models", {"default": data["model"]})
    for model in models.values():
        if model["served_name"] == served_name:
            return model.get("client", {})
    return {}


def select_gpus(inventory, selectors, policy):
    by_index = {str(g["index"]): g for g in inventory["gpus"]}
    by_uuid = {g["uuid"]: g for g in inventory["gpus"]}
    chosen = []
    for token in selectors.split(","):
        key = token.strip()
        gpu = by_index.get(key) or by_uuid.get(key)
        if gpu is None:
            raise ValueError("GPU not found: " + key)
        chosen.append(gpu)
    if len(chosen) != policy["tp"] or len({g["uuid"] for g in chosen}) != len(chosen):
        raise ValueError("Select exactly %d distinct local GPUs" % policy["tp"])
    if arch(inventory["arch"]) != policy["arch"]:
        raise ValueError("Profile CPU architecture does not match this server")
    if any(g["memory_mib"] < policy["min_vram_mib"] for g in chosen):
        raise ValueError("Selected GPU has less HBM than this profile permits")
    for gpu in chosen:
        if not any(name in gpu["name"].upper() for name in policy["gpu_names"]):
            raise ValueError("GPU model does not match profile: " + gpu["name"])
    return chosen


def engine_args(policy, port, host="127.0.0.1"):
    args = [
        "serve",
        "/models/" + policy["model_directory"],
        "--served-model-name",
        policy["served_name"],
        "--host",
        host,
        "--port",
        str(port),
        "--tensor-parallel-size",
        str(policy["tp"]),
    ]
    reserved = {"--model", "--served-model-name", "--host", "--port", "--tensor-parallel-size"}
    for flag, value in policy.get("engine_options", {}).items():
        if not re.fullmatch(r"--[a-z][a-z0-9-]*", flag) or flag in reserved:
            raise ValueError("Invalid or reserved engine option: " + flag)
        if value is False or value is None:
            continue
        args.append(flag)
        if value is not True:
            args.append(json.dumps(value) if isinstance(value, (dict, list)) else str(value))
    return args
