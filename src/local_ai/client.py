"""Headnode client. Every tool executes with the headnode user's permissions."""

import contextlib
import fcntl
import json
import math
import os
import shutil
import sys
import time
from pathlib import Path

from . import __version__, batch, history, native_cache, tasks, telemetry
from .artifacts import validate
from .common import arch, atomic_json, fingerprint, private_dir
from .endpoint import endpoint_url, wait_endpoint
from .operations import GUIDANCE
from .paths import client_assets, settings
from .profiles import catalog, client_options
from .resume import register


def service_key(endpoint):
    return fingerprint({"endpoint": endpoint_url(endpoint)})[:20]


def config(base, model, options=None):
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": "local-deepseek/" + model,
        "enabled_providers": ["local-deepseek"],
        "provider": {
            "local-deepseek": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Cluster local model",
                "options": {"baseURL": base, "apiKey": "local"},
                "models": {
                    model: {
                        "name": model,
                        "tool_call": True,
                        **(client_options(model) if options is None else options),
                    }
                },
            }
        },
        "autoupdate": False,
        "share": "disabled",
        "shell": "/bin/bash",
    }


def prepare(state, assets, session, base, model, project):
    cache = state / "cache"
    with (state / ".prepare.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        if not cache.exists():
            temp = state / ("cache.prepare-" + str(os.getpid()))
            shutil.copytree(assets / "seed-cache", temp)
            temp.rename(cache)
    for name in ["data", "state"]:
        (state / name).mkdir(exist_ok=True, mode=0o700)
    (session / "config").mkdir(exist_ok=True, mode=0o700)
    reused_dependencies = native_cache.prime(state, assets, session)
    file = session / "opencode.json"
    instructions = session / "operations.md"
    instructions.write_text(GUIDANCE, encoding="utf-8")
    instructions.chmod(0o600)
    cfg = config(base, model)
    execution_plugin = session / "config/opencode/execution.mjs"
    execution_plugin.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    shutil.copyfile(Path(__file__).with_name("execution.mjs"), execution_plugin)
    execution_plugin.chmod(0o600)
    cfg["plugin"] = [
        Path(__file__).with_name("observer.mjs").resolve().as_uri(),
        execution_plugin.resolve().as_uri(),
    ]
    cfg["compaction"] = {"auto": True, "prune": True}
    cfg["command"] = {
        "handoff": {
            "description": "Summarize objective, constraints, evidence and pending work for safe resumption",
            "template": "Create a concise handoff in the conversation: objective; explicit constraints; "
            "completed actions with evidence and file/job IDs; decisions; pending work and unresolved "
            "tool calls; next verification steps. Do not execute new work or repeat writes. "
            "Do not treat a handoff as approval for new actions.",
        }
    }
    cfg["instructions"] = [str(instructions)]
    # Resolve personal rules before replacing XDG_CONFIG_HOME with session isolation.
    from .instructions import personal_path

    personal_rules = personal_path().resolve()
    if personal_rules.is_file():
        cfg["instructions"].append(str(personal_rules))
    cfg["mcp"] = {
        "documents": {
            "type": "local",
            "command": [sys.executable, "-m", "local_ai.document_mcp"],
            "environment": {"PYTHONPATH": str(Path(__file__).resolve().parents[1])},
            "enabled": True,
            "timeout": 120000,
        }
    }
    tui = session / "tui.json"
    atomic_json(
        tui,
        {
            "mouse": False,
            "keybinds": {
                "messages_copy": "none",
                "input_paste": "none",
                "display_thinking": "<leader>i",
            },
            "cursor": {"style": "line", "blinking": False},
            "plugin": [
                [
                    Path(__file__).with_name("tui_defaults.mjs").resolve().as_uri(),
                    {"thinking_mode": "show"},
                ],
            ],
        },
    )
    atomic_json(file, cfg)
    env = os.environ.copy()
    env.update(
        LOCAL_AI_RUN_DIR=str(session),
        LOCAL_AI_PROJECT=str(project),
        LOCAL_AI_EXECUTION_DIR=str(
            (state.parent.parent if state.parent.name == "services" else state) / "execution"
        ),
        LOCAL_AI_EXECUTION_HELPER=str(Path(__file__).with_name("execution.py").resolve()),
        LOCAL_AI_EXECUTION_PYTHON=sys.executable,
        LOCAL_AI_DEPENDENCIES_REUSED=str(reused_dependencies).lower(),
        OPENCODE_TUI_CONFIG=str(tui),
        OPENCODE_CONFIG=str(file),
        OPENCODE_CONFIG_CONTENT=json.dumps(cfg),
        XDG_CONFIG_HOME=str(session / "config"),
        XDG_CACHE_HOME=str(cache),
        XDG_DATA_HOME=str(state / "data"),
        XDG_STATE_HOME=str(state / "state"),
        SHELL="/bin/bash",
        PWD=str(project),
        OPENCODE_DISABLE_MOUSE="true",
        OPENCODE_EXPERIMENTAL_DISABLE_COPY_ON_SELECT="true",
        OPENCODE_DISABLE_AUTOUPDATE="true",
        OPENCODE_DISABLE_MODELS_FETCH="true",
        OPENCODE_DISABLE_LSP_DOWNLOAD="true",
        OPENCODE_DISABLE_DEFAULT_PLUGINS="true",
    )
    for key in ["NO_PROXY", "no_proxy"]:
        env[key] = ",".join(filter(None, [env.get(key), "127.0.0.1", "localhost", "::1"]))
    return env


def execute(command, project, env, logfile, prompt):
    return tasks.execute(command, project, env, logfile, prompt)


def chat(options):
    options.run = batch.prompt(options)
    timeout = getattr(options, "run_timeout", 0)
    heartbeat = getattr(options, "heartbeat", 15)
    if not all(math.isfinite(v) and v >= 0 for v in (timeout, heartbeat)):
        raise ValueError("Timeout and heartbeat must be nonnegative")
    if timeout and options.run is None:
        raise ValueError("--run-timeout requires --run")
    base = endpoint_url(options.endpoint)
    os.umask(0o077)
    assets = Path(options.client_dir).expanduser().resolve()
    if not (assets / "manifest.json").is_file():
        raise RuntimeError("Client not installed; run local-ai client install on this headnode")
    manifest = validate(assets)
    state_root = private_dir(options.state_dir)
    installed = settings()
    default_endpoint = installed.get("endpoint")
    key = history.resolve(state_root, base, default_endpoint)
    state = private_dir(state_root / "services" / key)
    session = private_dir(state / "logs" / ("session-%d-%d" % (time.time_ns(), os.getpid())))
    project = Path(options.project).expanduser().resolve()
    if not project.is_dir():
        raise ValueError("Project directory does not exist: " + str(project))
    if not options.check and options.run is None and not sys.stdin.isatty():
        raise ValueError("Interactive chat requires a terminal; use --run for batch execution")
    wait_endpoint(base, options.model)
    if history.resolve(state_root, base, default_endpoint) != key:
        raise ValueError("History binding changed during startup; retry chat")
    history.remember_history(state_root, base, key, default_endpoint)
    env = prepare(state, assets, session, base, options.model, project)
    register(state_root, state, assets, base, options.model, project)
    if options.check:
        print(
            json.dumps(
                {
                    "ready": True,
                    "client_arch": manifest["arch"],
                    "log_directory": str(session),
                    "endpoint": base,
                    "model": options.model,
                }
            )
        )
        return 0
    command = [str(assets / "bin/opencode")]
    command += (
        ["run", "--dir", str(project), "--format", "json", options.run]
        if options.run is not None
        else [str(project)]
    )
    if getattr(options, "session", None):
        command += ["--session", options.session]
    if getattr(options, "continue_session", False):
        command += ["--continue"]
    atomic_json(
        session / "invocation.json",
        {
            "project": str(project),
            "command": command,
            "endpoint": base,
            "client_arch": manifest["arch"],
        },
    )
    print("Log: " + str(session / "terminal.log"), file=sys.stderr)
    launcher_path = Path(__file__).resolve().parents[2] / "local-ai"
    launcher = str(launcher_path) if launcher_path.is_file() else "local-ai"
    reconnect = [launcher, "chat", "--project", str(project), "--state-dir", str(state_root)]
    if not default_endpoint or base != endpoint_url(default_endpoint):
        reconnect += ["--endpoint", base]
    if options.model != (installed.get("model") or catalog()["model"]["served_name"]):
        reconnect += ["--model", options.model]
    if assets != client_assets(arch()).resolve():
        reconnect += ["--client-dir", str(assets)]
    env["LOCAL_AI_CONTEXT"] = json.dumps(
        {
            "endpoint": base,
            "model": options.model,
            "project": str(project),
            "client_dir": str(assets),
            "state_dir": str(state_root),
            "requested_session": getattr(options, "session", None),
            "client_version": manifest.get("version"),
            "local_ai_version": __version__,
            "request_observer_enabled": not getattr(options, "direct_api", False),
            "launcher": launcher,
            "resume_command": reconnect if options.run is None else None,
            "context_limit": client_options(options.model).get("limit", {}).get("context"),
        }
    )
    env["LOCAL_AI_OUTPUT_FORMAT"] = getattr(options, "output_format", "json")
    env["LOCAL_AI_BATCH"] = str(options.run is not None).lower()
    if options.run is not None or getattr(options, "sync_bash", False):
        # Batch pipelines require the command result, not a background submission ID.
        env["LOCAL_AI_ASYNC_BASH"] = "false"
    if getattr(options, "no_task_notifications", False):
        env["LOCAL_AI_NOTIFICATIONS"] = "false"
    env["LOCAL_AI_RUN_TIMEOUT"] = str(timeout)
    env["LOCAL_AI_HEARTBEAT"] = str(heartbeat)
    observer = (
        contextlib.nullcontext(base)
        if getattr(options, "direct_api", False)
        else telemetry.proxy(base, session)
    )
    with observer as observed_base:
        if observed_base != base:
            cfg = json.loads(env["OPENCODE_CONFIG_CONTENT"])
            cfg["provider"]["local-deepseek"]["options"]["baseURL"] = observed_base
            atomic_json(Path(env["OPENCODE_CONFIG"]), cfg)
            env["OPENCODE_CONFIG_CONTENT"] = json.dumps(cfg)
        return execute(command, project, env, session / "terminal.log", options.run)
