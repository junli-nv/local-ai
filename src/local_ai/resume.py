"""Restore local-ai connection context for OpenCode's native resume hint."""

import argparse
import json
import os
import shlex
import subprocess
import sys
import tempfile
from pathlib import Path

from .artifacts import validate
from .common import atomic_json, client_home, fingerprint, private_dir
from .profiles import client_options

MARKER = "# local-ai managed OpenCode resume launcher"


def install_launcher():
    target = Path.home() / ".local/bin/opencode"
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() or target.is_symlink():
        if target.is_symlink() or MARKER not in target.read_text(errors="replace"):
            print("保留已有 opencode；请使用 local-ai chat --session 恢复会话。", file=sys.stderr)
            return None
    code = (
        "import sys; sys.path.insert(0, "
        + repr(str(Path(__file__).resolve().parents[1]))
        + "); from local_ai.resume import main; sys.exit(main())"
    )
    fd, temporary = tempfile.mkstemp(prefix=".local-ai-opencode-", dir=target.parent)
    try:
        os.fchmod(fd, 0o700)
        with os.fdopen(fd, "w") as stream:
            stream.write(
                "#!/bin/bash\n"
                + MARKER
                + "\nexec "
                + shlex.join([sys.executable, "-c", code])
                + ' "$@"\n'
            )
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    if str(target.parent) not in os.environ.get("PATH", "").split(os.pathsep):
        print(
            '恢复入口已安装；当前 shell 请执行：export PATH="$HOME/.local/bin:$PATH"',
            file=sys.stderr,
        )
    return target


def register(state_root, state, assets, base, model, project):
    context = {
        "catalog": str(Path(os.environ["LOCAL_AI_CATALOG"]).expanduser().resolve())
        if os.environ.get("LOCAL_AI_CATALOG")
        else None,
        "client_options": client_options(model),
        "project": str(project),
        "state_dir": str(state_root),
        "state": str(state),
        "client_dir": str(assets),
        "endpoint": base,
        "model": model,
    }
    atomic_json(state / "connection.json", context)
    directory = private_dir(client_home() / "connections")
    atomic_json(directory / (fingerprint(str(state)) + ".json"), {"state": str(state)})
    install_launcher()


def context_for(state):
    path = state / "connection.json"
    if path.is_file():
        return json.loads(path.read_text())
    # Older clients already recorded invocation and model config together.
    for path in sorted((state / "logs").glob("*/invocation.json"), reverse=True):
        invocation = json.loads(path.read_text())
        if not invocation.get("endpoint"):
            continue
        cfg = json.loads((path.parent / "opencode.json").read_text())
        return {
            "project": invocation["project"],
            "state_dir": str(state.parent.parent),
            "state": str(state),
            "client_dir": str(Path(invocation["command"][0]).parent.parent),
            "endpoint": invocation["endpoint"],
            "model": cfg["model"].split("/", 1)[1],
        }
    return None


def native_sessions(state, context):
    """Use the public CLI instead of depending on OpenCode's database schema."""
    from .client import config

    assets = Path(context["client_dir"])
    validate(assets)
    env = os.environ.copy()
    env.update(
        OPENCODE_CONFIG_CONTENT=json.dumps(
            config(context["endpoint"], context["model"], context.get("client_options", {}))
        ),
        XDG_DATA_HOME=str(state / "data"),
        XDG_STATE_HOME=str(state / "state"),
        XDG_CACHE_HOME=str(state / "cache"),
        OPENCODE_DISABLE_MODELS_FETCH="true",
        OPENCODE_DISABLE_AUTOUPDATE="true",
        OPENCODE_DISABLE_DEFAULT_PLUGINS="true",
    )
    result = subprocess.run(
        [str(assets / "bin/opencode"), "session", "list", "--format", "json"],
        cwd=context["project"],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )
    if result.returncode:
        raise RuntimeError(
            "OpenCode session list --format json failed; check this client's CLI compatibility: "
            + result.stderr.strip()
        )
    try:
        sessions = json.loads(result.stdout) if result.stdout.strip() else []
        if not isinstance(sessions, list) or any(
            not isinstance(item, dict)
            or not isinstance(item.get("id"), str)
            or not isinstance(item.get("directory"), str)
            for item in sessions
        ):
            raise ValueError("Unexpected session metadata")
        return sessions
    except ValueError as error:
        raise ValueError(
            "OpenCode session list returned incompatible JSON metadata; stdout="
            + repr(result.stdout[:1000])
            + "; stderr="
            + repr(result.stderr[:1000])
        ) from error


def locate(session_id):
    states = set((client_home() / "services").glob("*"))
    for pointer in (client_home() / "connections").glob("*.json"):
        states.add(Path(json.loads(pointer.read_text())["state"]))
    matches = []
    for state in sorted(states):
        if not (state / "connection.json").exists() and not any(
            (state / "logs").glob("*/invocation.json")
        ):
            continue
        context = context_for(state)
        if context is None:
            continue
        projects = {context.get("project")}
        for path in (state / "logs").glob("*/invocation.json"):
            projects.add(json.loads(path.read_text()).get("project"))
        for project in sorted(p for p in projects if p and Path(p).is_dir()):
            for session in native_sessions(state, {**context, "project": project}):
                if session["id"] == session_id:
                    match = (context, session["directory"])
                    if match not in matches:
                        matches.append(match)
    if len(matches) != 1:
        raise ValueError(
            "未找到唯一的会话；请使用 local-ai chat --endpoint URL --session ID 指定连接。"
        )
    return matches[0]


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="opencode",
        description="Resume a local-ai session with its original endpoint, project and private history.",
    )
    parser.add_argument("-s", "--session", required=True, help="OpenCode session ID shown on exit")
    args = parser.parse_args(argv)
    try:
        from .client import chat

        context, project = locate(args.session)
        if context.get("catalog"):
            os.environ["LOCAL_AI_CATALOG"] = context["catalog"]
        else:
            os.environ.pop("LOCAL_AI_CATALOG", None)
        return chat(
            argparse.Namespace(
                endpoint=context["endpoint"],
                client_dir=Path(context["client_dir"]),
                state_dir=Path(context["state_dir"]),
                project=Path(project),
                model=context["model"],
                check=False,
                run=None,
                session=args.session,
                continue_session=False,
            )
        )
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print("ERROR: " + str(error), file=sys.stderr)
        return 1
