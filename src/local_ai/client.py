"""Headnode client. Every tool executes with the headnode user's permissions."""

import fcntl
import json
import os
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path

from .artifacts import validate
from .common import atomic_json, fingerprint, private_dir
from .endpoint import endpoint_url, wait_endpoint
from .operations import GUIDANCE


def service_key(endpoint):
    return fingerprint({"endpoint": endpoint_url(endpoint)})[:20]


def config(base, model):
    return {
        "$schema": "https://opencode.ai/config.json",
        "model": "local-deepseek/" + model,
        "enabled_providers": ["local-deepseek"],
        "provider": {
            "local-deepseek": {
                "npm": "@ai-sdk/openai-compatible",
                "name": "Cluster local DeepSeek",
                "options": {"baseURL": base, "apiKey": "local"},
                "models": {
                    model: {
                        "name": model,
                        "reasoning": True,
                        "tool_call": True,
                        "interleaved": {"field": "reasoning_content"},
                        "limit": {"context": 131072, "output": 32768},
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
    file = session / "opencode.json"
    instructions = session / "operations.md"
    instructions.write_text(GUIDANCE, encoding="utf-8")
    instructions.chmod(0o600)
    cfg = config(base, model)
    cfg["instructions"] = [str(instructions)]
    atomic_json(file, cfg)
    env = os.environ.copy()
    env.update(
        OPENCODE_CONFIG=str(file),
        OPENCODE_CONFIG_CONTENT=json.dumps(cfg),
        XDG_CONFIG_HOME=str(session / "config"),
        XDG_CACHE_HOME=str(cache),
        XDG_DATA_HOME=str(state / "data"),
        XDG_STATE_HOME=str(state / "state"),
        SHELL="/bin/bash",
        PWD=str(project),
        OPENCODE_DISABLE_AUTOUPDATE="true",
        OPENCODE_DISABLE_MODELS_FETCH="true",
        OPENCODE_DISABLE_LSP_DOWNLOAD="true",
        OPENCODE_DISABLE_DEFAULT_PLUGINS="true",
    )
    for key in ["NO_PROXY", "no_proxy"]:
        env[key] = ",".join(filter(None, [env.get(key), "127.0.0.1", "localhost", "::1"]))
    return env


def execute(command, project, env, logfile, prompt):
    if prompt is None:
        return subprocess.call(
            ["script", "-q", "-e", "-f", str(logfile), "-c", shlex.join(command)],
            cwd=project,
            env=env,
        )
    with logfile.open("wb") as log:
        child = subprocess.Popen(
            command, cwd=project, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
        )
        try:
            while True:
                chunk = child.stdout.read1(8192)
                if not chunk:
                    break
                log.write(chunk)
                log.flush()
                sys.stdout.buffer.write(chunk)
                sys.stdout.buffer.flush()
            return child.wait()
        finally:
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=3)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
            child.stdout.close()


def chat(options):
    base = endpoint_url(options.endpoint)
    os.umask(0o077)
    assets = Path(options.client_dir).expanduser().resolve()
    if not (assets / "manifest.json").is_file():
        raise RuntimeError("Client not installed; run local-ai client install on this headnode")
    manifest = validate(assets)
    state_root = private_dir(options.state_dir)
    key = service_key(base)
    state = private_dir(state_root / "services" / key)
    session = private_dir(state / "logs" / ("session-%d-%d" % (time.time_ns(), os.getpid())))
    project = Path(options.project).expanduser().resolve()
    if not project.is_dir():
        raise ValueError("Project directory does not exist: " + str(project))
    if not options.check and options.run is None and not sys.stdin.isatty():
        raise ValueError("Interactive chat requires a terminal; use --run for batch execution")
    wait_endpoint(base, options.model)
    env = prepare(state, assets, session, base, options.model, project)
    if options.check:
        print(
            json.dumps(
                {
                    "ready": True,
                    "client_arch": manifest["arch"],
                    "log_directory": str(session),
                    "endpoint": base,
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
    return execute(command, project, env, session / "terminal.log", options.run)
