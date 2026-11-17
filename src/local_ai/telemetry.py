"""Per-launch local API observation. No prompts, credentials or response text are persisted."""

import contextlib
import http.client
import json
import os
import socket
import threading
import time
import urllib.parse
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


def append(path, value):
    data = (json.dumps(value, ensure_ascii=False) + "\n").encode()
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW, 0o600)
    try:
        os.fchmod(fd, 0o600)
        os.write(fd, data)
    finally:
        os.close(fd)


class Observation:
    """Bounded SSE observer; bytes are forwarded unchanged, even for unknown frames."""

    def __init__(self):
        self.buffer = b""
        self.first = None
        self.usage = None
        self.finish = None
        self.done = False
        self.coverage = True

    def event(self, value):
        if not isinstance(value, dict):
            self.coverage = False
            return
        if isinstance(value.get("usage"), dict):
            self.usage = value["usage"]
        choices = value.get("choices") or []
        if not isinstance(choices, list):
            self.coverage = False
            return
        for choice in choices:
            if not isinstance(choice, dict):
                self.coverage = False
                continue
            delta = choice.get("delta") or {}
            if not isinstance(delta, dict):
                self.coverage = False
                continue
            if self.first is None and any(
                delta.get(k) for k in ("content", "reasoning_content", "tool_calls")
            ):
                self.first = time.monotonic()
            if choice.get("finish_reason"):
                self.finish = choice["finish_reason"]

    def feed(self, chunk):
        self.buffer += chunk
        while b"\n" in self.buffer:
            line, self.buffer = self.buffer.split(b"\n", 1)
            if not line.startswith(b"data:"):
                continue
            line = line[5:].strip()
            if line == b"[DONE]":
                self.done = True
                continue
            try:
                self.event(json.loads(line))
            except (ValueError, TypeError):
                self.coverage = False
        if len(self.buffer) > 1024 * 1024:
            self.buffer = b""
            self.coverage = False

    def fields(self):
        usage = self.usage or {}
        details = usage.get("prompt_tokens_details") or {}
        if not isinstance(details, dict):
            details = {}
        # Missing is unknown, never zero. Only take actual API-reported token counts.
        numbers = {}
        for key, value in {
            "prompt_tokens": usage.get("prompt_tokens"),
            "completion_tokens": usage.get("completion_tokens"),
            "cached_tokens": details.get("cached_tokens"),
        }.items():
            numbers[key] = value if isinstance(value, int) and value >= 0 else None
        return {
            **numbers,
            "finish_reason": self.finish,
            "stream_done": self.done,
            "observation_complete": self.coverage and not self.buffer.strip(),
        }


@contextlib.contextmanager
def proxy(base, directory, timeout=600):
    """One fixed upstream, no redirects/retries. Stop listener and active sockets on exit."""
    target = urllib.parse.urlsplit(base)
    if target.scheme not in ("http", "https") or not target.hostname:
        raise ValueError("Expected HTTP(S) endpoint")
    prefix = "/" + uuid.uuid4().hex
    active = set()
    sockets = set()
    lock = threading.Lock()
    path = Path(directory) / "requests.jsonl"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            self.forward()

        def do_POST(self):
            self.forward()

        def forward(self):
            route = urllib.parse.urlsplit(self.path).path
            if route not in {
                prefix + "/v1/models",
                prefix + "/v1/chat/completions",
                prefix + "/v1/completions",
            }:
                self.send_error(404)
                return
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length < 0 or length > 64 * 1024 * 1024:
                    raise ValueError()
            except ValueError:
                self.send_error(413)
                return
            is_model = route.endswith(("/chat/completions", "/completions"))
            payload = self.rfile.read(length)
            started = time.monotonic()
            observer = Observation()
            record = {
                "id": uuid.uuid4().hex,
                "started": time.time(),
                "session_id": self.headers.get("X-Local-AI-Session"),
                "agent": self.headers.get("X-Local-AI-Agent"),
                "state": "failed",
                "status": None,
            }
            cls = (
                http.client.HTTPSConnection
                if target.scheme == "https"
                else http.client.HTTPConnection
            )
            conn = cls(target.hostname, target.port, timeout=timeout)
            with lock:
                active.add(conn)
            sent = False
            upstream_socket = None
            try:
                headers = {
                    k: v
                    for k, v in self.headers.items()
                    if k.lower() in {"authorization", "content-type", "accept"}
                }
                headers["Accept-Encoding"] = "identity"
                route = target.path.rstrip("/") + route[len(prefix + "/v1") :]
                if urllib.parse.urlsplit(self.path).query:
                    route += "?" + urllib.parse.urlsplit(self.path).query
                conn.request(self.command, route, payload or None, headers)
                response = conn.getresponse()
                upstream_socket = conn.sock
                if upstream_socket is None and response.fp is not None:
                    upstream_socket = getattr(getattr(response.fp, "raw", None), "_sock", None)
                with lock:
                    if upstream_socket:
                        sockets.add(upstream_socket)
                record["status"] = response.status
                self.send_response(response.status)
                for key in ("Content-Type", "Content-Encoding", "Retry-After", "Content-Length"):
                    if response.getheader(key) is not None:
                        self.send_header(key, response.getheader(key))
                self.send_header("Connection", "close")
                self.end_headers()
                sent = True
                stream = "text/event-stream" in response.getheader("Content-Type", "")
                body = bytearray()
                while True:
                    chunk = response.read1(65536)
                    if not chunk:
                        break
                    if stream:
                        observer.feed(chunk)
                    elif len(body) <= 1024 * 1024:
                        body.extend(chunk)
                    self.wfile.write(chunk)
                    self.wfile.flush()
                if not stream and len(body) <= 1024 * 1024:
                    try:
                        observer.event(json.loads(body))
                        observer.done = True
                    except ValueError:
                        observer.coverage = False
                record["state"] = (
                    "completed" if response.status < 400 and (observer.done) else "incomplete"
                )
            except (OSError, http.client.HTTPException) as error:
                record["error_type"] = type(error).__name__
                if not sent:
                    self.send_error(502, "Upstream request failed")
            finally:
                now = time.monotonic()
                record.update(observer.fields())
                record["elapsed_seconds"] = now - started
                record["first_content_seconds"] = (
                    observer.first - started if observer.first is not None else None
                )
                if is_model:
                    append(path, record)
                conn.close()
                with lock:
                    active.discard(conn)
                    sockets.discard(upstream_socket)
                self.close_connection = True

    api = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    api.daemon_threads = True
    worker = threading.Thread(target=api.serve_forever, daemon=True)
    worker.start()
    try:
        yield f"http://127.0.0.1:{api.server_port}{prefix}/v1"
    finally:
        api.shutdown()
        with lock:
            for upstream_socket in list(sockets):
                try:
                    upstream_socket.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
            for conn in list(active):
                conn.close()
        deadline = time.monotonic() + 2
        while time.monotonic() < deadline:
            with lock:
                if not active:
                    break
            time.sleep(0.02)
        api.server_close()
        worker.join(timeout=3)


def lines(path):
    result, errors = [], 0
    if not Path(path).exists():
        return result, errors
    with Path(path).open() as stream:
        for line in stream:
            try:
                value = json.loads(line)
                if isinstance(value, dict):
                    result.append(value)
                else:
                    errors += 1
            except ValueError:
                errors += 1
    return result, errors


def report(directory):
    directory = Path(directory)
    metadata = json.loads((directory / "run.json").read_text())
    requests, bad_requests = lines(directory / "requests.jsonl")
    requests.sort(key=lambda r: r.get("started", 0))
    events, bad_events = lines(directory / "events.jsonl")
    tools = {}
    for event in events:
        if event.get("kind") == "tool":
            tools[(event.get("session_id"), event.get("message_id"), event.get("call_id"))] = event
    pending = [v for v in tools.values() if v.get("status") not in ("completed", "error")]
    spans = [
        max(0, v["end"] - v["start"]) / 1000
        for v in tools.values()
        if isinstance(v.get("start"), (int, float)) and isinstance(v.get("end"), (int, float))
    ]
    sessions = sorted({e["session_id"] for e in events if e.get("session_id")})
    cached = [r["cached_tokens"] for r in requests if r.get("cached_tokens") is not None]
    value = {
        "run": metadata,
        "sessions": sessions,
        "requests": requests,
        "tool_calls": list(tools.values()),
        "pending_tools": pending,
        "tool_seconds_sum": sum(spans) if spans else (None if tools else 0),
        "tool_timing_samples": len(spans),
        "tool_timing_missing": len(tools) - len(spans),
        "tool_timing_note": "sum; parallel spans may overlap",
        "cache_tokens": sum(cached) if cached and len(cached) == len(requests) else None,
        "cache_source": "API usage.prompt_tokens_details.cached_tokens; null means unknown",
        "compaction_attempts": sum(e.get("kind") == "compaction" for e in events),
        "event_count": len(events),
        "malformed_records": bad_requests + bad_events,
        "recovery": "Inspect pending tools and external effects before resuming; never replay automatically.",
    }
    value["observer_ready"] = any(e.get("kind") == "observer_ready" for e in events)
    value["api_seconds_sum"] = sum(r.get("elapsed_seconds", 0) for r in requests)
    value["latest_input_tokens"] = next(
        (r["prompt_tokens"] for r in reversed(requests) if r.get("prompt_tokens") is not None), None
    )
    value["context_limit"] = metadata.get("context_limit")
    value["context_fraction"] = (
        value["latest_input_tokens"] / value["context_limit"]
        if value["latest_input_tokens"] is not None and value["context_limit"]
        else None
    )
    primary = metadata.get("requested_session")
    if not primary and len(sessions) == 1:
        primary = sessions[0]
    value["resume_command"] = None
    if primary and all(metadata.get(k) for k in ("endpoint", "project", "state_dir", "client_dir")):
        value["resume_command"] = [
            metadata.get("launcher", "local-ai"),
            "chat",
            "--endpoint",
            metadata["endpoint"],
            "--project",
            metadata["project"],
            "--state-dir",
            metadata["state_dir"],
            "--client-dir",
            metadata["client_dir"],
            "--model",
            metadata["model"],
            "--session",
            primary,
        ]
    value["last_event"] = events[-1] if events else None
    value["incomplete_requests"] = [
        r["id"] for r in requests if r.get("state") != "completed" and r.get("id")
    ]
    value["request_observations_missing"] = (
        max(0, sum(e.get("kind") == "model_start" for e in events) - len(requests))
        if metadata.get("request_observer_enabled", True)
        else None
    )
    if metadata.get("state") in ("running", "starting"):
        try:
            from .tasks import identity

            os.kill(metadata["pid"], 0)
            if (
                metadata.get("pid_identity")
                and identity(metadata["pid"]) != metadata["pid_identity"]
            ):
                value["run"] = {**metadata, "state": "interrupted"}
        except (ProcessLookupError, KeyError):
            value["run"] = {**metadata, "state": "interrupted"}
    phase = value["run"]["state"]
    if phase in ("running", "starting"):
        last = value["last_event"] or {}
        if pending:
            phase = "tool_execution"
        elif last.get("kind") == "waiting":
            phase = "waiting_for_user"
        elif last.get("kind") == "model_start":
            phase = "model_request"
        elif last.get("kind") == "status":
            phase = {"idle": "waiting_for_user", "retry": "retrying"}.get(
                last.get("status"), "active"
            )
    value["phase"] = phase
    value["observer_ready_seconds"] = next(
        (
            (e["time"] / 1000 - metadata["started"])
            for e in events
            if e.get("kind") == "observer_ready" and e.get("time") and metadata.get("started")
        ),
        None,
    )
    return value
