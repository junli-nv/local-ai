"""Measure native follow-up delivery during a harmless shell call; no real model or GPU."""

import argparse
import contextlib
import fcntl
import json
import math
import os
import pty
import select
import shlex
import socket
import struct
import subprocess
import sys
import tempfile
import termios
import threading
import time
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from local_ai.artifacts import validate
from local_ai.client import prepare
from local_ai.common import atomic_json, private_dir
from local_ai.tasks import stop

MODEL = "steering-check"
INITIAL = "STEERING_INITIAL_85b2"
FOLLOWUP = "STEERING_FOLLOWUP_6e13"
ACK = "STEER_ACK_OK"


def request(url, data=None, timeout=2):
    req = urllib.request.Request(
        url,
        data=None if data is None else json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        req, timeout=timeout
    ) as response:
        body = response.read()
        return json.loads(body) if body else None


def has_text(messages, role, marker):
    for item in messages:
        if item.get("info", {}).get("role") == role and any(
            marker in part.get("text", "") for part in item.get("parts", [])
        ):
            return True
    return False


def classify(events):
    required = (
        "tool_started",
        "follow_up_submitted",
        "follow_up_persisted_observed",
        "follow_up_in_model_request",
        "tool_finished",
        "ack_persisted_observed",
    )
    if any(events.get(key) is None for key in required):
        raise ValueError("Incomplete delivery evidence")
    if not events["tool_started"] <= events["follow_up_submitted"] < events["tool_finished"]:
        raise ValueError("Follow-up was not submitted during the tool call")
    if events["follow_up_in_model_request"] < events["follow_up_submitted"]:
        raise ValueError("Invalid model delivery timestamp")
    return (
        "during_tool"
        if events["follow_up_in_model_request"] < events["tool_finished"]
        else "after_tool"
    )


def fixture_command(project, hold):
    code = (
        "import json,time\nfrom pathlib import Path\n"
        "p=Path(" + repr(str(project)) + ")\n"
        "def stamp(name):\n"
        " q=p/(name+'.tmp'); q.write_text(json.dumps(time.monotonic())); q.replace(p/name)\n"
        "with (p/'tool-runs.txt').open('a') as f: f.write('RUN\\n')\n"
        "stamp('tool-start.json')\ntime.sleep(" + repr(hold) + ")\n"
        "stamp('tool-end.json')\nprint('TOOL_DONE')\n"
    )
    return shlex.join([sys.executable, "-c", code])


class Model:
    def __init__(self, project, hold):
        self.command = fixture_command(project, hold)
        self.lock = threading.Lock()
        self.calls = []
        self.tool_calls = 0
        self.delivered = None

    def reply(self, payload):
        messages = payload.get("messages", [])
        followup = any(
            m.get("role") == "user" and FOLLOWUP in str(m.get("content", "")) for m in messages
        )
        tools = {t.get("function", {}).get("name") for t in payload.get("tools", [])}
        results = sum(m.get("role") == "tool" for m in messages)
        with self.lock:
            now = time.monotonic()
            self.calls.append({"at": now, "follow_up": followup, "tool_results": results})
            if tools and followup and self.delivered is None:
                self.delivered = now
            if tools and not results and not followup and self.tool_calls == 0:
                name = next((name for name in ("bash", "shell") if name in tools), None)
                if name is None:
                    raise ValueError("Native client exposes no supported shell tool")
                self.tool_calls += 1
                return {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_steering_probe",
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": json.dumps(
                                    {
                                        "command": self.command,
                                        "description": "Harmless bounded steering probe",
                                    }
                                ),
                            },
                        }
                    ]
                }, "tool_calls"
        return {"content": ACK if followup else "PROBE_STEP_DONE"}, "stop"

    def handler(self):
        model = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                body = json.dumps({"data": [{"id": MODEL}]}).encode()
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def do_POST(self):
                try:
                    payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
                    delta, finish = model.reply(payload)
                    self.send_response(200)
                    self.send_header("Content-Type", "text/event-stream")
                    self.end_headers()
                    event = {
                        "id": "cmpl-steering-probe",
                        "object": "chat.completion.chunk",
                        "created": 1,
                        "model": MODEL,
                        "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                    }
                    self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
                    event["choices"][0].update(delta={}, finish_reason=finish)
                    event["usage"] = {
                        "prompt_tokens": 100,
                        "completion_tokens": 10,
                        "total_tokens": 110,
                    }
                    self.wfile.write(
                        ("data: " + json.dumps(event) + "\n\ndata: [DONE]\n\n").encode()
                    )
                    self.wfile.flush()
                except (BrokenPipeError, ConnectionResetError):
                    pass
                except Exception as error:
                    self.server.probe_errors.append(str(error))

            def log_message(self, *args):
                pass

        return Handler


def run_case(assets, root, mode, hold, timeout, evidence):
    project = private_dir(root / "project")
    state = private_dir(root / "state")
    session = private_dir(root / "session")
    model = Model(project, hold)
    api = ThreadingHTTPServer(("127.0.0.1", 0), model.handler())
    api.daemon_threads = True
    api.probe_errors = []
    worker = threading.Thread(target=api.serve_forever, daemon=True)
    worker.start()
    backend = tui = None
    master = None
    session_id = None
    submitters = []
    submit_errors = []
    screen = bytearray()
    events = {}
    origin = time.monotonic()
    deadline = origin + timeout
    backend_log = evidence / (mode + "-backend.log")

    def drain():
        if master is not None and select.select([master], [], [], 0)[0]:
            with contextlib.suppress(OSError):
                screen.extend(os.read(master, 65536))

    def wait(predicate, description):
        while True:
            drain()
            result = predicate()
            if result:
                return result
            if api.probe_errors:
                raise RuntimeError("Mock API failed: " + str(api.probe_errors))
            if backend is not None and backend.poll() is not None:
                raise RuntimeError("Native backend exited; see " + str(backend_log))
            if tui is not None and tui.poll() is not None:
                raise RuntimeError("Native TUI exited before completion")
            if time.monotonic() >= deadline:
                raise RuntimeError("Timed out waiting for " + description)
            time.sleep(0.05)

    def submit(text):
        def send():
            try:
                request(
                    base + "/session/" + session_id + "/message",
                    {
                        "model": {"providerID": "local-deepseek", "modelID": MODEL},
                        "parts": [{"type": "text", "text": text}],
                    },
                    timeout=timeout,
                )
            except Exception as error:
                submit_errors.append(str(error))

        thread = threading.Thread(target=send, daemon=True)
        submitters.append(thread)
        thread.start()

    def ready():
        try:
            return request(base + "/global/health", timeout=1)
        except OSError:
            return False

    try:
        with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(root / "personal-config")}):
            env = prepare(
                state, assets, session, f"http://127.0.0.1:{api.server_port}/v1", MODEL, project
            )
        # All native config, cache and history paths are disposable; no personal rules are loaded.
        cfg = json.loads(env["OPENCODE_CONFIG_CONTENT"])
        cfg["permission"] = {"*": "allow"}
        atomic_json(Path(env["OPENCODE_CONFIG"]), cfg)
        env["OPENCODE_CONFIG_CONTENT"] = json.dumps(cfg)
        env.pop("OPENCODE_SERVER_PASSWORD", None)
        env.pop("OPENCODE_SERVER_USERNAME", None)
        env["OPENCODE_DISABLE_CLAUDE_CODE"] = "true"
        env["OPENCODE_DISABLE_EXTERNAL_SKILLS"] = "true"
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        with backend_log.open("wb") as log:
            os.chmod(backend_log, 0o600)
            backend = subprocess.Popen(
                [
                    str(assets / "bin/opencode"),
                    "serve",
                    "--hostname",
                    "127.0.0.1",
                    "--port",
                    str(port),
                ],
                cwd=project,
                env=env,
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
            wait(ready, "native server health")
            session_id = request(base + "/session", {"title": "steering probe " + mode})["id"]
            if mode == "tui":
                master, slave = pty.openpty()
                try:
                    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 44, 160, 0, 0))
                    tui = subprocess.Popen(
                        [str(assets / "bin/opencode"), "attach", base, "--session", session_id],
                        cwd=project,
                        env={**env, "TERM": "xterm-256color"},
                        stdin=slave,
                        stdout=slave,
                        stderr=slave,
                        start_new_session=True,
                    )
                finally:
                    os.close(slave)
                wait(lambda: b"steering probe tui" in screen, "TUI session rendering")
            submit(INITIAL + ": run the bounded shell probe exactly once.")
            wait(lambda: (project / "tool-start.json").is_file(), "shell start")
            events["tool_started"] = json.loads((project / "tool-start.json").read_text())
            events["follow_up_submitted"] = time.monotonic()
            text = FOLLOWUP + ": acknowledge this update while preserving the original task."
            if mode == "tui":
                os.write(master, text.encode() + b"\r")
            else:
                submit(text)

            def observe():
                rows = request(base + "/session/" + session_id + "/message")
                now = time.monotonic()
                if has_text(rows, "user", FOLLOWUP):
                    events.setdefault("follow_up_persisted_observed", now)
                if has_text(rows, "assistant", ACK):
                    events.setdefault("ack_persisted_observed", now)
                end = project / "tool-end.json"
                if end.is_file():
                    events["tool_finished"] = json.loads(end.read_text())
                with model.lock:
                    events["follow_up_in_model_request"] = model.delivered
                return all(
                    events.get(key) is not None
                    for key in (
                        "follow_up_persisted_observed",
                        "ack_persisted_observed",
                        "tool_finished",
                        "follow_up_in_model_request",
                    )
                )

            wait(observe, "follow-up delivery, acknowledgement and shell completion")
            for thread in submitters:
                thread.join(timeout=max(0.1, deadline - time.monotonic()))
            if submit_errors or any(thread.is_alive() for thread in submitters):
                raise RuntimeError(
                    "Native submissions did not finish cleanly: " + str(submit_errors)
                )
            if (project / "tool-runs.txt").read_text().splitlines() != ["RUN"]:
                raise RuntimeError("Shell command was not executed exactly once")
            phase = classify(events)
            return {
                "transport": mode,
                "delivery_phase": phase,
                "follow_up_to_model_seconds": events["follow_up_in_model_request"]
                - events["follow_up_submitted"],
                "backend_visible_before_tool_end": events["follow_up_persisted_observed"]
                < events["tool_finished"],
                "command_runs_once": True,
                "events_seconds": {key: value - origin for key, value in events.items()},
            }
    finally:
        try:
            atomic_json(
                evidence / (mode + "-events.json"),
                {
                    "events_seconds": {
                        key: None if value is None else value - origin
                        for key, value in events.items()
                    },
                    "model_requests": [{**call, "at": call["at"] - origin} for call in model.calls],
                    "submit_errors": submit_errors,
                    "mock_errors": api.probe_errors,
                },
            )
        finally:
            if backend is not None and backend.poll() is None and session_id is not None:
                with contextlib.suppress(OSError):
                    request(base + "/session/" + session_id + "/abort", {}, timeout=2)
            for child in (tui, backend):
                if child is not None:
                    stop(child)
            if master is not None:
                os.close(master)
            for thread in submitters:
                thread.join(timeout=3)
            api.shutdown()
            api.server_close()
            worker.join(timeout=3)


def check(assets, output, mode="both", hold=5.0, timeout=90.0):
    if not math.isfinite(hold) or not 0 < hold <= 60:
        raise ValueError("--hold-seconds must be finite, positive and at most 60")
    if not math.isfinite(timeout) or timeout <= hold:
        raise ValueError("--timeout must be finite and greater than --hold-seconds")
    if mode not in {"api", "tui", "both"}:
        raise ValueError("Unknown probe mode")
    if output.exists():
        raise ValueError("--output must be a new evidence directory")
    manifest = validate(assets)
    output.mkdir(parents=True, mode=0o700)
    result = {
        "client_version": manifest["version"],
        "mock_model": True,
        "hold_seconds": hold,
        "cases": [],
        "state": "running",
    }
    try:
        with tempfile.TemporaryDirectory(prefix="local-ai-steering-") as folder:
            for transport in ["api", "tui"] if mode == "both" else [mode]:
                case = run_case(assets, Path(folder) / transport, transport, hold, timeout, output)
                result["cases"].append(case)
                print(json.dumps(case), flush=True)
        result["state"] = "measured"
        result["immediate_delivery_in_all_cases"] = all(
            case["delivery_phase"] == "during_tool" for case in result["cases"]
        )
        return result
    except KeyboardInterrupt:
        result.update(state="interrupted", error="Probe interrupted")
        raise
    except Exception as error:
        result.update(state="failed", error=str(error))
        raise
    finally:
        atomic_json(output / "report.json", result)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-dir", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True, help="New private evidence directory")
    parser.add_argument("--mode", choices=["api", "tui", "both"], default="both")
    parser.add_argument(
        "--hold-seconds", type=float, default=5, help="Mock shell duration, at most 60"
    )
    parser.add_argument("--timeout", type=float, default=90, help="Deadline per case in seconds")
    args = parser.parse_args()
    print(
        json.dumps(
            check(
                args.client_dir.expanduser().resolve(),
                args.output.expanduser().absolute(),
                args.mode,
                args.hold_seconds,
                args.timeout,
            )
        )
    )
