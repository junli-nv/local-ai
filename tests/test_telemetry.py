import contextlib
import io
import json
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from local_ai import tasks, telemetry
from local_ai.common import atomic_json


@contextlib.contextmanager
def upstream(body, status=200):
    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            received.append(
                (
                    self.path,
                    dict(self.headers),
                    self.rfile.read(int(self.headers["Content-Length"])),
                )
            )
            self.send_response(status)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            # Exercise incremental parsing without reserializing the upstream stream.
            for index in range(0, len(body), 7):
                self.wfile.write(body[index : index + 7])
                self.wfile.flush()

        def log_message(self, *args):
            pass

    api = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    worker = threading.Thread(target=api.serve_forever)
    worker.start()
    try:
        yield f"http://127.0.0.1:{api.server_port}/v1", received
    finally:
        api.shutdown()
        api.server_close()
        worker.join()


def stream(cached=True, done=True):
    usage = {"prompt_tokens": 100, "completion_tokens": 2}
    if cached:
        usage["prompt_tokens_details"] = {"cached_tokens": 80}
    frames = [
        {"choices": [{"delta": {"role": "assistant"}}]},
        {"choices": [{"delta": {"reasoning_content": "private-thinking"}}]},
        {
            "choices": [{"delta": {"content": "private-answer"}, "finish_reason": "stop"}],
            "usage": usage,
        },
    ]
    body = b"".join(b"data: " + json.dumps(x).encode() + b"\n\n" for x in frames)
    return body + (b"data: [DONE]\n\n" if done else b"")


class TelemetryTests(unittest.TestCase):
    def test_stream_preserved_and_usage_is_actual_without_private_content(self):
        body = stream()
        with tempfile.TemporaryDirectory() as root, upstream(body) as (base, received):
            with telemetry.proxy(base, root) as local:
                request = urllib.request.Request(
                    local + "/chat/completions",
                    b'{"messages":[]}',
                    headers={"Content-Type": "application/json", "X-Local-AI-Session": "ses_a"},
                )
                self.assertEqual(urllib.request.urlopen(request).read(), body)
            records, bad = telemetry.lines(Path(root) / "requests.jsonl")
            self.assertEqual(bad, 0)
            self.assertEqual(len(records), 1)
            row = records[0]
            self.assertEqual(row["state"], "completed")
            self.assertEqual(row["cached_tokens"], 80)
            self.assertEqual(row["prompt_tokens"], 100)
            self.assertEqual(row["session_id"], "ses_a")
            self.assertGreaterEqual(row["first_content_seconds"], 0)
            self.assertTrue(row["observation_complete"])
            self.assertEqual(received[0][0], "/v1/chat/completions")
            self.assertNotIn("X-Local-AI-Session", received[0][1])
            text = (Path(root) / "requests.jsonl").read_text()
            self.assertNotIn("private", text)
            self.assertEqual((Path(root) / "requests.jsonl").stat().st_mode & 0o777, 0o600)

    def test_missing_cache_is_unknown_and_truncated_stream_is_incomplete(self):
        with tempfile.TemporaryDirectory() as root, upstream(stream(False, False)) as (base, _):
            with telemetry.proxy(base, root) as local:
                urllib.request.urlopen(
                    urllib.request.Request(local + "/chat/completions", b"{}")
                ).read()
            row = telemetry.lines(Path(root) / "requests.jsonl")[0][0]
            self.assertIsNone(row["cached_tokens"])
            self.assertEqual(row["state"], "incomplete")

    def test_http_error_is_forwarded_and_never_retried(self):
        with tempfile.TemporaryDirectory() as root, upstream(b"failure", 429) as (base, received):
            with telemetry.proxy(base, root) as local:
                with self.assertRaises(urllib.error.HTTPError) as raised:
                    urllib.request.urlopen(
                        urllib.request.Request(local + "/chat/completions", b"{}")
                    )
                self.assertEqual(raised.exception.code, 429)
                raised.exception.read()
            self.assertEqual(len(received), 1)
            self.assertEqual(telemetry.lines(Path(root) / "requests.jsonl")[0][0]["status"], 429)

    def test_observation_malformed_fields_and_large_frame_do_not_crash(self):
        value = telemetry.Observation()
        value.feed(b'data: {"choices": "bad"}\n')
        value.feed(b"x" * (1024 * 1024 + 1))
        value.feed(b'\ndata: {"usage":{"prompt_tokens_details":"bad"}}\n')
        self.assertFalse(value.fields()["observation_complete"])
        self.assertIsNone(value.fields()["cached_tokens"])

    def test_report_preserves_uncertain_tools_and_original_endpoint(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            atomic_json(
                root / "run.json",
                {
                    "state": "running",
                    "pid": 99999999,
                    "endpoint": "http://gpu:18000/v1",
                    "model": "m",
                    "project": "/work",
                    "state_dir": "/state",
                    "client_dir": "/assets",
                    "context_limit": 1000,
                },
            )
            for row in [
                {"kind": "observer_ready"},
                {"kind": "tool", "session_id": "s", "call_id": "a", "status": "running"},
                {
                    "kind": "tool",
                    "session_id": "s",
                    "call_id": "b",
                    "status": "completed",
                    "start": 1000,
                    "end": 3000,
                },
            ]:
                telemetry.append(root / "events.jsonl", row)
            with (root / "events.jsonl").open("a") as out:
                out.write('{"partial"')
            value = telemetry.report(root)
            self.assertEqual(value["run"]["state"], "interrupted")
            self.assertEqual(len(value["pending_tools"]), 1)
            self.assertEqual(value["tool_seconds_sum"], 2)
            self.assertEqual(value["malformed_records"], 1)
            self.assertIn("http://gpu:18000/v1", value["resume_command"])
            self.assertIsNone(value["cache_tokens"])

    def test_unknown_tool_timing_is_not_zero(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            atomic_json(root / "run.json", {"state": "completed"})
            telemetry.append(
                root / "events.jsonl",
                {"kind": "tool", "session_id": "s", "call_id": "c", "status": "completed"},
            )
            value = telemetry.report(root)
            self.assertIsNone(value["tool_seconds_sum"])
            self.assertEqual(value["tool_timing_missing"], 1)

    def test_pid_reuse_does_not_claim_running(self):
        with tempfile.TemporaryDirectory() as root:
            atomic_json(
                Path(root) / "run.json",
                {"state": "running", "pid": os.getpid(), "pid_identity": "different"},
            )
            self.assertEqual(telemetry.report(root)["run"]["state"], "interrupted")


class TaskTests(unittest.TestCase):
    def run_child(self, root, script, timeout="0"):
        env = dict(os.environ, LOCAL_AI_HEARTBEAT="0", LOCAL_AI_RUN_TIMEOUT=timeout)
        binary = io.BytesIO()
        stdout = io.TextIOWrapper(binary)
        with patch("sys.stdout", stdout), contextlib.redirect_stderr(io.StringIO()):
            code = tasks.execute(
                [sys.executable, "-c", script], root, env, root / "terminal.log", "test"
            )
            stdout.flush()
        return code

    def test_success_records_exit_and_complete_output(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            self.assertEqual(self.run_child(root, "print('complete-output')"), 0)
            self.assertIn("complete-output", (root / "terminal.log").read_text())
            self.assertEqual(json.loads((root / "run.json").read_text())["state"], "completed")

    def test_deadline_stops_descendant_even_when_leader_exits_on_term(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            script = (
                "import subprocess,time,sys; "
                "p=subprocess.Popen([sys.executable,'-c','import time; time.sleep(30)']); "
                "print(p.pid,flush=True); time.sleep(30)"
            )
            self.assertEqual(self.run_child(root, script, ".4"), 124)
            pid = int((root / "terminal.log").read_text().strip())
            status = Path(f"/proc/{pid}/stat")
            if status.exists():
                self.assertEqual(status.read_text().rsplit(")", 1)[1].split()[0], "Z")
            self.assertEqual(json.loads((root / "run.json").read_text())["state"], "timed_out")

    def test_native_error_cannot_be_reported_as_success(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            telemetry.append(root / "events.jsonl", {"kind": "error"})
            self.assertEqual(self.run_child(root, "pass"), 1)
            self.assertEqual(json.loads((root / "run.json").read_text())["state"], "failed")


class SignalTests(unittest.TestCase):
    def test_sigterm_cleans_child_and_records_interruption(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            code = (
                "from pathlib import Path; import os,sys; from local_ai.tasks import execute; "
                "root=Path(sys.argv[1]); raise SystemExit(execute("
                "[sys.executable,'-c','import time; time.sleep(30)'],"
                "root,dict(os.environ,LOCAL_AI_HEARTBEAT='0'),root/'terminal.log','test'))"
            )
            runner = subprocess.Popen(
                [sys.executable, "-c", code, str(root)],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            try:
                deadline = time.monotonic() + 5
                while True:
                    if (root / "run.json").exists():
                        record = json.loads((root / "run.json").read_text())
                        if record["state"] == "running":
                            break
                    if time.monotonic() >= deadline:
                        self.fail("supervisor did not start")
                    time.sleep(0.02)
                runner.send_signal(signal.SIGTERM)
                self.assertEqual(runner.wait(timeout=6), 143)
                value = json.loads((root / "run.json").read_text())
                self.assertEqual(value["state"], "interrupted")
                proc = Path(f"/proc/{record['child_pid']}/stat")
                if proc.exists():
                    self.assertEqual(proc.read_text().rsplit(")", 1)[1].split()[0], "Z")
            finally:
                if runner.poll() is None:
                    runner.kill()
                    runner.wait()
