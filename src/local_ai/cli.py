"""User-facing commands. GPU operations never run as part of chat."""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

from . import artifacts, client, images, installlog, server
from .common import arch, client_home
from .profiles import catalog, profile


class CommandParser(argparse.ArgumentParser):
    """Use consistent default-value help at every command level."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("formatter_class", argparse.ArgumentDefaultsHelpFormatter)
        super().__init__(*args, **kwargs)


def parser():
    a = CommandParser(
        prog="local-ai",
        description="GPU inference server + BCM-local OpenCode client. Example hosts: GPU001 / bcm-headnode.",
        epilog="Manual in source checkout: docs/commands.md (Chinese), docs/en/commands.md (English). "
        "Online: https://github.com/junli-nv/local-ai/blob/main/docs/commands.md. "
        "Use COMMAND --help or GROUP COMMAND --help for options.",
    )
    a.add_argument(
        "--debug",
        action="store_true",
        help="Show a Python traceback on failure; place before the command group",
    )
    a.add_argument(
        "--install-log",
        type=Path,
        help="Append installation/deployment steps to this file; default DATA_DIR/install.log or CLIENT_DIR/install.log; put before the command group",
    )
    groups = a.add_subparsers(dest="group", required=True)
    groups.add_parser("profiles", help="Show hardware profiles and validation levels")
    gpu = groups.add_parser(
        "server",
        help="GPU001: inspect, plan, start, query or stop inference instances",
        description="GPU001: inspect, plan, start, query or stop inference instances",
    ).add_subparsers(dest="action", required=True)
    gpu.add_parser(
        "inventory",
        help="Show this server CPU architecture and GPU inventory",
        description="Run on GPU001. Read hardware inventory without starting a service.",
    )
    for action in ["plan", "start", "status", "stop"]:
        details = {
            "plan": "GPU001: print a plan without starting a container",
            "start": "GPU001: validate resources and start an inference instance",
            "status": "GPU001: show the named container status",
            "stop": "GPU001: stop the named instance and preserve host data",
        }[action]
        b = gpu.add_parser(action, help=details, description=details)
        b.add_argument(
            "--data-dir",
            type=Path,
            default=Path(os.environ.get("LOCAL_AI_DATA_DIR", "/raid/local-ai")),
            help="Server data root for models, image locks, cache and logs; LOCAL_AI_DATA_DIR overrides the fallback",
        )
        b.add_argument(
            "--name", default="a", help="Instance identifier (for example a or b), not a hostname"
        )
        if action in ["plan", "start"]:
            b.add_argument(
                "--profile",
                default="b300-tp4",
                choices=list(catalog()["profiles"]),
                help="Hardware and engine preset; use profiles to list supported values",
            )
            b.add_argument(
                "--gpus",
                required=True,
                help="Comma-separated GPU indices from nvidia-smi on this server, or full UUIDs; count must match the profile",
            )
            b.add_argument(
                "--host",
                default="127.0.0.1",
                help="IPv4 listen address; 0.0.0.0 exposes all IPv4 interfaces for direct endpoint access",
            )
            b.add_argument(
                "--port",
                type=int,
                default=18000,
                help="Model HTTP API port on this GPU server, 1024..65535",
            )
            if action == "plan":
                b.add_argument(
                    "--inventory", type=Path, help="JSON fixture; never accepted by start"
                )
    image = groups.add_parser(
        "image",
        help="GPU preparation host: pull, export or import pinned container images",
        description="GPU preparation host: pull, export or import pinned container images",
    ).add_subparsers(dest="action", required=True)
    for action in ["pull", "export", "import"]:
        details = {
            "pull": "Download the profile image and record its platform identity",
            "export": "Save a platform-specific image archive and companion lock",
            "import": "Verify the archive and lock, then load the image",
        }[action]
        b = image.add_parser(action, help=details, description=details)
        if action == "pull":
            b.add_argument(
                "--force",
                action="store_true",
                help="Contact the registry even if a verified local image exists",
            )
        b.add_argument(
            "--profile",
            required=True,
            choices=list(catalog()["profiles"]),
            help="Hardware and engine preset; use profiles to list supported values",
        )
        b.add_argument(
            "--data-dir",
            type=Path,
            default=Path(os.environ.get("LOCAL_AI_DATA_DIR", "/raid/local-ai")),
            help="Server data root for models, image locks, cache and logs; LOCAL_AI_DATA_DIR overrides the fallback",
        )
        if action == "export":
            b.add_argument(
                "--output",
                type=Path,
                required=True,
                help="Destination archive path; companion checksum/lock files are created",
            )
        if action == "import":
            b.add_argument(
                "--archive",
                type=Path,
                required=True,
                help="Local Docker image archive to verify and load",
            )
            b.add_argument(
                "--lock",
                type=Path,
                required=True,
                help="Companion .lock.json from image export; must match the archive",
            )
    model = groups.add_parser(
        "model",
        help="GPU preparation host: download complete pinned model weights",
        description="GPU preparation host: download complete pinned model weights",
    ).add_subparsers(dest="action", required=True)
    b = model.add_parser(
        "download",
        help="Download model config, tokenizer and all weight shards",
        description="Run on a connected preparation host. Download the pinned model into DATA_DIR/models/.",
    )
    b.add_argument(
        "--profile",
        default="b300-tp4",
        choices=list(catalog()["profiles"]),
        help="Hardware and engine preset; use profiles to list supported values",
    )
    b.add_argument(
        "--data-dir",
        type=Path,
        default=Path(os.environ.get("LOCAL_AI_DATA_DIR", "/raid/local-ai")),
        help="Server data root for models, image locks, cache and logs; LOCAL_AI_DATA_DIR overrides the fallback",
    )
    b.add_argument(
        "--force",
        action="store_true",
        help="Refresh model files from the pinned remote revision even if local files are complete",
    )
    clients = groups.add_parser(
        "client",
        help="bcm-headnode: install, inspect or export the native OpenCode client",
        description="bcm-headnode: install, inspect or export the native OpenCode client",
    ).add_subparsers(dest="action", required=True)
    for action in ["install", "export", "doctor"]:
        details = {
            "install": "Install a pinned native client online or from local assets",
            "export": "Export client assets without personal history or credentials",
            "doctor": "Check the client binary and required local tools",
        }[action]
        b = clients.add_parser(action, help=details, description=details)
        b.add_argument(
            "--client-dir",
            type=Path,
            default=client_home() / "clients" / arch(),
            help="Native client asset directory on this BCM host",
        )
        if action == "install":
            b.add_argument(
                "--binary",
                type=Path,
                help="Import this local OpenCode executable instead of downloading it",
            )
            b.add_argument(
                "--seed-cache",
                type=Path,
                help="Import public offline cache assets from this directory",
            )
            b.add_argument(
                "--version",
                default=artifacts.VERSION,
                help="Expected OpenCode version for download or local binary validation",
            )
            b.add_argument("--sha256", help="Expected checksum for imported binary")
        if action == "export":
            b.add_argument(
                "--output",
                type=Path,
                required=True,
                help="Destination archive path; companion checksum/lock files are created",
            )
    b = groups.add_parser(
        "chat",
        help="bcm-headnode: chat using tools on this host",
        description="Run on bcm-headnode. Connect to GPU001 through SSH, or use a direct API endpoint. Tools execute locally as the current user.",
        epilog="Example: ./local-ai chat --server GPU001 --project /home/alice/project",
    )
    connection = b.add_mutually_exclusive_group(required=True)
    connection.add_argument("--server", help="GPU server SSH hostname or user@hostname")
    connection.add_argument(
        "--endpoint", help="Use an already reachable OpenAI base URL instead of SSH"
    )
    b.add_argument(
        "--ssh-user", help="SSH login user; omit to use user@host or existing OpenSSH settings"
    )
    b.add_argument(
        "--ssh-port",
        type=int,
        default=22,
        help="SSH transport port; independent of the model API port",
    )
    b.add_argument("--port", type=int, default=18000, help="GPU server API port")
    b.add_argument(
        "--local-port", type=int, default=0, help="Local tunnel port; 0 chooses a free port"
    )
    b.add_argument(
        "--client-dir",
        type=Path,
        default=client_home() / "clients" / arch(),
        help="Native client asset directory on this BCM host",
    )
    b.add_argument(
        "--state-dir",
        type=Path,
        default=client_home(),
        help="Private client history, cache and session logs on this host",
    )
    b.add_argument(
        "--project",
        type=Path,
        default=Path.cwd(),
        help="Existing project directory on this client host, not on GPU001",
    )
    b.add_argument(
        "--model",
        default=catalog()["model"]["served_name"],
        help="Served model ID; must match the remote API model list",
    )
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
        value = server.plan(q.data_dir, policy, q.gpus, q.name, q.port, hardware, host=q.host)
        return value if q.action == "plan" else server.start(value, policy)
    if q.group == "image":
        policy = profile(q.profile)
        if q.action == "pull":
            return images.pull(q.data_dir, policy, force=q.force)
        if q.action == "export":
            return images.export_image(q.data_dir, policy, q.output)
        return images.import_image(q.data_dir, policy, q.archive, q.lock)
    if q.group == "model":
        return images.download_model(q.data_dir, profile(q.profile), force=q.force)
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
        with installlog.session(q):
            value = dispatch(q)
            if not isinstance(value, int):
                installlog.event("RESULT " + json.dumps(value, ensure_ascii=False))
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
