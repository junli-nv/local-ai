import io
import json
import os
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from local_ai.cli import main, parser
from local_ai.completion import bash_script, candidates
from local_ai.profiles import catalog


class CompletionTests(unittest.TestCase):
    def complete(self, *words):
        return candidates(parser(), words)

    def test_context_and_choices(self):
        self.assertIn("server", self.complete("")[1])
        self.assertEqual(self.complete("server", "sta"), ("values", ["start", "status"]))
        self.assertEqual(
            self.complete("--debug", "server", "start", "--wa")[1],
            ["--wait-timeout", "--warmup", "--warmup-timeout"],
        )
        self.assertEqual(self.complete("install", "--role", "cl"), ("values", ["client"]))
        self.assertEqual(self.complete("config", "set", "en"), ("values", ["endpoint"]))
        self.assertEqual(self.complete("document", "read", "a.pdf", "--mode", "r")[1], ["render"])
        self.assertEqual(self.complete("completion", ""), ("values", ["bash"]))
        self.assertIn("--project", self.complete("chat", "")[1])

    def test_external_catalog_choices_are_live(self):
        data = catalog()
        data["profiles"]["custom-tp4"] = dict(data["profiles"]["b300-tp4"])
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "catalog.json"
            path.write_text(json.dumps(data))
            with patch.dict(os.environ, {"LOCAL_AI_CATALOG": str(path)}):
                for command in [("install",), ("server", "start"), ("export",)]:
                    self.assertEqual(
                        self.complete(*command, "--profile", "custom"), ("values", ["custom-tp4"])
                    )
                self.assertEqual(
                    self.complete("export", "--profile", "b300-tp4", "--profile", "custom")[1],
                    ["custom-tp4"],
                )

    def test_values_do_not_become_commands_and_paths_are_explicit(self):
        self.assertEqual(self.complete("chat", "--run", "server", "--ch")[1], ["--check"])
        self.assertEqual(self.complete("chat", "--endpoint", ""), ("values", []))
        self.assertEqual(self.complete("server", "start", "--gpus", ""), ("values", []))
        self.assertEqual(self.complete("chat", "--project", ""), ("files", []))
        self.assertEqual(self.complete("document", "read", ""), ("files", []))
        self.assertEqual(self.complete("document", "read", "--", "-"), ("files", []))
        self.assertEqual(self.complete("unknown", ""), ("values", []))

    def test_equals_and_global_option_values(self):
        self.assertEqual(self.complete("install", "--role=cl"), ("values", ["--role=client"]))
        self.assertEqual(self.complete("install", "--role", "=", "cl"), ("values", ["client"]))
        self.assertIn("start", self.complete("--install-log", "server", "server", "")[1])
        self.assertIn("--port", self.complete("server", "start", "--gpus=0,1", "--")[1])
        self.assertEqual(
            self.complete("install", "--role", "=", "server", "--profile=b300-tp4-d"),
            ("values", ["--profile=b300-tp4-dspark"]),
        )

    def test_completion_bypasses_dispatch_and_logging(self):
        with (
            patch("local_ai.cli.dispatch", side_effect=AssertionError("dispatch")),
            patch("local_ai.installlog.session", side_effect=AssertionError("logging")),
            patch("subprocess.run", side_effect=AssertionError("subprocess")),
            redirect_stdout(io.StringIO()) as output,
        ):
            self.assertEqual(main(["completion", "bash"]), 0)
            self.assertIn("complete -o filenames", output.getvalue())
            self.assertEqual(main(["--_complete", "server", "sta"]), 0)
            self.assertTrue(output.getvalue().endswith("values\nstart\nstatus\n"))

    def test_bash_32_wrapper_preserves_paths_with_spaces(self):
        root = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, "a file.txt").touch()
            script = (
                bash_script(root / "local-ai")
                + r"""
COMP_WORDS=("$LA_TEST_LAUNCHER" server sta)
COMP_CWORD=2
_local_ai_complete
printf '%s\n' "${COMPREPLY[@]}"
COMP_WORDS=("$LA_TEST_LAUNCHER" document read a)
COMP_CWORD=3
_local_ai_complete
printf '%s\n' "${COMPREPLY[@]}"
COMP_WORDS=("$LA_TEST_LAUNCHER" install --role = cl)
COMP_CWORD=4
_local_ai_complete
printf '%s\n' "${COMPREPLY[@]}"
"""
            )
            result = subprocess.run(
                ["/bin/bash", "--noprofile", "--norc"],
                input=script,
                cwd=directory,
                env={**os.environ, "LA_TEST_LAUNCHER": str(root / "local-ai")},
                text=True,
                capture_output=True,
                check=True,
            )
            self.assertEqual(
                result.stdout.splitlines(), ["start", "status", "a file.txt", "client"]
            )
            self.assertEqual(result.stderr, "")
