"""Hardware policy and deterministic vLLM argument construction."""

import json
from importlib.resources import files

from .common import arch


def catalog():
    return json.loads(files("local_ai").joinpath("profiles.json").read_text())


def profile(name):
    data = catalog()
    if name not in data["profiles"]:
        raise ValueError("Unknown profile: " + name)
    return {**data["model"], **data["profiles"][name], "name": name}


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


def engine_args(policy, port):
    return [
        "serve",
        "/models/" + policy["model_directory"],
        "--served-model-name",
        policy["served_name"],
        "--host",
        "127.0.0.1",
        "--port",
        str(port),
        "--tensor-parallel-size",
        str(policy["tp"]),
        "--tokenizer-mode",
        "deepseek_v41",
        "--tool-call-parser",
        "deepseek_v41",
        "--reasoning-parser",
        "deepseek_v41",
        "--enable-auto-tool-choice",
        "--max-model-len",
        "131072",
        "--max-num-seqs",
        "4",
        "--max-num-batched-tokens",
        "8192",
        "--gpu-memory-utilization",
        "0.80",
        "--kv-cache-dtype",
        "fp8",
        "--attention-config",
        json.dumps(
            {
                "backend": "FLASHINFER_MLA_SPARSE_DSV41",
                "indexer_kv_dtype": "mxfp4",
                "indexer_sparse_logits": True,
            }
        ),
        "--engram-config",
        json.dumps({"cpu_offload": policy["cpu_offload"]}),
        "--kernel-config",
        json.dumps({"enable_flashinfer_autotune": False}),
        "--compilation-config",
        json.dumps(
            {"mode": 0, "cudagraph_mode": "FULL_DECODE_ONLY", "cudagraph_capture_sizes": [1, 2, 4]}
        ),
    ]
