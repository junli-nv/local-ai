import argparse
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_ai import client, resume
from local_ai.common import atomic_json


class ResumeTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.home = self.root / "home with spaces"
        self.home.mkdir()
        self.state_root = self.home / ".local/state/local-ai"
        self.sessions = {}
        native = patch(
            "local_ai.resume.native_sessions",
            side_effect=lambda state, context: self.sessions.get(str(state), []),
        )
        native.start()
        self.addCleanup(native.stop)
        self.patch = patch("local_ai.resume.client_home", return_value=self.state_root)
        self.patch.start()
        self.addCleanup(self.patch.stop)

    def service(self, key, session_id="ses_example", legacy=False, root=None):
        state = (root or self.state_root) / "services" / key
        (state / "data").mkdir(parents=True)
        project = self.root / ("project " + key)
        project.mkdir(exist_ok=True)
        self.sessions[str(state)] = [{"id": session_id, "directory": str(project)}]
        context = {
            "project": str(project),
            "state": str(state),
            "state_dir": str(state.parent.parent),
            "client_dir": str(self.root / "assets"),
            "endpoint": "http://" + key + ":18000/v1",
            "model": "example-model",
        }
        if legacy:
            log = state / "logs/session-123"
            atomic_json(
                log / "invocation.json",
                {
                    "project": str(project),
                    "endpoint": context["endpoint"],
                    "command": [str(self.root / "assets/bin/opencode")],
                },
            )
            atomic_json(log / "opencode.json", {"model": "local-deepseek/example-model"})
        else:
            atomic_json(state / "connection.json", context)
        return state, context, project

    def test_existing_session_restores_original_project_and_connection(self):
        _, context, project = self.service("gpu-a", legacy=True)
        self.service("gpu-b", "ses_other")
        self.assertEqual(resume.locate("ses_example"), (context, str(project)))
        with patch("local_ai.client.chat", return_value=0) as chat:
            self.assertEqual(resume.main(["-s", "ses_example"]), 0)
        options = chat.call_args.args[0]
        self.assertEqual(options.endpoint, context["endpoint"])
        self.assertEqual(options.project, project)
        self.assertEqual(options.state_dir, self.state_root)
        self.assertEqual(options.session, "ses_example")

    def test_custom_state_root_is_found_via_private_pointer(self):
        state, context, project = self.service("custom", root=self.root / "custom")
        atomic_json(self.state_root / "connections/custom.json", {"state": str(state)})
        self.assertEqual(resume.locate("ses_example"), (context, str(project)))

    def test_missing_or_ambiguous_session_does_not_pick_an_endpoint(self):
        self.service("gpu-a")
        with self.assertRaises(ValueError):
            resume.locate("' OR 1=1 --")
        self.service("gpu-b")
        with self.assertRaises(ValueError):
            resume.locate("ses_example")

    def test_launcher_runs_and_preserves_unrelated_existing_executable(self):
        with patch("local_ai.resume.Path.home", return_value=self.home):
            launcher = resume.install_launcher()
            result = subprocess.run([str(launcher), "--help"], capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn("--session", result.stdout)
            self.assertEqual(launcher.stat().st_mode & 0o777, 0o700)
            launcher.write_text("#!/bin/bash\nexit 42\n")
            self.assertIsNone(resume.install_launcher())
            self.assertEqual(subprocess.run([str(launcher)]).returncode, 42)

    def test_session_and_continue_flags_reach_native_client(self):
        for flags, expected in [
            ({"session": "ses_example"}, ["--session", "ses_example"]),
            ({"continue_session": True}, ["--continue"]),
        ]:
            with self.subTest(flags=flags):
                assets = self.root / "assets"
                (assets / "seed-cache").mkdir(parents=True, exist_ok=True)
                (assets / "manifest.json").write_text("{}")
                options = argparse.Namespace(
                    endpoint="http://gpu-a:18000/v1",
                    client_dir=assets,
                    state_dir=self.root / "client-state",
                    project=self.root,
                    model="model",
                    check=False,
                    run="test prompt",
                    **flags,
                )
                with (
                    patch(
                        "local_ai.client.validate",
                        return_value={"arch": "amd64", "version": "99.0.0"},
                    ),
                    patch("local_ai.client.wait_endpoint"),
                    patch("local_ai.client.register"),
                    patch("local_ai.client.execute", return_value=0) as execute,
                ):
                    self.assertEqual(client.chat(options), 0)
                command, _, env, _, _ = execute.call_args.args
                self.assertEqual(command[-len(expected) :], expected)
                self.assertEqual(env["OPENCODE_DISABLE_MOUSE"], "true")
                self.assertEqual(env["OPENCODE_EXPERIMENTAL_DISABLE_COPY_ON_SELECT"], "true")
                tui = json.loads(Path(env["OPENCODE_TUI_CONFIG"]).read_text())
                self.assertFalse(tui["mouse"])
                self.assertEqual(tui["keybinds"]["messages_copy"], "none")
                self.assertEqual(tui["keybinds"]["input_paste"], "none")
