import contextlib
import io
import json
import os
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import patch

from local_ai import client
from local_ai.cli import main, parser
from local_ai.endpoint import endpoint_url, wait_endpoint


@contextlib.contextmanager
def model_api(model="test-model", statuses=(200,)):
    requests = []

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            requests.append(self.path)
            self.send_response(statuses[min(len(requests) - 1, len(statuses) - 1)])
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps({"data": [{"id": model}]}).encode())

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Handler) as http:
        thread = threading.Thread(
            target=lambda: http.serve_forever(poll_interval=0.01), daemon=True
        )
        thread.start()
        try:
            with patch.dict(os.environ, {"NO_PROXY": "127.0.0.1", "no_proxy": "127.0.0.1"}):
                yield "http://127.0.0.1:%d/v1" % http.server_port, requests
        finally:
            http.shutdown()
            thread.join(timeout=2)


class EndpointTests(unittest.TestCase):
    def test_valid_endpoints(self):
        for url in [
            "http://gpu-a:18000/v1",
            "https://proxy.example/api/v1",
            "http://127.0.0.1:28000/v1",
            "http://[::1]:18000/v1",
        ]:
            self.assertEqual(endpoint_url(url + "/"), url)

    def test_invalid_endpoints(self):
        for url in [
            "",
            "gpu-a:18000",
            "ftp://host/v1",
            "http://u:p@host/v1",
            "http://@host/v1",
            "http://host:0/v1",
            "http://host:65536/v1",
            "http://host:bad/v1",
            "http://0.0.0.0:18000/v1",
            "http://[::]:18000/v1",
            "http://host/v1?key=secret",
            "http://host/v1#x",
            "http://host\n/v1",
        ]:
            with self.subTest(url=url), self.assertRaises(ValueError):
                endpoint_url(url)

    def test_endpoint_configurable_and_legacy_options_rejected(self):
        with patch("local_ai.cli.settings", return_value={}):
            self.assertIsNone(parser().parse_args(["chat"]).endpoint)
            with contextlib.redirect_stderr(io.StringIO()) as output:
                self.assertEqual(main(["chat", "--check"]), 1)
            self.assertIn("Set --endpoint", output.getvalue())
        for extra in [["--server", "gpu-a"]]:
            with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
                parser().parse_args(["chat"] + extra)
        for option in ["--server", "--ssh-user", "--ssh-port", "--local-port", "--port"]:
            with self.subTest(option=option), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    parser().parse_args(
                        ["chat", "--endpoint", "http://gpu-a:18000/v1", option, "22"]
                    )
                self.assertEqual(error.exception.code, 2)
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            parser().parse_args(["client", "doctor"])

    def test_model_api_retry(self):
        with model_api(statuses=(503, 200)) as (base, requests):
            wait_endpoint(base, "test-model", seconds=3)
            self.assertEqual(requests, ["/v1/models", "/v1/models"])

    def test_wrong_model_fails(self):
        with model_api(model="other") as (base, _):
            with self.assertRaisesRegex(ValueError, "does not advertise model test-model"):
                wait_endpoint(base, "test-model")

    def test_unavailable_api_error(self):
        with model_api(statuses=(503,)) as (base, _):
            with self.assertRaisesRegex(RuntimeError, "Model API is not ready.*503"):
                wait_endpoint(base, "test-model", seconds=0.25)

    def assets(self, root):
        assets = root / "assets"
        (assets / "seed-cache").mkdir(parents=True)
        (assets / "manifest.json").write_text("{}")
        return assets

    def test_check_never_starts_subprocess(self):
        with tempfile.TemporaryDirectory() as directory, model_api() as (base, _):
            root = Path(directory)
            assets = self.assets(root)
            output = io.StringIO()
            with (
                patch("local_ai.client.validate", return_value={"arch": "amd64"}),
                patch(
                    "local_ai.client.subprocess.Popen", side_effect=AssertionError("no subprocess")
                ),
                patch(
                    "local_ai.client.subprocess.call", side_effect=AssertionError("no subprocess")
                ),
                contextlib.redirect_stdout(output),
            ):
                code = main(
                    [
                        "chat",
                        "--endpoint",
                        base,
                        "--model",
                        "test-model",
                        "--check",
                        "--client-dir",
                        str(assets),
                        "--state-dir",
                        str(root / "state"),
                        "--project",
                        str(root),
                    ]
                )
            result = json.loads(output.getvalue())
            self.assertEqual(code, 0)
            self.assertTrue(result["ready"])
            self.assertEqual(result["endpoint"], base)
            self.assertNotIn("tunnel_closes_on_exit", result)

    def test_run_records_endpoint_and_keeps_tools_on_client(self):
        with tempfile.TemporaryDirectory() as directory, model_api() as (base, _):
            root = Path(directory)
            assets = self.assets(root)
            args = parser().parse_args(
                [
                    "chat",
                    "--endpoint",
                    base,
                    "--model",
                    "test-model",
                    "--run",
                    "hostname",
                    "--client-dir",
                    str(assets),
                    "--state-dir",
                    str(root / "state"),
                    "--project",
                    str(root),
                ]
            )
            with (
                patch("local_ai.client.validate", return_value={"arch": "amd64"}),
                patch("local_ai.client.execute", return_value=0) as execute,
                patch("local_ai.client.subprocess.Popen", side_effect=AssertionError("no SSH")),
                contextlib.redirect_stderr(io.StringIO()),
            ):
                self.assertEqual(client.chat(args), 0)
            command, project, env, logfile, prompt = execute.call_args.args
            self.assertEqual(project, root)
            self.assertEqual(command[0], str(assets / "bin/opencode"))
            self.assertEqual(prompt, "hostname")
            config = json.loads(env["OPENCODE_CONFIG_CONTENT"])
            self.assertEqual(config["provider"]["local-deepseek"]["options"]["baseURL"], base)
            invocation = json.loads((logfile.parent / "invocation.json").read_text())
            self.assertEqual(invocation["endpoint"], base)
            self.assertNotIn("ssh_command", invocation)

    def test_switch_endpoints_keeps_saved_defaults_and_separate_state(self):
        with (
            tempfile.TemporaryDirectory() as directory,
            model_api("model-a") as (base_a, requests_a),
            model_api("model-b") as (base_b, requests_b),
        ):
            root = Path(directory)
            assets = self.assets(root)
            settings_path = root / "installation.json"
            original = json.dumps({"endpoint": base_a, "model": "model-a"})
            settings_path.write_text(original)
            common = [
                "--client-dir",
                str(assets),
                "--state-dir",
                str(root / "state"),
                "--project",
                str(root),
            ]
            output = io.StringIO()
            with (
                patch.dict(os.environ, {"LOCAL_AI_ROOT": str(root)}),
                patch("local_ai.client.validate", return_value={"arch": "amd64"}),
                patch("local_ai.client.register") as register,
                patch("local_ai.client.execute", return_value=0) as execute,
                contextlib.redirect_stderr(io.StringIO()),
                contextlib.redirect_stdout(output),
            ):
                for extra in ([], ["--endpoint", base_b, "--model", "model-b"], []):
                    self.assertEqual(main(["chat", *common, "--run", "hostname", *extra]), 0)
                self.assertEqual(
                    main(["chat", *common, "--endpoint", base_b, "--model", "model-b", "--check"]),
                    0,
                )
                errors = io.StringIO()
                with contextlib.redirect_stderr(errors):
                    self.assertEqual(main(["chat", *common, "--endpoint", base_b, "--check"]), 1)
                self.assertIn("available models: model-b", errors.getvalue())
                self.assertIn("chat --model ID", errors.getvalue())
            first, switched, returned = execute.call_args_list
            environments = [call.args[2] for call in (first, switched, returned)]
            for env, base, model in zip(
                environments, (base_a, base_b, base_a), ("model-a", "model-b", "model-a")
            ):
                cfg = json.loads(env["OPENCODE_CONFIG_CONTENT"])
                self.assertEqual(cfg["provider"]["local-deepseek"]["options"]["baseURL"], base)
                self.assertEqual(cfg["model"], "local-deepseek/" + model)
            for variable in ("XDG_DATA_HOME", "XDG_STATE_HOME", "XDG_CACHE_HOME"):
                self.assertEqual(environments[0][variable], environments[2][variable])
                self.assertNotEqual(environments[0][variable], environments[1][variable])
            self.assertEqual(len(list((root / "state/services").iterdir())), 2)
            self.assertEqual(settings_path.read_text(), original)
            result = json.loads(output.getvalue())
            self.assertEqual((result["endpoint"], result["model"]), (base_b, "model-b"))
            self.assertEqual(
                [call.args[3] for call in register.call_args_list], [base_a, base_b, base_a, base_b]
            )
            self.assertEqual(requests_a, ["/v1/models"] * 2)
            self.assertEqual(requests_b, ["/v1/models"] * 3)

    def test_invalid_endpoint_rejected_before_writes(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "absent"
            args = parser().parse_args(
                [
                    "chat",
                    "--endpoint",
                    "http://0.0.0.0:18000/v1",
                    "--state-dir",
                    str(root),
                    "--check",
                ]
            )
            with self.assertRaisesRegex(ValueError, "wildcard"):
                client.chat(args)
            self.assertFalse(root.exists())
