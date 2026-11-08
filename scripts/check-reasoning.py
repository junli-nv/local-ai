"""CPU-only native variant switching contract; isolated state and a mock model."""

import argparse
import fcntl
import json
import os
import pty
import select
import signal
import socket
import struct
import subprocess
import tempfile
import termios
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from local_ai.artifacts import validate
from local_ai.client import prepare
from local_ai.common import private_dir
from local_ai.profiles import catalog

MODEL = catalog()["model"]["served_name"]


def request(url, data=None, timeout=15):
    req = urllib.request.Request(
        url,
        data=None if data is None else json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        raise RuntimeError("Native request failed: " + error.read().decode()) from error


def stop_process(child):
    if child is None:
        return
    if child.poll() is None:
        os.killpg(child.pid, signal.SIGTERM)
    try:
        child.wait(timeout=5)
    except subprocess.TimeoutExpired:
        os.killpg(child.pid, signal.SIGKILL)
        child.wait(timeout=5)


def check_keyboard(assets, base, session_id, project, env, captured):
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 44, 160, 0, 0))
    child = subprocess.Popen(
        [str(assets / "bin/opencode"), "attach", base, "--session", session_id],
        cwd=project,
        env=dict(env, TERM="xterm-256color"),
        stdin=slave,
        stdout=slave,
        stderr=slave,
        start_new_session=True,
    )
    os.close(slave)
    output = bytearray()

    def drain_until(predicate, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline and child.poll() is None:
            if select.select([master], [], [], 0.1)[0]:
                try:
                    output.extend(os.read(master, 65536))
                except OSError:
                    break
            if predicate():
                return True
        return predicate()

    try:
        assert drain_until(lambda: b"reasoning variant contract" in output, 20), output.decode(
            errors="replace"
        )
        count = len(captured)
        os.write(master, b"Return OK. No tools.\r")
        assert drain_until(lambda: len(captured) > count, 15), output.decode(errors="replace")
        assert captured[-1].get("chat_template_kwargs") is None, captured[-1].get(
            "chat_template_kwargs"
        )
        assert captured[-1].get("reasoning_effort") is None, captured[-1].get("reasoning_effort")
        drain_until(lambda: False, 1)
        payload = None
        for _ in range(2):
            count = len(captured)
            os.write(master, b"\x14")
            drain_until(lambda: False, 0.5)
            os.write(master, b"Return OK. No tools.\r")
            assert drain_until(lambda: len(captured) > count, 15), output.decode(errors="replace")
            payload = captured[-1].get("chat_template_kwargs")
            drain_until(lambda: False, 1)
            if payload:
                break
        assert (
            payload
            and payload.get("thinking") is True
            and payload.get("reasoning_effort") in (25, 50, 75, 100)
        ), payload
        os.write(master, b"\x18q")
        assert drain_until(lambda: child.poll() is not None, 8), "TUI did not exit"
        assert child.wait(timeout=3) == 0, output.decode(errors="replace")
        print("CTRL_T_REQUEST_VERIFIED", payload, flush=True)
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
        os.close(master)


def check(assets):
    manifest = validate(assets)
    captured = []

    class MockModel(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"data": [{"id": MODEL}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            captured.append(payload)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            chunks = [{"role": "assistant"}]
            if payload.get("chat_template_kwargs", {}).get("thinking", True):
                chunks.append({"reasoning_content": "A short mock check."})
            chunks.append({"content": "OK"})
            for delta in chunks:
                event = {
                    "id": "chatcmpl-contract",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": MODEL,
                    "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
                }
                self.wfile.write(("data: " + json.dumps(event) + "\n\n").encode())
            event["choices"] = [{"index": 0, "delta": {}, "finish_reason": "stop"}]
            event["usage"] = {"prompt_tokens": 8, "completion_tokens": 4, "total_tokens": 12}
            self.wfile.write(("data: " + json.dumps(event) + "\n\ndata: [DONE]\n\n").encode())
            self.wfile.flush()

        def log_message(self, *args):
            pass

    with tempfile.TemporaryDirectory(prefix="local-ai-reasoning-contract-") as folder:
        root = Path(folder)
        project = root / "project"
        project.mkdir()
        state = private_dir(root / "private")
        session = private_dir(state / "setup")
        api = ThreadingHTTPServer(("127.0.0.1", 0), MockModel)
        threading.Thread(target=api.serve_forever, daemon=True).start()
        env = prepare(
            state, assets, session, "http://127.0.0.1:%d/v1" % api.server_port, MODEL, project
        )
        env["HOME"] = str(root / "home")
        Path(env["HOME"]).mkdir()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = "http://127.0.0.1:%d" % port
        backend = None
        try:
            with tempfile.TemporaryFile() as log:
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
                deadline = time.monotonic() + 25
                while True:
                    try:
                        request(base + "/global/health", timeout=1)
                        break
                    except (OSError, urllib.error.URLError):
                        if backend.poll() is not None or time.monotonic() >= deadline:
                            log.seek(0)
                            raise RuntimeError(
                                "Native startup failed: " + log.read().decode(errors="replace")
                            )
                        time.sleep(0.2)
                providers = request(base + "/provider")
                for provider in providers.get("all", []):
                    if provider["id"] == "local-deepseek":
                        resolved = provider["models"][MODEL]["variants"]
                        assert set(resolved) == {
                            "default",
                            "low",
                            "high",
                            "xhigh",
                            "max",
                            "none",
                        }, resolved
                        assert resolved["default"] == {}
                        print("RESOLVED_VARIANTS", list(resolved), flush=True)
                created = request(base + "/session", {"title": "reasoning variant contract"})
                expected = [
                    ("default", None),
                    ("low", {"thinking": True, "reasoning_effort": 25}),
                    ("high", {"thinking": True, "reasoning_effort": 50}),
                    ("xhigh", {"thinking": True, "reasoning_effort": 75}),
                    ("max", {"thinking": True, "reasoning_effort": 100}),
                    ("none", {"thinking": False}),
                    ("default", None),
                ]
                for variant, kwargs in expected:
                    count = len(captured)
                    response = request(
                        base + "/session/" + created["id"] + "/message",
                        {
                            "model": {"providerID": "local-deepseek", "modelID": MODEL},
                            "variant": variant,
                            "parts": [{"type": "text", "text": "Return OK. No tools."}],
                        },
                    )
                    assert len(captured) == count + 1, (variant, len(captured) - count)
                    actual = captured[-1]
                    assert actual.get("chat_template_kwargs") == kwargs, (
                        variant,
                        actual.get("chat_template_kwargs"),
                    )
                    assert actual.get("reasoning_effort") in (None, variant)
                    assert response["info"].get("error") is None, response["info"].get("error")
                    print("VARIANT_REQUEST_VERIFIED", variant, kwargs, flush=True)
                check_keyboard(assets, base, created["id"], project, env, captured)
                report = {
                    "client_version": manifest["version"],
                    "same_session": True,
                    "same_process": backend.poll() is None,
                    "api_variant_requests": len(expected),
                    "http_requests": len(captured),
                    "default_restored": True,
                    "mock_only": True,
                    "ctrl_t_verified": True,
                }
                print(json.dumps(report), flush=True)
        finally:
            try:
                stop_process(backend)
            finally:
                api.shutdown()
                api.server_close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-dir", type=Path, required=True)
    check(parser.parse_args().client_dir.expanduser().resolve())
