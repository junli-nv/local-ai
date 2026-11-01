import contextlib
import io
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_ai.cli import main, parser


class ConfigurationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "uninstalled"
        self.file = self.root / "installation.json"
        environment = patch.dict(os.environ, {"LOCAL_AI_ROOT": str(self.root)})
        environment.start()
        self.addCleanup(environment.stop)
        for target in (
            "urllib.request.urlopen",
            "subprocess.run",
            "subprocess.call",
            "subprocess.Popen",
            "local_ai.deployment.install",
            "local_ai.artifacts.install",
        ):
            guard = patch(
                target, side_effect=AssertionError("Configuration must not install/connect")
            )
            guard.start()
            self.addCleanup(guard.stop)

    def invoke(self, *arguments):
        output, error = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(error):
            code = main(list(arguments))
        return code, output.getvalue(), error.getvalue()

    def write(self, value):
        self.root.mkdir(exist_ok=True)
        self.file.write_text(json.dumps(value))

    def test_show_is_read_only_before_installation(self):
        code, output, error = self.invoke("config", "show")
        self.assertEqual(code, 0, error)
        self.assertEqual(
            json.loads(output), {"file": str(self.file), "endpoint": None, "model": None}
        )
        self.assertFalse(self.root.exists())

    def test_set_unset_preserve_installation_metadata_without_installing(self):
        metadata = {
            "role": "both",
            "profiles": ["b300-tp4"],
            "bundle_sha256": "receipt",
            "custom": {"preserve": True},
        }
        self.write(metadata)
        for key, value in (("endpoint", "http://GPU002:18000/v1/"), ("model", "other-model")):
            code, _, error = self.invoke("config", "set", key, value)
            self.assertEqual(code, 0, error)
        self.assertEqual(parser().parse_args(["chat"]).endpoint, "http://GPU002:18000/v1")
        self.assertEqual(parser().parse_args(["chat"]).model, "other-model")
        record = json.loads(self.file.read_text())
        for key, value in metadata.items():
            self.assertEqual(record[key], value)
        self.assertEqual(self.file.stat().st_mode & 0o777, 0o644)
        code, _, error = self.invoke("config", "unset", "endpoint")
        self.assertEqual(code, 0, error)
        self.assertIsNone(parser().parse_args(["chat"]).endpoint)
        code, _, error = self.invoke("chat", "--check")
        self.assertEqual(code, 1)
        self.assertIn("config set endpoint", error)
        self.assertEqual(self.invoke("config", "unset", "model")[0], 0)
        self.assertEqual(json.loads(self.file.read_text()), metadata)
        self.assertFalse((self.root / "install.log").exists())
        self.assertFalse((self.root / "clients").exists())

    def test_invalid_values_do_not_change_existing_settings(self):
        self.write({"endpoint": "http://GPU001:18000/v1", "role": "client"})
        original = self.file.read_bytes()
        for key, value in (("endpoint", "http://0.0.0.0:18000/v1"), ("model", " ")):
            code, _, _ = self.invoke("config", "set", key, value)
            self.assertEqual(code, 1)
            self.assertEqual(self.file.read_bytes(), original)

    def test_manual_edit_is_read_on_the_next_invocation(self):
        self.write({"endpoint": "http://GPU001:18000/v1", "model": "first"})
        self.assertEqual(parser().parse_args(["chat"]).model, "first")
        self.write({"endpoint": "http://GPU002:18000/v1", "model": "second"})
        code, output, error = self.invoke("config", "show")
        self.assertEqual(code, 0, error)
        self.assertEqual(json.loads(output)["endpoint"], "http://GPU002:18000/v1")
        self.assertEqual(parser().parse_args(["chat"]).model, "second")

    def test_invalid_settings_report_filename_without_overwriting(self):
        self.root.mkdir()
        for content in (
            "{broken",
            "[]",
            '{"installation": []}',
            '{"endpoint": 42}',
            '{"model": []}',
        ):
            self.file.write_text(content)
            code, _, error = self.invoke("config", "set", "endpoint", "http://GPU002:18000/v1")
            self.assertEqual(code, 1)
            self.assertIn(str(self.file), error)
            self.assertNotIn("Traceback", error)
            self.assertEqual(self.file.read_text(), content)

    def test_bundle_metadata_kept_without_forging_verification_receipt(self):
        self.root.mkdir()
        (self.root / "bundle.json").write_text(
            json.dumps({"format": 1, "installation": {"role": "client", "model": "bundled"}})
        )
        code, _, error = self.invoke("config", "set", "endpoint", "http://GPU002:18000/v1")
        self.assertEqual(code, 0, error)
        value = json.loads(self.file.read_text())
        self.assertEqual(value["model"], "bundled")
        self.assertNotIn("bundle_sha256", value)
