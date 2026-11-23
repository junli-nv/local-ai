import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_ai import documents
from local_ai.cli import parser


class PdfBackendTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name).resolve()

    def test_optional_setup_uses_private_venv_and_offline_wheels(self):
        wheels = self.root / "wheels"
        wheels.mkdir()
        with (
            patch.dict(os.environ, {"XDG_STATE_HOME": str(self.root)}),
            patch("local_ai.documents.pdf_python", side_effect=[None, "/private/python"]),
            patch("local_ai.documents.run") as run,
        ):
            result = documents.setup_pdf(wheels)
        commands = [call.args[0] for call in run.call_args_list]
        self.assertEqual(commands[0][:3], [sys.executable, "-m", "venv"])
        self.assertEqual(commands[0][3], str(self.root / "local-ai/document-tools/pypdf"))
        self.assertEqual(commands[1][0], commands[0][3] + "/bin/python")
        self.assertIn("--no-index", commands[1])
        self.assertEqual(commands[1][-3:], ["--find-links", str(wheels.resolve()), "pypdf"])
        self.assertEqual(result["status"], "installed")
        self.assertEqual(
            parser().parse_args(["document", "setup-pdf", "--wheel-dir", str(wheels)]).wheel_dir,
            wheels,
        )

    def test_setup_reuses_available_backend_without_install_or_network(self):
        with (
            patch("local_ai.documents.pdf_python", return_value="/existing/python"),
            patch("local_ai.documents.run") as run,
        ):
            self.assertEqual(documents.setup_pdf()["status"], "already-present")
        run.assert_not_called()

    def test_failed_install_is_reported_and_can_be_retried(self):
        with (
            patch.dict(os.environ, {"XDG_STATE_HOME": str(self.root)}),
            patch("local_ai.documents.pdf_python", return_value=None),
            patch("local_ai.documents.run", side_effect=[None, RuntimeError("offline")]),
            self.assertRaisesRegex(RuntimeError, "offline"),
        ):
            documents.setup_pdf()
        with (
            patch.dict(os.environ, {"XDG_STATE_HOME": str(self.root)}),
            patch("local_ai.documents.pdf_python", side_effect=[None, "/ready/python"]),
            patch("local_ai.documents.run"),
        ):
            self.assertEqual(documents.setup_pdf()["status"], "installed")

    def test_auto_uses_external_pypdf_and_warns_when_rendering_is_missing(self):
        pdf = self.root / "manual.pdf"
        pdf.write_bytes(b"%PDF-1.4")

        def extract(command, **kwargs):
            self.assertEqual(command[:3], ["/private/python", "-I", "-c"])
            self.assertEqual(command[-2:], ["2", "2"])
            Path(command[-3]).write_text("BCM page two\fBCM page three\f")
            return subprocess.CompletedProcess(command, 0, b"", b"")

        with (
            patch("local_ai.documents.shutil.which", return_value=None),
            patch("local_ai.documents.pdf_python", return_value="/private/python"),
            patch("local_ai.documents.subprocess.run", side_effect=extract),
        ):
            result = documents.read_document(pdf, start=2, count=2)
        text = result["content"][0]["text"]
        meta = json.loads(text.split("\n", 1)[0])
        self.assertEqual(meta["image_count"], 0)
        self.assertIn("Page 2\nBCM page two", text)
        self.assertIn("Page 3\nBCM page three", text)
        self.assertTrue(any("not inspected" in w for w in meta["warnings"]))

    def test_read_never_installs_packages_and_explicit_render_still_requires_poppler(self):
        pdf = self.root / "manual.pdf"
        pdf.write_bytes(b"%PDF-1.4")
        with (
            patch("local_ai.documents.shutil.which", return_value=None),
            patch("local_ai.documents.pdf_python", return_value=None),
            patch("local_ai.documents.setup_pdf") as setup,
        ):
            with self.assertRaisesRegex(ValueError, "setup-pdf"):
                documents.read_document(pdf)
            with self.assertRaisesRegex(ValueError, "pdftoppm"):
                documents.read_document(pdf, mode="render")
        setup.assert_not_called()
