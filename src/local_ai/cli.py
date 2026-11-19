"""User-facing commands. GPU operations never run as part of chat."""

import argparse
import json
import shlex
import subprocess
import sys
import time
from pathlib import Path

from . import (
    __version__,
    artifacts,
    benchmark,
    bundle,
    client,
    completion,
    configuration,
    deployment,
    diagnostics,
    documents,
    execution,
    history,
    images,
    installlog,
    instructions,
    portability,
    preparation,
    readiness,
    server,
    tasks,
    telemetry,
    video,
    warmup,
    webpage,
    workflows,
)
from .common import arch, client_home
from .paths import client_assets, data_root, root, settings
from .profiles import catalog, profile, require_deployable


class CommandParser(argparse.ArgumentParser):
    """Use consistent default-value help at every command level."""

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("formatter_class", argparse.ArgumentDefaultsHelpFormatter)
        super().__init__(*args, **kwargs)


def instruction_options(command):
    command.add_argument(
        "--instructions",
        choices=["general", "bcm", "none"],
        default="general",
        help="Apply personal rules: general, general plus BCM, or none to leave rules untouched; client roles only",
    )
    command.add_argument(
        "--instructions-language",
        choices=["zh", "en"],
        default="zh",
        help="Installed template language; does not set the assistant response language",
    )


def parser():
    a = CommandParser(
        prog="local-ai",
        description="GPU inference server + BCM-local OpenCode client. Example hosts: GPU001 / bcm-headnode.",
        epilog="Manual in source checkout: docs/commands.md (Chinese), docs/en/commands.md (English). "
        "Online: https://github.com/junli-nv/local-ai/blob/main/docs/commands.md. "
        "Use COMMAND --help or GROUP COMMAND --help for options. "
        'Enable Bash Tab completion: eval "$(./local-ai completion bash)".',
    )
    a.add_argument(
        "--version",
        action="version",
        version="%(prog)s " + __version__,
        help="Show local-ai package version and exit",
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
    b = groups.add_parser(
        "completion",
        help="Print shell completion setup; no files are changed",
        description="Print Bash 3.2+ completion setup to stdout without JSON or installation logs.",
        epilog='Enable in Bash: eval "$(./local-ai completion bash)". '
        "Subcommands, options, choices and local paths are completed without executing commands.",
    )
    b.add_argument("shell", choices=["bash"], help="Shell to generate Tab completion for")
    groups.add_parser(
        "profiles", help="Show hardware profiles, validation levels and planning-only frameworks"
    )
    document = groups.add_parser(
        "document", help="Client host: read rich documents or check conversion tools"
    ).add_subparsers(dest="action", required=True)
    document.add_parser("doctor", help="Show local document converters; no downloads")
    doc = document.add_parser("read", help="Extract document text and/or page images as MCP JSON")
    doc.add_argument("path", type=Path, help="Local file on this client host")
    doc.add_argument(
        "--mode",
        choices=["auto", "text", "render"],
        default="auto",
        help="PDF auto includes page images; Office auto extracts text",
    )
    doc.add_argument("--start", type=int, default=1, help="First page, sheet or slide (one-based)")
    doc.add_argument("--count", type=int, default=3, help="Number of pages/sections, 1..5")
    doc.add_argument("--offset", type=int, default=0, help="Text character offset for continuation")
    web = document.add_parser("web", help="Fetch HTTP(S) text without a browser or login")
    web.add_argument("url", help="HTTP(S) page reachable from this client")
    web.add_argument("--offset", type=int, default=0, help="Text character offset")
    vid = document.add_parser("video", help="Read local subtitles, metadata or sampled frames")
    vid.add_argument("path", type=Path, help="Local video file, at most 4 GiB")
    vid.add_argument(
        "--mode",
        choices=["info", "subtitles", "frames"],
        default="subtitles",
        help="Subtitles by default; info/frames need optional FFmpeg tools",
    )
    vid.add_argument("--start", type=float, default=0, help="Frames: first seek time in seconds")
    vid.add_argument("--count", type=int, default=3, help="Frames: number of samples, 1..5")
    vid.add_argument("--interval", type=float, default=10, help="Frames: spacing in seconds")
    vid.add_argument("--offset", type=int, default=0, help="Subtitles: text character offset")
    config = groups.add_parser(
        "config",
        help="View or change saved client defaults without installing",
        description="Manage defaults in ROOT/installation.json; no downloads or service changes.",
    ).add_subparsers(dest="action", required=True)
    config.add_parser("show", help="Show the settings file and saved endpoint/model")
    b = config.add_parser("set", help="Save a client default; do not install or connect")
    b.add_argument("key", choices=configuration.KEYS, help="Default to change")
    b.add_argument("value", help="Endpoint URL or served model ID")
    b = config.add_parser("unset", help="Remove a saved default")
    b.add_argument("key", choices=configuration.KEYS, help="Default to remove")
    b = groups.add_parser(
        "install", help="Install in this unpacked directory; reuse local bundle assets"
    )
    b.add_argument(
        "--role",
        choices=["server", "client", "both"],
        default=settings().get("role", "client"),
        help="Resources to prepare; first installation defaults to client",
    )
    b.add_argument(
        "--profile",
        choices=list(catalog()["profiles"]),
        default=settings().get("default_profile")
        or (settings().get("profiles") or ["b300-tp4"])[0],
        help="Server model/image recipe; does not allocate or start GPUs",
    )
    b.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Runtime data directory; defaults to the unpacked program root",
    )
    b.add_argument(
        "--endpoint",
        help="Optional initial default API URL; later edit with config set endpoint",
    )
    b.add_argument(
        "--model", help="Client model ID; server installations follow the selected profile"
    )
    b.add_argument(
        "--client-version", help="Optional OpenCode release; reuse local version by default"
    )
    network = b.add_mutually_exclusive_group()
    network.add_argument(
        "--offline",
        dest="offline",
        action="store_true",
        help="Use local files only; fail instead of downloading",
    )
    network.add_argument(
        "--online",
        dest="offline",
        action="store_false",
        help="Allow downloads; extracted bundles otherwise default to offline",
    )
    b.set_defaults(offline=None)
    instruction_options(b)
    b = groups.add_parser(
        "prepare",
        help="Online host: prepare target-platform images and models without running them",
        description="Prepare offline server media on any host CPU architecture; no GPU required.",
    )
    b.add_argument(
        "--profile",
        action="append",
        required=True,
        choices=list(catalog()["profiles"]),
        help="Target server recipe; repeat to prepare multiple platforms",
    )
    b.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Prepared images and models directory; defaults to the program root",
    )
    b.add_argument(
        "--force",
        action="store_true",
        help="Refresh target images and pinned model metadata",
    )
    b = groups.add_parser("export", help="Export a portable complete local-ai directory")
    b.add_argument(
        "--output",
        type=Path,
        default=root() / "dist/local-ai.tar",
        help="Portable archive; defaults to ROOT/dist/local-ai.tar; .tar recommended for large models",
    )
    b.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Existing runtime data to include; program always comes from its own directory",
    )
    b.add_argument(
        "--profile",
        action="append",
        choices=list(catalog()["profiles"]),
        help="Server recipes to include; repeat for multiple recipes; uses installed recipes by default",
    )
    b.add_argument(
        "--client-dir",
        type=Path,
        help="Optional existing native client assets to include from a legacy installation",
    )
    gpu = groups.add_parser(
        "server",
        help="GPU001: inspect, plan, start, benchmark, query or stop inference instances",
        description="GPU001: inspect, plan, start, benchmark, query or stop inference instances",
    ).add_subparsers(dest="action", required=True)
    gpu.add_parser(
        "inventory",
        help="Show this server CPU architecture and GPU inventory",
        description="Run on GPU001. Read hardware inventory without starting a service.",
    )
    for action in ["plan", "start", "status", "stop", "warmup", "benchmark"]:
        details = {
            "plan": "GPU001: print a plan without starting a container; frameworks return deployable=false and command=null",
            "start": "GPU001: validate resources, start an instance and wait for API readiness",
            "status": "GPU001: report whether the named service API is ready",
            "stop": "GPU001: stop the named instance and preserve host data",
            "warmup": "GPU001: explicitly generate bounded synthetic requests to warm inference kernels",
            "benchmark": "GPU001: benchmark a ready managed instance over local HTTP; generates synthetic inference traffic",
        }[action]
        b = gpu.add_parser(action, help=details, description=details)
        b.add_argument(
            "--data-dir",
            type=Path,
            default=data_root(),
            help="Server data root for models, image locks, cache and logs; LOCAL_AI_DATA_DIR overrides the fallback",
        )
        b.add_argument(
            "--name", default="a", help="Instance identifier (for example a or b), not a hostname"
        )
        if action == "benchmark":
            for flag, default, description in [
                ("input-tokens", 1024, "Exact synthetic input tokens per request"),
                (
                    "output-tokens",
                    256,
                    "Exact generated tokens per request, including special tokens",
                ),
                ("concurrency", 1, "Simultaneous requests per round"),
                ("repeats", 3, "Measured rounds; total measured requests = repeats * concurrency"),
                ("warmup-rounds", 1, "Unmeasured warmup rounds at the same shape; 0 skips warmup"),
                ("timeout", 600, "Overall seconds for tokenization, warmup and measured requests"),
            ]:
                b.add_argument("--" + flag, type=int, default=default, help=description)
        if action == "warmup":
            b.add_argument(
                "--timeout",
                type=int,
                default=600,
                help="Overall warmup deadline in seconds; failure leaves the container running",
            )
            b.add_argument(
                "--input-tokens",
                help="Comma-separated exact input lengths; default 1024,8192,32768 where context permits",
            )
            b.add_argument(
                "--concurrency",
                help="Comma-separated simultaneous request counts; default 1,2,4,8 capped at twice max-num-seqs",
            )
            b.add_argument(
                "--output-tokens",
                type=int,
                default=256,
                help="Generated tokens per synthetic request",
            )
            b.add_argument(
                "--repeats", type=int, default=2, help="Passes over the input/concurrency matrix"
            )
        if action in ["plan", "start"]:
            b.add_argument(
                "--profile",
                default=settings().get("default_profile")
                or (settings().get("profiles") or ["b300-tp4"])[0],
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
            if action == "start":
                b.add_argument(
                    "--wait-timeout",
                    type=int,
                    default=600,
                    help="Maximum seconds to wait for API readiness; timeout leaves the container running",
                )
            if action == "start":
                b.add_argument(
                    "--warmup",
                    action="store_true",
                    help="After API readiness, run explicit inference warmup; generates synthetic requests",
                )
                b.add_argument(
                    "--warmup-timeout",
                    type=int,
                    default=600,
                    help="Additional overall warmup deadline in seconds; used only with --warmup",
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
            default=data_root(),
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
        default=settings().get("default_profile")
        or (settings().get("profiles") or ["b300-tp4"])[0],
        choices=list(catalog()["profiles"]),
        help="Hardware and engine preset; use profiles to list supported values",
    )
    b.add_argument(
        "--data-dir",
        type=Path,
        default=data_root(),
        help="Server data root for models, image locks, cache and logs; LOCAL_AI_DATA_DIR overrides the fallback",
    )
    b.add_argument(
        "--force",
        action="store_true",
        help="Refresh model files from the pinned remote revision even if local files are complete",
    )
    clients = groups.add_parser(
        "client",
        help="bcm-headnode: manage clients, inspect tasks and run workflow acceptance",
        description="bcm-headnode: manage clients, inspect tasks and run workflow acceptance",
    ).add_subparsers(dest="action", required=True)
    for action in ["install", "export"]:
        details = {
            "install": "Install a selected native client online or from local assets",
            "export": "Export client assets without personal history or credentials",
        }[action]
        b = clients.add_parser(action, help=details, description=details)
        b.add_argument(
            "--client-dir",
            type=Path,
            default=client_assets(arch()),
            help="Native client asset directory on this BCM host",
        )
        if action == "install":
            instruction_options(b)
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
                default=None,
                help="Select a release; otherwise reuse installed or detect imported version; first online download reference: "
                + artifacts.VERSION,
            )
            b.add_argument("--sha256", help="Expected checksum for imported binary")
        if action == "export":
            b.add_argument(
                "--output",
                type=Path,
                required=True,
                help="Destination archive path; companion checksum/lock files are created",
            )
    jobs = clients.add_parser(
        "job", help="Start, inspect, pause or stop durable local command tasks"
    ).add_subparsers(dest="job_action", required=True)
    for action in [
        "start",
        "adopt",
        "input",
        "list",
        "status",
        "output",
        "pause",
        "resume",
        "stop",
        "remove",
        "pause-session",
        "resume-session",
        "stop-session",
    ]:
        b = jobs.add_parser(action, help="Managed command task: " + action)
        b.add_argument(
            "--state-dir", type=Path, default=client_home(), help="Private user state root"
        )
        if action in {"start", "adopt"}:
            if action == "adopt":
                b.add_argument(
                    "--pid",
                    type=int,
                    required=True,
                    help="Owned process-group leader PID; never the calling shell",
                )
            if action == "start":
                b.add_argument(
                    "--adapter",
                    choices=["local", "ssh", "slurm", "container"],
                    default="local",
                    help="Execution backend",
                )
                b.add_argument("--host", help="SSH target for remote execution or control")
                b.add_argument(
                    "--remote-project", help="Absolute working directory on the target host"
                )
                b.add_argument("--image", help="Prepared container image; never pulled implicitly")
                b.add_argument(
                    "--submit-arg",
                    action="append",
                    default=[],
                    help="Slurm resource option, e.g. --submit-arg=--partition=cpu",
                )
            if action == "start":
                b.add_argument("--interactive", action="store_true", help="Start with a local PTY")
                b.add_argument(
                    "--command", required=True, help="Bash command on the selected backend"
                )
            b.add_argument(
                "--project", type=Path, default=Path.cwd(), help="Project working directory"
            )
            b.add_argument("--session", default="cli", help="Task session identity")
            b.add_argument(
                "--request-id", help="Stable idempotency key; default creates a new operation"
            )
            b.add_argument(
                "--timeout",
                type=float,
                default=3600,
                help="Positive wall seconds including pauses (default 3600; max 604800)",
            )
        elif action.endswith("-session"):
            b.add_argument("--session", required=True, help="Exact OpenCode session ID to control")
            b.add_argument(
                "--project", type=Path, default=Path.cwd(), help="Original project directory"
            )
        elif action != "list":
            b.add_argument("job_id", help="Managed task ID returned by start/list")
        if action == "input":
            b.add_argument(
                "--data", required=True, help="UTF-8 PTY input, including newline if needed"
            )
            b.add_argument(
                "--request-id", help="Stable input key; default creates a new input operation"
            )
        if action == "output":
            b.add_argument("--offset", type=int, default=0, help="Byte cursor from next_offset")
            b.add_argument("--limit", type=int, default=16384, help="Maximum bytes, 1..65536")
    histories = clients.add_parser(
        "history", help="Manage connections associated with saved session history"
    ).add_subparsers(dest="history_action", required=True)
    b = histories.add_parser(
        "list", help="List local historical endpoints and session counts without connecting"
    )
    b.add_argument(
        "--state-dir", type=Path, default=client_home(), help="Private client state root"
    )
    b.add_argument(
        "--json", action="store_true", help="Print structured history metadata instead of a table"
    )
    for action in ("backup", "restore", "select"):
        b = histories.add_parser(
            action, help="Private history " + action + "; never merges databases"
        )
        b.add_argument(
            "--state-dir", type=Path, default=client_home(), help="Private client state root"
        )
        if action == "backup":
            b.add_argument(
                "--output",
                type=Path,
                required=True,
                help="New private history ZIP; contains conversations",
            )
        elif action == "select":
            b.add_argument("history_id", help="History identity from client history list")
        else:
            b.add_argument(
                "--archive", type=Path, required=True, help="Private history ZIP from backup"
            )
            b.add_argument(
                "--client-dir",
                type=Path,
                default=client_assets(arch()),
                help="Native client matching the snapshot version",
            )
            b.add_argument(
                "--endpoint",
                default=settings().get("endpoint"),
                help="New reachable endpoint; no request is made during restore",
            )
            b.add_argument(
                "--select",
                action="store_true",
                help="Explicitly select the restored history for future chats",
            )
            b.add_argument(
                "--project",
                type=Path,
                help="Optional local project directory for restored connection metadata",
            )
    b = clients.add_parser(
        "doctor", help="Aggregate private client, history, task and request diagnostics"
    )
    b.add_argument(
        "--state-dir", type=Path, default=client_home(), help="Private client state root"
    )
    b.add_argument(
        "--client-dir", type=Path, default=client_assets(arch()), help="Native client assets"
    )
    b.add_argument(
        "--endpoint",
        default=settings().get("endpoint"),
        help="Model API to check only with --check-endpoint",
    )
    b.add_argument(
        "--model",
        default=settings().get("model") or catalog()["model"]["served_name"],
        help="Served model identity",
    )
    b.add_argument(
        "--check-endpoint", action="store_true", help="Explicitly check API readiness; no inference"
    )
    b.add_argument("--limit", type=int, default=20, help="Recent runs to inspect, 1..1000")
    b = histories.add_parser(
        "update-endpoint",
        help="Update the server address associated with existing sessions",
        description="Update saved history connections only; installation defaults are unchanged. The target must have no separate sessions.",
        epilog="Example: ./local-ai client history update-endpoint --old http://GPU001:18000/v1 --new http://GPU002:18000/v1",
    )
    b.add_argument(
        "--old",
        dest="old_endpoint",
        required=True,
        help="Previous model API endpoint whose history is retained",
    )
    b.add_argument(
        "--new",
        dest="endpoint",
        default=settings().get("endpoint"),
        help="Replacement endpoint; defaults to the saved endpoint",
    )
    b.add_argument(
        "--model",
        default=settings().get("model"),
        help="Replacement model ID; otherwise retain the source model",
    )
    b.add_argument(
        "--state-dir", type=Path, default=client_home(), help="Private client state root"
    )
    b.add_argument(
        "--dry-run",
        action="store_true",
        help="Show the binding plan without writing files or connecting",
    )

    b = clients.add_parser(
        "workflow", help="Run explicit real model/tool acceptance in a new private directory"
    )
    b.add_argument(
        "--endpoint",
        default=settings().get("endpoint"),
        help="Reachable model API; uses actual inference",
    )
    b.add_argument(
        "--model",
        default=settings().get("model") or catalog()["model"]["served_name"],
        help="Served model ID",
    )
    b.add_argument(
        "--client-dir", type=Path, default=client_assets(arch()), help="Native client assets"
    )
    b.add_argument(
        "--output",
        type=Path,
        required=True,
        help="New private results/workspace directory; must not exist",
    )
    b.add_argument(
        "--case", choices=workflows.CASES, required=True, help="Workflow acceptance case"
    )
    b.add_argument(
        "--timeout",
        type=float,
        default=90,
        help="Per-turn batch deadline in seconds (0-3600 exclusive of zero)",
    )
    for action in ("tasks", "report"):
        b = clients.add_parser(
            action, help="Inspect private launch status and diagnostics without inference"
        )
        if action == "tasks":
            b.add_argument(
                "--state-dir", type=Path, default=client_home(), help="Private client state root"
            )
            b.add_argument("--limit", type=int, default=20, help="Maximum recent launches (1-1000)")
        else:
            b.add_argument(
                "--run-dir",
                type=Path,
                required=True,
                help="Launch log directory containing run.json",
            )
    b = groups.add_parser(
        "chat",
        help="bcm-headnode: chat using tools on this host",
        description="Run on bcm-headnode. Connect to a reachable HTTP(S) model API endpoint. Tools execute locally as the current user.",
        epilog="Example: ./local-ai chat --endpoint http://GPU001:18000/v1 --project /home/alice/project",
    )
    b.add_argument(
        "--endpoint",
        default=settings().get("endpoint"),
        help="HTTP(S) API URL including /v1; override the saved default for this invocation without saving",
    )
    b.add_argument(
        "--client-dir",
        type=Path,
        default=client_assets(arch()),
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
        default=settings().get("model") or catalog()["model"]["served_name"],
        help="Served model ID at the selected endpoint; overrides the installed model default for this invocation",
    )
    b.add_argument(
        "--check", action="store_true", help="Check model API connectivity without chatting"
    )
    b.add_argument(
        "chat_command", nargs="?", choices=["run"], help="run starts noninteractive batch chat"
    )
    b.add_argument("prompt", nargs="?", help="Task prompt for chat run")
    b.add_argument("--run", help="One task prompt; default plain text output, then exit")
    b.add_argument(
        "--sync-bash",
        action="store_true",
        help="Use native synchronous Bash, retaining its command parser",
    )
    b.add_argument(
        "--no-task-notifications",
        action="store_true",
        help="Disable automatic managed-task messages for this chat",
    )

    b.add_argument(
        "--prompt-file",
        type=Path,
        help="Read UTF-8 task instructions from a file or - for stdin; never executes the file implicitly",
    )
    b.add_argument(
        "--format",
        dest="output_format",
        choices=["text", "json"],
        default="text",
        help="Batch answer format; JSON preserves native machine events",
    )
    b.add_argument(
        "--run-timeout",
        type=float,
        default=0,
        help="Batch --run deadline in seconds; zero disables; timeout exits 124",
    )
    b.add_argument(
        "--heartbeat",
        type=float,
        default=15,
        help="Batch progress interval in seconds; zero disables",
    )
    b.add_argument(
        "--direct-api",
        action="store_true",
        help="Bypass local request observer; retain native event and task records",
    )
    resume = b.add_mutually_exclusive_group()
    resume.add_argument(
        "-s", "--session", help="Resume this OpenCode session in the selected private history"
    )
    resume.add_argument(
        "-c",
        "--continue",
        dest="continue_session",
        action="store_true",
        help="Continue the latest OpenCode session for this project and history identity",
    )
    a.epilog = (
        a.epilog or ""
    ) + " Model recipes: set LOCAL_AI_CATALOG to an external profiles JSON file."
    return a


def dispatch(q):
    if q.group == "document":
        if q.action == "doctor":
            return documents.dependencies()
        if q.action == "web":
            return webpage.read_webpage(q.url, q.offset)
        if q.action == "video":
            return video.read_video(q.path, q.mode, q.start, q.count, q.interval, q.offset)
        return documents.read_document(q.path, q.mode, q.start, q.count, q.offset)
    if q.group == "config":
        if q.action == "show":
            return configuration.show()
        return configuration.update(q.key, getattr(q, "value", None), remove=q.action == "unset")
    if q.group == "install":
        return deployment.install(q)
    if q.group == "prepare":
        return preparation.prepare(q)
    if q.group == "export":
        return bundle.export(q)
    if q.group == "profiles":
        return catalog()["profiles"]
    if q.group == "server":
        if q.action == "inventory":
            return server.inventory()
        if q.action == "status":
            value = server.status(q.name)
            print(value["message"], file=sys.stderr, flush=True)
            if "warmup" in value:
                print(
                    "推理预热（Warmup）: " + value["warmup"]["state"], file=sys.stderr, flush=True
                )
            if value.get("log"):
                print("运行日志（Runtime log）： " + value["log"], file=sys.stderr, flush=True)
            return value
        if q.action == "stop":
            return server.stop(q.data_dir, q.name)
        if q.action == "benchmark":
            return benchmark.run(
                server.managed_spec(q.data_dir, q.name),
                server.inspect_container,
                input_tokens=q.input_tokens,
                output_tokens=q.output_tokens,
                concurrency=q.concurrency,
                repeats=q.repeats,
                warmup_rounds=q.warmup_rounds,
                timeout=q.timeout,
            )
        if q.action == "warmup":
            spec = server.managed_spec(q.data_dir, q.name)
            result = warmup.run(
                spec,
                server.inspect_container,
                timeout=q.timeout,
                inputs=q.input_tokens,
                concurrency=q.concurrency,
                output_tokens=q.output_tokens,
                repeats=q.repeats,
            )
            return {
                "state": "ready",
                "ready": True,
                "container": spec["container"],
                "warmup": result,
                "log": str(readiness.log_path(spec)),
            }
        if q.action == "start" and q.warmup and q.warmup_timeout <= 0:
            raise ValueError("--warmup-timeout must be positive")
        if q.action == "start" and q.wait_timeout <= 0:
            raise ValueError("--wait-timeout must be positive")
        policy = profile(q.profile)
        hardware = (
            json.loads(q.inventory.read_text())
            if q.action == "plan" and q.inventory
            else server.inventory()
        )
        value = server.plan(q.data_dir, policy, q.gpus, q.name, q.port, hardware, host=q.host)
        if q.action == "plan":
            return value
        result = server.start(value, policy)
        runtime_log = Path(value["spec"]["data_dir"]) / "instances" / q.name / "server.log"
        installlog.event("容器已运行，正在等待 API 就绪；首次模型加载和编译可能需要数分钟。")
        installlog.event("Runtime log: " + str(runtime_log))
        installlog.event("Follow startup: " + shlex.join(["tail", "-f", str(runtime_log)]))
        launcher = Path(__file__).resolve().parents[2] / "local-ai"
        command = str(launcher) if launcher.is_file() else "local-ai"
        installlog.event(
            "查询状态（Check status）: "
            + shlex.join([command, "server", "status", "--name", q.name])
        )
        checked = readiness.wait(value["spec"], server.inspect_container, timeout=q.wait_timeout)
        if q.warmup:
            checked["warmup"] = warmup.run(
                value["spec"], server.inspect_container, timeout=q.warmup_timeout
            )
        return {**result, **checked}
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
        if q.action == "doctor":
            return diagnostics.inspect(
                q.state_dir, q.client_dir, q.endpoint, q.model, q.check_endpoint, q.limit
            )
        if q.action == "job":
            action = q.job_action.replace("-", "_")
            options = {}
            if action in {"start", "adopt"}:
                options = {
                    "session": q.session,
                    "project": str(q.project),
                    "argv": ["/bin/bash", "-lc", q.command]
                    if action == "start"
                    else ["<adopted>", str(q.pid)],
                    "interactive": getattr(q, "interactive", False),
                    "request_id": q.request_id or "cli_" + str(time.time_ns()),
                    "timeout": q.timeout,
                }
                if (
                    action == "start"
                    and q.adapter == "local"
                    and (q.host or q.remote_project or q.image or q.submit_arg)
                ):
                    raise ValueError("Remote options require an explicit --adapter")
                if action == "start" and q.adapter != "local":
                    options.update(
                        adapter=q.adapter,
                        host=q.host,
                        remote_project=q.remote_project,
                        image=q.image,
                        submit_args=q.submit_arg,
                    )
                if action == "adopt":
                    options["adopt_pid"] = q.pid
                    action = "start"
            elif action.endswith("_session"):
                options = {"session": q.session, "project": str(q.project)}
            elif action != "list":
                options["job_id"] = q.job_id
            if action == "input":
                options.update(data=q.data, request_id=q.request_id or "cli_" + str(time.time_ns()))
            if action == "output":
                options.update(offset=q.offset, limit=q.limit)
            return execution.perform(q.state_dir / "execution", action, **options)
        if q.action == "history":
            if q.history_action == "backup":
                return portability.backup(q.state_dir, q.output)
            if q.history_action == "restore":
                return portability.restore(
                    q.state_dir, q.archive, q.client_dir, q.endpoint, q.select, q.project
                )
            if q.history_action == "select":
                return portability.select(q.state_dir, q.history_id)
            if q.history_action == "list":
                rows = history.list_histories(q.state_dir, settings().get("endpoint"))
                if q.json:
                    print(json.dumps(rows, indent=2))
                elif rows:
                    print("HISTORY               SESSIONS  DEFAULT  RECORDED ENDPOINTS")
                    for row in rows:
                        count = row["sessions"] if row["sessions"] is not None else "?"
                        addresses = ", ".join(row["endpoints"]) or "(unknown)"
                        marker = "*" if row["default"] else "-"
                        print(f"{row['history_id']:<20}  {count!s:<8}  {marker:<7}  {addresses}")
                        if row["error"]:
                            print("  ERROR: " + row["error"])
                else:
                    print("No local session history found.")
                return int(any(row["error"] for row in rows))
            if not q.endpoint:
                raise ValueError("Set --new or configure the saved replacement endpoint")
            q.default_endpoint = settings().get("endpoint")
            print(json.dumps(history.update_endpoint(q), indent=2))
            return 0
        if q.action == "workflow":
            if not q.endpoint:
                raise ValueError("Set --endpoint or configure the default")
            result = workflows.run(q)
            print(json.dumps(result, indent=2))
            return 0 if result["state"] == "passed" else 1
        if q.action == "tasks":
            return tasks.list_runs(q.state_dir, q.limit)
        if q.action == "report":
            return telemetry.report(q.run_dir)
        if q.action == "install":
            value = artifacts.install(q.client_dir, q.binary, q.seed_cache, q.version, q.sha256)
            if q.client_dir.resolve() == client_assets(arch()):
                deployment.publish_client(q.client_dir)
            value["instructions"] = instructions.apply(q.instructions, q.instructions_language)
            return value
        if q.action == "export":
            return artifacts.export_client(q.client_dir, q.output)
    if q.group == "chat":
        if not q.endpoint:
            raise ValueError(
                "Set --endpoint or save a default with local-ai config set endpoint URL"
            )
        return client.chat(q)
    raise ValueError("Unsupported command")


def preflight(q):
    """Reject incomplete recipes before logging, probing or changing resources."""
    if q.group == "prepare":
        preparation.policies(q.profile)
        return
    if (
        q.group in {"image", "model"}
        or (q.group == "install" and q.role in {"server", "both"})
        or (q.group == "server" and q.action == "start")
    ):
        require_deployable(profile(q.profile))
    elif q.group == "export":
        for name in q.profile or settings().get("profiles", []):
            require_deployable(profile(name))


def main(argv=None):
    q = None
    try:
        argv = list(sys.argv[1:] if argv is None else argv)
        if argv[:1] == ["--_complete"]:
            mode, values = completion.candidates(parser(), argv[1:])
            print("\n".join([mode, *values]))
            return 0
        q = parser().parse_args(argv)
        if q.group == "completion":
            print(completion.bash_script(root() / "local-ai"))
            return 0
        preflight(q)
        with installlog.session(q):
            value = dispatch(q)
            if not isinstance(value, int):
                installlog.event("RESULT " + json.dumps(value, ensure_ascii=False))
        if isinstance(value, int):
            return value
        print(json.dumps(value, indent=2))
        if q.group == "server" and q.action == "status" and not value["ready"]:
            return 1
        return 0
    except KeyboardInterrupt:
        return 130
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        if q is not None and q.debug:
            raise
        print("ERROR: " + str(error), file=sys.stderr)
        return 1
