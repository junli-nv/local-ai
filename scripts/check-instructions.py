"""Native OpenCode instruction forwarding check using a local mock API; no GPU."""

import argparse
import json
import os
import subprocess
import tempfile
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from local_ai.artifacts import validate
from local_ai.client import prepare

MARKER = "LOCAL_AI_PERSONAL_RULES_7e63d91a"


def check(assets):
    manifest = validate(assets)
    captured = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            body = json.dumps({"data": [{"id": "instruction-check"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self):
            payload = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            captured.append(payload)
            response = {
                "id": "chatcmpl-instructions",
                "object": "chat.completion.chunk",
                "created": 1,
                "model": "instruction-check",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"role": "assistant", "content": "OK"},
                        "finish_reason": None,
                    }
                ],
            }
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream")
            self.end_headers()
            self.wfile.write(("data: " + json.dumps(response) + "\n\n").encode())
            response["choices"][0].update(delta={}, finish_reason="stop")
            response["usage"] = {"prompt_tokens": 10, "completion_tokens": 1, "total_tokens": 11}
            self.wfile.write(("data: " + json.dumps(response) + "\n\ndata: [DONE]\n\n").encode())
            self.wfile.flush()

        def log_message(self, *args):
            pass

    with tempfile.TemporaryDirectory(prefix="local-ai-instructions-") as directory:
        root = Path(directory)
        config = root / "personal-config"
        rules = config / "opencode/AGENTS.md"
        rules.parent.mkdir(parents=True)
        rules.write_text("# Personal instruction\n" + MARKER + "\n")
        state, session, project = (root / name for name in ("state", "session", "project"))
        for path in (state, session, project):
            path.mkdir()
        (project / "AGENTS.md").write_text("LOCAL_AI_PROJECT_RULES_b1a8049f\n")
        api = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=api.serve_forever, daemon=True)
        worker.start()
        try:
            with patch.dict(os.environ, {"XDG_CONFIG_HOME": str(config)}):
                env = prepare(
                    state,
                    assets,
                    session,
                    f"http://127.0.0.1:{api.server_port}/v1",
                    "instruction-check",
                    project,
                )
            result = subprocess.run(
                [
                    str(assets / "bin/opencode"),
                    "run",
                    "--dir",
                    str(project),
                    "--format",
                    "json",
                    "Return OK without tools.",
                ],
                env=env,
                cwd=project,
                text=True,
                capture_output=True,
                timeout=35,
            )
            if result.returncode:
                raise RuntimeError("Native client failed: " + result.stderr)
            instructions = "\n".join(
                str(message.get("content", ""))
                for body in captured
                for message in body.get("messages", [])
                if message.get("role") in {"system", "developer"}
            )
            checks = {
                "client_version": manifest["version"],
                "requests": len(captured),
                "personal_rules_in_model_context": MARKER in instructions,
                "project_rules_in_model_context": "LOCAL_AI_PROJECT_RULES_b1a8049f" in instructions,
                "built_in_guidance_in_model_context": "documents_read_document" in instructions,
                "session_config_isolated": env["XDG_CONFIG_HOME"] == str(session / "config"),
                "personal_rules_unchanged": rules.read_text()
                == "# Personal instruction\n" + MARKER + "\n",
            }
            print(json.dumps(checks))
            if not all(
                value for key, value in checks.items() if key not in {"client_version", "requests"}
            ):
                raise RuntimeError("Native instruction forwarding failed")
        finally:
            api.shutdown()
            api.server_close()
            worker.join(timeout=3)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--client-dir", type=Path, required=True)
    check(parser.parse_args().client_dir.resolve())
