"""An owned, loopback-only SSH tunnel for one client invocation."""

import ipaddress
import json
import re
import socket
import subprocess
import time
import urllib.request
from pathlib import Path


def destination(server, user=None):
    if "@" in server:
        if user:
            raise ValueError("Specify SSH user once")
        user, server = server.split("@", 1)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,252}", server):
        try:
            ipaddress.ip_address(server)
        except ValueError:
            raise ValueError("Invalid SSH hostname/address") from None
    if user and not re.fullmatch(r"[A-Za-z0-9_][A-Za-z0-9_.-]{0,63}", user):
        raise ValueError("Invalid SSH user")
    return (user + "@" if user else "") + server


def ssh_command(server, user, ssh_port, local_port, remote_port):
    for port in [ssh_port, local_port, remote_port]:
        if not 1 <= port <= 65535:
            raise ValueError("Invalid TCP port")
    return [
        "ssh",
        "-N",
        "-T",
        "-o",
        "BatchMode=yes",
        "-o",
        "ExitOnForwardFailure=yes",
        "-o",
        "ServerAliveInterval=30",
        "-o",
        "ServerAliveCountMax=3",
        "-p",
        str(ssh_port),
        "-L",
        "127.0.0.1:%d:127.0.0.1:%d" % (local_port, remote_port),
        "--",
        destination(server, user),
    ]


def available_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_endpoint(base, model, process=None, seconds=15):
    deadline = time.monotonic() + seconds
    last = None
    while time.monotonic() < deadline:
        if process is not None and process.poll() is not None:
            raise RuntimeError(
                "SSH tunnel exited; verify SSH login/host key and inspect tunnel.log"
            )
        try:
            with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
                base.rstrip("/") + "/models", timeout=2
            ) as response:
                data = json.load(response)
            if model not in {row["id"] for row in data["data"]}:
                raise ValueError("Server does not advertise model " + model)
            return
        except (OSError, KeyError, json.JSONDecodeError) as error:
            last = str(error)
        time.sleep(0.2)
    raise RuntimeError("Model API is not ready: " + str(last))


class Tunnel:
    def __init__(self, server, user, ssh_port, remote_port, local_port, log):
        self.port = local_port or available_port()
        self.command = ssh_command(server, user, ssh_port, self.port, remote_port)
        self.log = Path(log)
        self.process = None
        self.stream = None

    def __enter__(self):
        self.stream = self.log.open("a")
        self.stream.write(json.dumps({"command": self.command}) + "\n")
        self.stream.flush()
        try:
            self.process = subprocess.Popen(
                self.command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=self.stream,
            )
        except Exception:
            self.stream.close()
            raise
        return self

    @property
    def endpoint(self):
        return "http://127.0.0.1:%d/v1" % self.port

    def __exit__(self, *exc):
        if self.process and self.process.poll() is None:
            self.process.terminate()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait()
        if self.stream:
            self.stream.close()
