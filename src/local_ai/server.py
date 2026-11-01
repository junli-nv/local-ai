"""GPU-host operations. Planning is pure when inventory is supplied."""

import csv
import fcntl
import ipaddress
import json
import re
import socket
from pathlib import Path

from . import readiness
from .common import arch, atomic_json, fingerprint, run
from .images import resolve_image
from .profiles import engine_args, legacy_environment, legacy_model_identity, select_gpus


def inventory():
    r = run(
        [
            "nvidia-smi",
            "--query-gpu=index,uuid,name,pci.bus_id,memory.total",
            "--format=csv,noheader,nounits",
        ]
    )
    gpus = []
    for row in csv.reader(r.stdout.splitlines()):
        gpus.append(
            {
                "index": int(row[0]),
                "uuid": row[1].strip(),
                "name": row[2].strip(),
                "pci": row[3].strip(),
                "memory_mib": int(row[4]),
            }
        )
    return {"arch": arch(), "gpus": gpus}


def inspect_container(name):
    r = run(["docker", "inspect", name], check=False)
    return json.loads(r.stdout)[0] if r.returncode == 0 else None


def listen_address(host):
    try:
        address = ipaddress.IPv4Address(host)
    except ipaddress.AddressValueError as error:
        raise ValueError(
            "Host must be an IPv4 listen address, for example 127.0.0.1 or 0.0.0.0"
        ) from error
    if address.is_multicast or str(address) == "255.255.255.255":
        raise ValueError("Host must be a unicast IPv4 address or 0.0.0.0")
    return str(address)


def check_port(host, port):
    with socket.socket() as sock:
        try:
            sock.bind((host, port))
        except OSError as error:
            raise RuntimeError(
                "Cannot bind model API at %s:%s: %s" % (host, port, error)
            ) from error


def plan(root, policy, gpus, name, port, hardware, host="127.0.0.1"):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", name):
        raise ValueError("Invalid instance name")
    if not 1024 <= port <= 65535:
        raise ValueError("Port must be 1024..65535")
    host = listen_address(host)
    chosen = select_gpus(hardware, gpus, policy)
    root = Path(root).expanduser().resolve()
    spec = {
        "data_dir": str(root),
        "profile": policy["name"],
        "platform": policy["platform"],
        "instance": name,
        "container": "local-ai-" + name,
        "port": port,
        "image": policy["image"],
        "gpus": [g["uuid"] for g in chosen],
        "args": engine_args(policy, port, host),
    }
    identity = {key: policy[key] for key in ["repo", "revision"]}
    if identity != legacy_model_identity():
        spec["model_identity"] = identity
    if policy.get("environment", {}) != legacy_environment():
        spec["environment"] = policy.get("environment", {})
    # Preserve the existing default deployment fingerprint.
    if host != "127.0.0.1":
        spec["host"] = host
    inst = root / "instances" / name
    labels = {
        "local-ai.project": "cluster-local-ai",
        "local-ai.data-dir": str(root),
        "local-ai.instance": name,
        "local-ai.gpus": ",".join(spec["gpus"]),
        "local-ai.port": str(port),
        "local-ai.spec": fingerprint(spec),
    }
    command = ["docker", "run", "-d", "--name", spec["container"], "--platform", policy["platform"]]
    for key, value in labels.items():
        command += ["--label", key + "=" + value]
    command += ["--network", "host", "--ipc", "host", "--ulimit", "memlock=-1"]
    for gpu in spec["gpus"]:
        command += ["--device", "nvidia.com/gpu=" + gpu]
    for source, target, ro in [
        (root / "models", "/models", True),
        (inst, "/instance", False),
        (inst / "cache", "/root/.cache", False),
    ]:
        command += [
            "--mount",
            "type=bind,src=" + str(source) + ",dst=" + target + (",readonly" if ro else ""),
        ]
    for value in [
        "HF_HUB_OFFLINE=1",
        "TRANSFORMERS_OFFLINE=1",
        "PYTHONUNBUFFERED=1",
        "VLLM_ENGINE_READY_TIMEOUT_S=3600",
        "NCCL_SOCKET_IFNAME=lo",
        "GLOO_SOCKET_IFNAME=lo",
        "CUDA_VISIBLE_DEVICES=" + ",".join(spec["gpus"]),
    ]:
        command += ["-e", value]
    for key, value in policy.get("environment", {}).items():
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", key):
            raise ValueError("Invalid engine environment name: " + key)
        command += ["-e", key + "=" + str(value)]
    entry = "import os,json,datetime; f=open('/instance/server.log','a',buffering=1); f.write('\\nSTART '+datetime.datetime.now().isoformat()+'\\n'); os.dup2(f.fileno(),1); os.dup2(f.fileno(),2); os.execvp('vllm',['vllm']+json.load(open('/instance/args.json')))"
    command += ["--entrypoint", "python3", policy["image"], "-c", entry]
    return {
        "spec": spec,
        "selected_devices": chosen,
        "command": command,
        "validation": policy["validation"],
        "notes": [
            policy.get("host_memory_note", ""),
            "Planning does not allocate GPUs or check current port/GPU occupancy.",
        ],
    }


def validate_model(root, policy):
    model = Path(root) / "models" / policy["model_directory"]
    for name in ["config.json", "tokenizer.json"]:
        if not (model / name).is_file():
            raise ValueError("Missing model file: " + str(model / name))
    json.loads((model / "config.json").read_text())
    json.loads((model / "tokenizer.json").read_text())
    indices = list(model.glob("*.safetensors.index.json"))
    if len(indices) != 1:
        raise ValueError("Expected one safetensors index in " + str(model))
    index = json.loads(indices[0].read_text())
    weights = index.get("weight_map") if isinstance(index, dict) else None
    if not isinstance(weights, dict) or not weights:
        raise ValueError("Empty safetensors weight index")
    if not all(isinstance(name, str) for name in weights.values()):
        raise ValueError("Invalid weight shard name in index")
    for name in set(weights.values()):
        if not isinstance(name, str):
            raise ValueError("Invalid weight shard name in index")
        relative = Path(name)
        if relative.is_absolute() or ".." in relative.parts:
            raise ValueError("Unsafe weight index path")
        f = model / relative
        if not f.is_file() or f.stat().st_size == 0:
            raise ValueError("Missing weight shard: " + str(f))
        if not f.resolve().is_relative_to(model.resolve()):
            raise ValueError("Unsafe weight shard symlink: " + str(f))
        with f.open("rb") as stream:
            header = stream.read(8)
            size = int.from_bytes(header, "little")
            if len(header) != 8 or not 2 <= size <= min(100_000_000, f.stat().st_size - 8):
                raise ValueError("Invalid or truncated safetensors header: " + str(f))
            tensors = json.loads(stream.read(size))
        if not isinstance(tensors, dict):
            raise ValueError("Invalid safetensors header object: " + str(f))
        ends = []
        for key, entry in tensors.items():
            if key == "__metadata__":
                continue
            offsets = entry.get("data_offsets") if isinstance(entry, dict) else None
            if (
                not isinstance(offsets, list)
                or len(offsets) != 2
                or not all(isinstance(x, int) for x in offsets)
            ):
                raise ValueError("Invalid tensor offsets: " + str(f))
            start, end = offsets
            if not 0 <= start <= end:
                raise ValueError("Invalid tensor offsets: " + str(f))
            ends.append(end)
        if not ends or max(ends) + size + 8 != f.stat().st_size:
            raise ValueError("Truncated or oversized weight shard: " + str(f))
    return model


def conflicts(spec, containers, compute):
    selected = set(spec["gpus"])
    for c in containers:
        labels = c["Config"].get("Labels") or {}
        if c["State"]["Running"] and selected & set(labels.get("local-ai.gpus", "").split(",")):
            raise RuntimeError("GPU assignment overlaps " + c["Name"])
        if c["State"]["Running"] and labels.get("local-ai.port") == str(spec["port"]):
            raise RuntimeError("API port already assigned to " + c["Name"])
    busy = [row for row in compute if row and row[0].strip() in selected]
    if busy:
        raise RuntimeError("Selected GPUs have compute processes: " + str(busy))


def start(value, policy):
    spec = value["spec"]
    root = Path(spec["data_dir"])
    inst = root / "instances" / spec["instance"]
    validate_model(root, policy)
    check_host_memory(policy)
    aliases = set(run(["nvidia-ctk", "cdi", "list"]).stdout.splitlines())
    for gpu in spec["gpus"]:
        if "nvidia.com/gpu=" + gpu not in aliases:
            raise RuntimeError(
                "Missing local CDI UUID alias: "
                + gpu
                + ". On this GPU host, run nvidia-ctk cdi list; refresh definitions with sudo systemctl restart nvidia-cdi-refresh.service, then verify the selected UUID aliases. See the deployment guide for hosts without that service."
            )
    reference = resolve_image(root, policy)
    command = list(value["command"])
    command[command.index(policy["image"])] = reference
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".deploy.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        old = inspect_container(spec["container"])
        if old:
            labels = old["Config"].get("Labels") or {}
            if labels.get("local-ai.project") != "cluster-local-ai" or labels.get(
                "local-ai.spec"
            ) != fingerprint(spec):
                raise RuntimeError(
                    "Existing container differs or is unmanaged; inspect it and replace it explicitly"
                )
            if (
                not (inst / "args.json").is_file()
                or json.loads((inst / "args.json").read_text()) != spec["args"]
            ):
                raise RuntimeError(
                    "Managed args.json drift detected; explicit replacement required"
                )
            if old["State"]["Running"]:
                return {"state": "already-running", "container": spec["container"]}
        ids = run(
            ["docker", "ps", "-q", "--filter", "label=local-ai.project=cluster-local-ai"]
        ).stdout.split()
        others = [inspect_container(cid) for cid in ids]
        compute = list(
            csv.reader(
                run(
                    ["nvidia-smi", "--query-compute-apps=gpu_uuid,pid", "--format=csv,noheader"]
                ).stdout.splitlines()
            )
        )
        conflicts(spec, [c for c in others if c], compute)
        check_port(spec.get("host", "127.0.0.1"), spec["port"])
        (inst / "cache").mkdir(parents=True, exist_ok=True)
        atomic_json(inst / "args.json", spec["args"])
        atomic_json(inst / "spec.json", spec)
        atomic_json(inst / "docker-command.json", command)
        r = run(
            ["docker", "start", spec["container"]] if old else command, check=False, timeout=None
        )
        (inst / "launch.log").write_text(r.stdout + r.stderr)
        if r.returncode:
            raise RuntimeError("Container launch failed; see " + str(inst / "launch.log"))
    return {
        "state": "started-not-yet-ready",
        "container": spec["container"],
        "health": "http://%s:%d/health"
        % (
            "127.0.0.1"
            if spec.get("host", "127.0.0.1") == "0.0.0.0"
            else spec.get("host", "127.0.0.1"),
            spec["port"],
        ),
        "log": str(inst / "server.log"),
    }


def status(name, probe=True):
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,31}", name):
        raise ValueError("Invalid instance name")
    old = inspect_container("local-ai-" + name)
    if old is None:
        raise ValueError("服务尚未就绪（NOT READY）：实例不存在 / container not found")
    value = {"container": old["Name"], "state": old["State"], "labels": old["Config"].get("Labels")}
    if not probe:
        return value
    labels = value["labels"] or {}
    value.update(
        ready=False,
        listening=False,
        health=None,
        log=None,
        detail="容器未运行 / container not running",
    )
    if labels.get("local-ai.project") != "cluster-local-ai" or not labels.get("local-ai.data-dir"):
        value["detail"] = "不是 local-ai 管理的实例 / unmanaged container"
    else:
        inst = Path(labels["local-ai.data-dir"]) / "instances" / name
        value["log"] = str(inst / "server.log")
        try:
            spec = json.loads((inst / "spec.json").read_text())
            if spec["container"] != "local-ai-" + name or str(spec["port"]) != labels.get(
                "local-ai.port"
            ):
                raise ValueError("Instance metadata mismatch")
            spec["host"] = listen_address(spec.get("host", "127.0.0.1"))
            spec["port"] = int(spec["port"])
            if not 1024 <= spec["port"] <= 65535:
                raise ValueError("Invalid API port")
            if old["State"].get("Running"):
                value.update(readiness.probe(spec))
        except (OSError, ValueError, KeyError, TypeError) as error:
            value["detail"] = "无法读取实例配置 / invalid instance configuration: " + str(error)
    value["message"] = readiness.message(value)
    return value


def stop(root, name):
    value = status(name, probe=False)
    labels = value["labels"] or {}
    if labels.get("local-ai.project") != "cluster-local-ai" or labels.get(
        "local-ai.data-dir"
    ) != str(Path(root).resolve()):
        raise ValueError("Refusing to stop a container owned by another deployment")
    result = run(["docker", "stop", "--timeout", "60", "local-ai-" + name], timeout=None)
    return {"state": "stopped", "container": result.stdout.strip()}


def check_host_memory(policy, available_gib=None):
    """Conservative offload guard, not a measured minimum RAM claim."""
    minimum = policy.get("min_host_available_gib")
    if minimum is None:
        return
    if available_gib is None:
        values = {}
        for line in Path("/proc/meminfo").read_text().splitlines():
            key, value = line.split(":", 1)
            values[key] = int(value.strip().split()[0])
        available_gib = values["MemAvailable"] / (1024 * 1024)
    if available_gib < minimum:
        raise ValueError(
            "CPU Engram offload requires at least %s GiB MemAvailable in this profile; available %.1f GiB"
            % (minimum, available_gib)
        )
