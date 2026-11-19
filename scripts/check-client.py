"""CPU-only native OpenCode contract check in disposable state; no inference."""

import argparse
import fcntl
import json
import os
import pty
import re
import select
import shlex
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
from local_ai.common import client_home, private_dir
from local_ai.history import resolve
from local_ai.paths import settings
from local_ai.resume import locate, register


class Models(BaseHTTPRequestHandler):
    def do_GET(self):
        body = json.dumps({"data": [{"id": "compat-model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *args):
        pass


def request(url, data=None, timeout=2):
    req = urllib.request.Request(
        url,
        data=None if data is None else json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        req, timeout=timeout
    ) as response:
        return json.load(response)


def interactive_exit(command):
    master, slave = pty.openpty()
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 44, 160, 0, 0))
    child = subprocess.Popen(
        command,
        stdin=slave,
        stdout=slave,
        stderr=slave,
        start_new_session=True,
        env=dict(os.environ, TERM="xterm-256color"),
    )
    os.close(slave)
    output = bytearray()
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline and child.poll() is None:
            if select.select([master], [], [], 0.2)[0]:
                try:
                    output.extend(os.read(master, 65536))
                except OSError:
                    break
            if b"local-ai compatibility session" in output:
                break
        if b"local-ai compatibility session" not in output:
            raise RuntimeError(f"Native TUI did not open the requested session: {output[-2048:]!r}")
        deadline = time.monotonic() + 10
        interrupt = time.monotonic() + 0.5
        while time.monotonic() < deadline:
            now = time.monotonic()
            if now >= interrupt and child.poll() is None:
                os.write(master, b"\x03")
                interrupt = now + 2
            if select.select([master], [], [], 0.2)[0]:
                try:
                    output.extend(os.read(master, 65536))
                except OSError:
                    break
            elif child.poll() is not None:
                break
        try:
            return bytes(output), child.wait(timeout=3)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError(f"Native TUI did not exit on Ctrl-C: {output[-2048:]!r}") from error
    finally:
        if child.poll() is None:
            os.killpg(child.pid, signal.SIGKILL)
            child.wait()
        os.close(master)


def check(assets):
    manifest = validate(assets)
    with tempfile.TemporaryDirectory(prefix="local-ai-contract-") as directory:
        root = Path(directory)
        os.environ["HOME"] = str(root / "home")
        os.environ["XDG_STATE_HOME"] = str(root / "user-state")
        project = root / "project with spaces"
        project.mkdir()
        api = ThreadingHTTPServer(("127.0.0.1", 0), Models)
        threading.Thread(target=api.serve_forever, daemon=True).start()
        base = "http://127.0.0.1:%d/v1" % api.server_port
        state_root = private_dir(client_home())
        key = resolve(state_root, base, settings().get("endpoint"))
        state = private_dir(state_root / "services" / key)
        session = private_dir(state / "logs" / "setup")
        env = prepare(state, assets, session, base, "compat-model", project)
        register(state_root, state, assets, base, "compat-model", project)
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        backend_url = "http://127.0.0.1:%d" % port
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
            try:
                deadline = time.monotonic() + 25
                while True:
                    try:
                        request(backend_url + "/global/health")
                        break
                    except (OSError, urllib.error.URLError):
                        if time.monotonic() >= deadline or backend.poll() is not None:
                            log.seek(0)
                            raise RuntimeError(
                                "Native backend failed: " + log.read().decode(errors="replace")
                            )
                        time.sleep(0.2)
                created = request(
                    backend_url + "/session?directory=" + urllib.parse.quote(str(project)),
                    {"title": "local-ai compatibility session"},
                    timeout=25,
                )
                session_id = created["id"]
            finally:
                if backend.poll() is None:
                    os.killpg(backend.pid, signal.SIGTERM)
                backend.wait(timeout=5)
        context, restored = locate(session_id)
        assert context["endpoint"] == base and restored == str(project)
        try:
            output, returncode = interactive_exit(
                [str(Path.home() / ".local/bin/opencode"), "-s", session_id]
            )
            plain = re.sub(rb"\x1b\[[0-?]*[ -/]*[@-~]", b"", output).decode(errors="replace")
            hint = re.search(r"(?m)^  Continue  ([^\r\n]+)", plain)
            if hint is None or f"opencode -s {session_id}" in plain:
                raise RuntimeError("Ctrl-C did not print the local-ai resume command")
            command = shlex.split(hint[1])
            if (
                Path(command[0]).name != "local-ai"
                or command[1] != "chat"
                or command[2:4] != ["--session", session_id]
                or command[command.index("--project") + 1] != str(project)
            ):
                raise RuntimeError("Unexpected local-ai resume command")
            replay, replay_code = interactive_exit(command)
            if replay_code or b"local-ai compatibility session" not in replay:
                raise RuntimeError("The displayed command did not restore the same session")
        finally:
            api.shutdown()
            api.server_close()
        loaded = b"local-ai compatibility session" in output
        mouse = [n for n in (1000, 1002, 1003, 1006) if f"\x1b[?{n}h".encode() in output]
        report = {
            "client_version": manifest["version"],
            "session_restored": loaded,
            "mouse_capture_enabled": mouse,
            "bracketed_paste": b"\x1b[?2004h" in output,
            "exit_code": returncode,
            "exit_hint_replay": True,
        }
        print(json.dumps(report))
        if not loaded or mouse or not report["bracketed_paste"] or returncode != 0:
            raise SystemExit("Native client contract failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-dir", type=Path, required=True)
    check(parser.parse_args().client_dir.expanduser().resolve())
