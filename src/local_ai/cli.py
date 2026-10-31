"""User-facing commands. GPU operations never run as part of chat."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import artifacts, client, images, server
from .common import arch, client_home
from .profiles import catalog, profile


def parser():
    a = argparse.ArgumentParser(
        prog="local-ai", description="GPU inference server + BCM headnode OpenCode client"
    )
    a.add_argument("--debug", action="store_true")
    groups = a.add_subparsers(dest="group", required=True)
    groups.add_parser("profiles", help="Show hardware profiles and validation levels")
    gpu = groups.add_parser("server").add_subparsers(dest="action", required=True)
    gpu.add_parser("inventory")
    for action in ["plan", "start", "status", "stop"]:
        b = gpu.add_parser(action)
        b.add_argument(
            "--data-dir",
            type=Path,
            default=Path(os.environ.get("LOCAL_AI_DATA_DIR", "/raid/local-ai")),
        )
        b.add_argument("--name", default="a")
        if action in ["plan", "start"]:
            b.add_argument("--profile", default="b300-tp4", choices=list(catalog()["profiles"]))
            b.add_argument("--gpus", required=True, help="Host GPU indices or full UUIDs")
            b.add_argument("--port", type=int, default=18000)
            if action == "plan":
                b.add_argument(
                    "--inventory", type=Path, help="JSON fixture; never accepted by start"
                )
    image = groups.add_parser("image").add_subparsers(dest="action", required=True)
    for action in ["pull", "export", "import"]:
        b = image.add_parser(action)
        b.add_argument("--profile", required=True, choices=list(catalog()["profiles"]))
        b.add_argument(
            "--data-dir",
            type=Path,
            default=Path(os.environ.get("LOCAL_AI_DATA_DIR", "/raid/local-ai")),
        )
        if action == "export":
            b.add_argument("--output", type=Path, required=True)
        if action == "import":
            b.add_argument("--archive", type=Path, required=True)
            b.add_argument("--lock", type=Path, required=True)
    model = groups.add_parser("model").add_subparsers(dest="action", required=True)
    b = model.add_parser("download")
    b.add_argument("--profile", default="b300-tp4", choices=list(catalog()["profiles"]))
    b.add_argument(
        "--data-dir", type=Path, default=Path(os.environ.get("LOCAL_AI_DATA_DIR", "/raid/local-ai"))
    )
    clients = groups.add_parser("client").add_subparsers(dest="action", required=True)
    for action in ["install", "export", "doctor"]:
        b = clients.add_parser(action)
        b.add_argument("--client-dir", type=Path, default=client_home() / "clients" / arch())
        if action == "install":
            b.add_argument("--binary", type=Path)
            b.add_argument("--seed-cache", type=Path)
            b.add_argument("--version", default=artifacts.VERSION)
            b.add_argument("--sha256", help="Expected checksum for imported binary")
        if action == "export":
            b.add_argument("--output", type=Path, required=True)
    b = groups.add_parser("chat", help="Run on BCM; SSH tunnel to a GPU server")
    connection = b.add_mutually_exclusive_group(required=True)
    connection.add_argument("--server", help="GPU server SSH hostname or user@hostname")
    connection.add_argument(
        "--endpoint", help="Use an already reachable OpenAI base URL instead of SSH"
    )
    b.add_argument("--ssh-user")
    b.add_argument("--ssh-port", type=int, default=22)
    b.add_argument("--port", type=int, default=18000, help="GPU server API port")
    b.add_argument(
        "--local-port", type=int, default=0, help="Local tunnel port; 0 chooses a free port"
    )
    b.add_argument("--client-dir", type=Path, default=client_home() / "clients" / arch())
    b.add_argument("--state-dir", type=Path, default=client_home())
    b.add_argument("--project", type=Path, default=Path.cwd())
    b.add_argument("--model", default=catalog()["model"]["served_name"])
    b.add_argument(
        "--check", action="store_true", help="Check connection, then close tunnel without chatting"
    )
    b.add_argument("--run", help="One prompt; stream JSON events, save full logs, then exit")
    return a


def dispatch(q):
    if q.group == "profiles":
        return catalog()["profiles"]
    if q.group == "server":
        if q.action == "inventory":
            return server.inventory()
        if q.action == "status":
            return server.status(q.name)
        if q.action == "stop":
            return server.stop(q.data_dir, q.name)
        policy = profile(q.profile)
        hardware = (
            json.loads(q.inventory.read_text())
            if q.action == "plan" and q.inventory
            else server.inventory()
        )
        value = server.plan(q.data_dir, policy, q.gpus, q.name, q.port, hardware)
        return value if q.action == "plan" else server.start(value, policy)
    if q.group == "image":
        policy = profile(q.profile)
        if q.action == "pull":
            return images.pull(q.data_dir, policy)
        if q.action == "export":
            return images.export_image(q.data_dir, policy, q.output)
        return images.import_image(q.data_dir, policy, q.archive, q.lock)
    if q.group == "model":
        return images.download_model(q.data_dir, profile(q.profile))
    if q.group == "client":
        if q.action == "install":
            return artifacts.install(q.client_dir, q.binary, q.seed_cache, q.version, q.sha256)
        if q.action == "export":
            return artifacts.export_client(q.client_dir, q.output)
        tools = {name: shutil.which(name) for name in ["python3", "git", "ssh", "rg", "script"]}
        return {
            "ready": all(tools.values()),
            "arch": arch(),
            "tools": tools,
            "client": artifacts.validate(q.client_dir),
        }
    if q.group == "chat":
        return client.chat(q)
    raise ValueError("Unsupported command")


def main(argv=None):
    q = parser().parse_args(argv)
    try:
        value = dispatch(q)
        if isinstance(value, int):
            return value
        print(json.dumps(value, indent=2))
        if q.group == "client" and q.action == "doctor" and not value["ready"]:
            return 1
        return 0
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        if q.debug:
            raise
        print("ERROR: " + str(error), file=sys.stderr)
        return 1
