"""CPU-only native OpenCode contract check in disposable state; no inference."""

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
from local_ai.client import prepare, service_key
from local_ai.common import client_home, private_dir
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


def request(url, data=None):
    req = urllib.request.Request(
        url,
        data=None if data is None else json.dumps(data).encode(),
        headers={"Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=2) as response:
        return json.load(response)


def check(assets):
    manifest = validate(assets)
    with tempfile.TemporaryDirectory(prefix="local-ai-contract-") as directory:
        root = Path(directory)
        os.environ["HOME"] = str(root / "home")
        os.environ["XDG_STATE_HOME"] = str(root / "user-state")
        project = root / "project"
        project.mkdir()
        api = ThreadingHTTPServer(("127.0.0.1", 0), Models)
        threading.Thread(target=api.serve_forever, daemon=True).start()
        base = "http://127.0.0.1:%d/v1" % api.server_port
        state_root = private_dir(client_home())
        state = private_dir(state_root / "services" / service_key(base))
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
                )
                session_id = created["id"]
            finally:
                if backend.poll() is None:
                    os.killpg(backend.pid, signal.SIGTERM)
                backend.wait(timeout=5)
        context, restored = locate(session_id)
        assert context["endpoint"] == base and restored == str(project)
        master, slave = pty.openpty()
        fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack("HHHH", 44, 160, 0, 0))
        child = subprocess.Popen(
            [str(Path.home() / ".local/bin/opencode"), "-s", session_id],
            stdin=slave,
            stdout=slave,
            stderr=slave,
            start_new_session=True,
            env=dict(os.environ, TERM="xterm-256color"),
        )
        os.close(slave)
        output = bytearray()
        loaded = False
        try:
            deadline = time.monotonic() + 30
            while time.monotonic() < deadline and child.poll() is None:
                if select.select([master], [], [], 0.2)[0]:
                    try:
                        output.extend(os.read(master, 65536))
                    except OSError:
                        break
                if b"local-ai compatibility session" in output:
                    loaded = True
                    break
            os.write(master, b"\x18q")
            deadline = time.monotonic() + 8
            while time.monotonic() < deadline and child.poll() is None:
                if select.select([master], [], [], 0.2)[0]:
                    try:
                        output.extend(os.read(master, 65536))
                    except OSError:
                        break
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGTERM)
            child.wait(timeout=5)
        finally:
            if child.poll() is None:
                os.killpg(child.pid, signal.SIGKILL)
                child.wait()
            os.close(master)
            api.shutdown()
            api.server_close()
        mouse = [n for n in (1000, 1002, 1003, 1006) if f"\x1b[?{n}h".encode() in output]
        report = {
            "client_version": manifest["version"],
            "session_restored": loaded,
            "mouse_capture_enabled": mouse,
            "bracketed_paste": b"\x1b[?2004h" in output,
            "exit_code": child.returncode,
        }
        print(json.dumps(report))
        if not loaded or mouse or not report["bracketed_paste"] or child.returncode != 0:
            raise SystemExit("Native client contract failed")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-dir", type=Path, required=True)
    check(parser.parse_args().client_dir.expanduser().resolve())
