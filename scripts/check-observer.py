"""Native tool, resume, observer and compaction contract; local mock API, no GPU."""

import argparse
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from local_ai.client import prepare
from local_ai.tasks import stop
from local_ai.telemetry import lines, report


def request(url, data=None, timeout=25):
    req = urllib.request.Request(
        url,
        None if data is None else json.dumps(data).encode(),
        {"Content-Type": "application/json"},
    )
    with urllib.request.build_opener(urllib.request.ProxyHandler({})).open(
        req, timeout=timeout
    ) as response:
        return json.load(response)


def check(assets):
    calls = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"data": [{"id": "observer-check"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            value = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            calls.append(value)
            tool_results = sum(m.get("role") == "tool" for m in value.get("messages", []))
            functions = {t["function"]["name"] for t in value.get("tools", [])}
            if functions and tool_results < 1:
                assert "bash" in functions, functions
                delta = {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_first",
                            "type": "function",
                            "function": {
                                "name": "bash",
                                "arguments": json.dumps(
                                    {
                                        "command": "printf 'FIRST\\n' > ledger.txt",
                                        "description": "Create ledger",
                                    }
                                ),
                            },
                        }
                    ]
                }
                finish = "tool_calls"
            elif (
                functions
                and tool_results < 2
                and any(
                    "APPEND_SECOND" in str(m.get("content", "")) for m in value.get("messages", [])
                )
            ):
                delta = {
                    "tool_calls": [
                        {
                            "index": 0,
                            "id": "call_second",
                            "type": "function",
                            "function": {
                                "name": "bash",
                                "arguments": json.dumps(
                                    {
                                        "command": "printf 'SECOND\\n' >> ledger.txt",
                                        "description": "Append once",
                                    }
                                ),
                            },
                        }
                    ]
                }
                finish = "tool_calls"
            else:
                delta, finish = (
                    {
                        "content": "Objective: ledger. FIRST completed. Preserve constraints; verify before repeating writes."
                    },
                    "stop",
                )
            chunk = {
                "id": "cmpl-check",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "observer-check",
                "choices": [{"index": 0, "delta": delta, "finish_reason": None}],
            }
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(("data: " + json.dumps(chunk) + "\n\n").encode())
            chunk["choices"][0].update(delta={}, finish_reason=finish)
            chunk["usage"] = {
                "prompt_tokens": 100,
                "completion_tokens": 10,
                "total_tokens": 110,
                "prompt_tokens_details": {"cached_tokens": 80},
            }
            self.wfile.write(("data: " + json.dumps(chunk) + "\n\ndata: [DONE]\n\n").encode())
            self.wfile.flush()

        def log_message(self, *args):
            pass

    with tempfile.TemporaryDirectory(prefix="local-ai-observer-") as tmp:
        root = Path(tmp)
        project = root / "project"
        project.mkdir()
        env = dict(
            os.environ,
            HOME=str(root / "home"),
            XDG_CONFIG_HOME=str(root / "config"),
            XDG_STATE_HOME=str(root / "user-state"),
            PYTHONPATH=os.pathsep.join(sys.path),
        )
        api = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        thread = threading.Thread(target=api.serve_forever)
        thread.start()
        endpoint = f"http://127.0.0.1:{api.server_port}/v1"
        session = None
        summaries = []
        try:
            for prompt in ("Create FIRST.", "APPEND_SECOND without repeating FIRST."):
                command = [
                    sys.executable,
                    "-c",
                    "from local_ai.cli import main; raise SystemExit(main())",
                    "chat",
                    "--client-dir",
                    str(assets),
                    "--endpoint",
                    endpoint,
                    "--model",
                    "observer-check",
                    "--state-dir",
                    str(root / "state"),
                    "--project",
                    str(project),
                    "--run-timeout",
                    "25",
                    "--run",
                    prompt,
                ]
                if session:
                    command += ["--session", session]
                result = subprocess.run(
                    command, env=env, capture_output=True, text=True, timeout=40
                )
                if result.returncode:
                    raise RuntimeError(result.stderr + result.stdout)
                files = sorted(
                    (root / "state").glob("services/*/logs/*/run.json"),
                    key=lambda p: p.stat().st_mtime,
                )
                value = report(files[-1].parent)
                assert value["observer_ready"], value
                assert len(value["sessions"]) == 1, value
                if session:
                    assert value["sessions"] == [session]
                session = value["sessions"][0]
                assert value["tool_calls"], value
                assert not value["pending_tools"], value
                assert value["requests"], value
                assert all(r["cached_tokens"] == 80 for r in value["requests"]), value
                assert value["resume_command"][-1] == session, value
                summaries.append(value)
                print(
                    json.dumps(
                        {
                            "native_turn": len(summaries),
                            "tools": len(value["tool_calls"]),
                            "requests": len(value["requests"]),
                        }
                    ),
                    flush=True,
                )
            assert (project / "ledger.txt").read_text().splitlines() == ["FIRST", "SECOND"]
            # Force native compaction via its public session API in the same temporary history.
            state = files[-1].parent.parent.parent
            setup = root / "compaction"
            setup.mkdir()
            with tempfile.TemporaryFile() as log:
                with patch.dict(os.environ, env):
                    prepared = prepare(state, assets, setup, endpoint, "observer-check", project)
                with socket.socket() as sock:
                    sock.bind(("127.0.0.1", 0))
                    port = sock.getsockname()[1]
                backend = subprocess.Popen(
                    [
                        str(assets / "bin/opencode"),
                        "serve",
                        "--hostname",
                        "127.0.0.1",
                        "--port",
                        str(port),
                    ],
                    env=prepared,
                    cwd=project,
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                )
                try:
                    base = f"http://127.0.0.1:{port}"
                    deadline = time.monotonic() + 20
                    while True:
                        try:
                            request(base + "/global/health", timeout=2)
                            break
                        except (OSError, urllib.error.URLError):
                            if time.monotonic() >= deadline or backend.poll() is not None:
                                log.seek(0)
                                raise RuntimeError(log.read().decode())
                            time.sleep(0.2)
                    request(
                        base + f"/session/{session}/summarize",
                        {
                            "providerID": "local-deepseek",
                            "modelID": "observer-check",
                            "auto": False,
                        },
                    )
                    events = lines(setup / "events.jsonl")[0]
                    assert any(e.get("kind") == "compaction" for e in events), events
                    assert any(
                        "Preserve the user's objective" in json.dumps(body) for body in calls
                    ), "Compaction preservation prompt missing"
                finally:
                    stop(backend)
            print(
                json.dumps(
                    {
                        "client": "native",
                        "tool_roundtrips": 2,
                        "same_session_resume": True,
                        "cache_usage_observed": True,
                        "compaction_hook": True,
                        "ledger_exactly_once": True,
                    }
                )
            )
        finally:
            api.shutdown()
            api.server_close()
            thread.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-dir", type=Path, required=True)
    check(parser.parse_args().client_dir.resolve())
