import argparse
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_ai import history
from local_ai.common import atomic_json


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "private state"
        self.root.mkdir()
        self.old = "http://old:18000/v1"
        self.new = "http://new:18000/v1"
        self.next = "http://next:18000/v1"
        self.profile = patch("local_ai.history.installation_key", return_value="a" * 20)
        self.profile.start()
        self.addCleanup(self.profile.stop)
        self.source = self.state(self.old, ["ses_keep"])
        self.target = self.state(self.new, [])
        self.options = argparse.Namespace(
            state_dir=self.root,
            old_endpoint=self.old,
            endpoint=self.new,
            default_endpoint=self.new,
            model=None,
            dry_run=False,
        )

    def state(self, endpoint, sessions):
        path = self.root / "services" / history.endpoint_key(endpoint)
        db = path / "data/opencode/opencode.db"
        db.parent.mkdir(parents=True)
        with sqlite3.connect(db) as connection:
            connection.execute("create table session(id text primary key)")
            connection.executemany("insert into session values(?)", [(v,) for v in sessions])
        atomic_json(
            path / "connection.json",
            dict(
                endpoint=endpoint,
                model="example-model",
                project=str(self.root),
                state=str(path),
                state_dir=str(self.root),
                client_dir=str(self.root / "assets"),
            ),
        )
        return path

    def test_update_endpoint_preserves_database_bytes_and_inode(self):
        files = [p / "data/opencode/opencode.db" for p in (self.source, self.target)]
        before = [(p.read_bytes(), p.stat().st_ino) for p in files]
        result = history.update_endpoint(self.options)
        self.assertEqual(result["sessions"], 1)
        self.assertFalse(result["database_copied"])
        self.assertEqual(before, [(p.read_bytes(), p.stat().st_ino) for p in files])
        self.assertEqual(history.resolve(self.root, self.new, self.new), self.source.name)
        self.assertEqual(
            json.loads((self.source / "connection.json").read_text())["endpoint"], self.new
        )
        backup = Path(result["backup_directory"])
        self.assertEqual(backup.stat().st_mode & 0o777, 0o700)
        self.assertEqual(history.binding_path(self.root).stat().st_mode & 0o777, 0o600)

    def test_empty_target_only_and_dry_run_is_read_only(self):
        self.options.dry_run = True
        before = {str(p.relative_to(self.root)) for p in self.root.rglob("*")}
        self.assertTrue(history.update_endpoint(self.options)["dry_run"])
        self.assertEqual(before, {str(p.relative_to(self.root)) for p in self.root.rglob("*")})
        self.options.dry_run = False
        with sqlite3.connect(self.target / "data/opencode/opencode.db") as c:
            c.execute("insert into session values('ses_new')")
        with self.assertRaises(ValueError):
            history.update_endpoint(self.options)
        self.assertFalse(history.binding_path(self.root).exists())

    def test_saved_and_ad_hoc_endpoints_share_the_selected_history(self):
        history.update_endpoint(self.options)
        self.assertEqual(history.resolve(self.root, self.next, self.next), self.source.name)
        self.assertEqual(history.resolve(self.root, self.next, self.new), self.source.name)
        context = json.loads((self.source / "connection.json").read_text())
        self.assertEqual(
            history.current_context(context, {"endpoint": self.next})["endpoint"], self.next
        )

    def test_update_endpoint_is_idempotent(self):
        history.update_endpoint(self.options)
        self.assertFalse(history.update_endpoint(self.options)["changed"])

    def test_server_switch_does_not_overwrite_another_legacy_database(self):
        history.update_endpoint(self.options)
        separate = self.state(self.next, ["ses_separate"])
        db = separate / "data/opencode/opencode.db"
        before = db.read_bytes()
        self.assertEqual(history.resolve(self.root, self.next, self.next), self.source.name)
        history.remember_history(self.root, self.next, self.source.name, self.new)
        self.assertEqual(db.read_bytes(), before)
        rows = history.list_histories(self.root, self.new)
        legacy = next(r for r in rows if r["history_id"] == separate.name)
        self.assertEqual(legacy["sessions"], 1)
        self.assertFalse(legacy["default"])

    def test_moving_installation_does_not_change_user_history(self):
        history.update_endpoint(self.options)
        with patch("local_ai.history.installation_key", return_value="b" * 20):
            self.assertEqual(history.resolve(self.root, self.next, self.next), self.source.name)

    def test_metadata_write_failure_rolls_back(self):
        original = (self.source / "connection.json").read_bytes()
        real = history.atomic_json
        failed = False

        def write(path, value):
            nonlocal failed
            if Path(path) == history.binding_path(self.root) and not failed:
                failed = True
                raise OSError("simulated write failure")
            real(path, value)

        with patch("local_ai.history.atomic_json", side_effect=write), self.assertRaises(OSError):
            history.update_endpoint(self.options)
        self.assertFalse(history.binding_path(self.root).exists())
        self.assertEqual(
            json.loads(original), json.loads((self.source / "connection.json").read_text())
        )

    def test_invalid_binding_cannot_escape_state_root(self):
        atomic_json(
            history.binding_path(self.root),
            {"version": 1, "defaults": {}, "endpoints": {self.new: "../../other"}},
        )
        with self.assertRaises(ValueError):
            history.resolve(self.root, self.new)

    def test_default_remembered_once_then_tracks_replacement(self):
        history.remember_history(self.root, self.old, self.source.name, self.old)
        self.assertEqual(history.resolve(self.root, self.new, self.new), self.source.name)
        history.remember_history(self.root, self.new, self.source.name, self.new)
        self.assertEqual(history.resolve(self.root, self.old, self.new), self.source.name)

    def test_chat_uses_replacement_api_and_original_history(self):
        from local_ai import client

        history.update_endpoint(self.options)
        assets = self.root / "assets"
        (assets / "seed-cache").mkdir(parents=True)
        (assets / "manifest.json").write_text("{}")
        options = argparse.Namespace(
            endpoint=self.next,
            model="example-model",
            state_dir=self.root,
            client_dir=assets,
            project=self.root,
            run="example task",
            check=False,
            session="ses_keep",
            direct_api=True,
        )
        with (
            patch("local_ai.client.settings", return_value={"endpoint": self.new}),
            patch("local_ai.client.validate", return_value={"arch": "amd64"}),
            patch("local_ai.client.wait_endpoint") as ready,
            patch("local_ai.client.register"),
            patch("local_ai.client.execute", return_value=0) as execute,
            patch("sys.stderr", new_callable=io.StringIO),
        ):
            self.assertEqual(client.chat(options), 0)
        ready.assert_called_once_with(self.next, "example-model")
        command, project, env, log, prompt = execute.call_args.args
        self.assertEqual(env["XDG_DATA_HOME"], str(self.source / "data"))
        self.assertEqual(
            json.loads(env["OPENCODE_CONFIG_CONTENT"])["provider"]["local-deepseek"]["options"][
                "baseURL"
            ],
            self.next,
        )
        self.assertEqual(command[-2:], ["--session", "ses_keep"])
        self.assertEqual(history.session_count(self.source), 1)

    def test_resume_uses_current_default_with_original_session_and_project(self):
        from local_ai import resume

        history.update_endpoint(self.options)
        context = json.loads((self.source / "connection.json").read_text())
        with (
            patch("local_ai.resume.locate", return_value=(context, str(self.root))),
            patch("local_ai.paths.settings", return_value={"endpoint": self.next}),
            patch("local_ai.client.chat", return_value=0) as chat,
        ):
            self.assertEqual(resume.main(["-s", "ses_keep"]), 0)
        options = chat.call_args.args[0]
        self.assertEqual(options.endpoint, self.next)
        self.assertEqual(options.session, "ses_keep")
        self.assertEqual(options.project, self.root)

    def test_history_cli_updates_connections_without_changing_defaults(self):
        from local_ai import cli

        saved = {"endpoint": self.new, "model": "example-model"}
        with patch("local_ai.cli.settings", return_value=saved):
            options = cli.parser().parse_args(
                [
                    "client",
                    "history",
                    "update-endpoint",
                    "--old",
                    self.old,
                    "--new",
                    self.new,
                    "--state-dir",
                    str(self.root),
                    "--dry-run",
                ]
            )
            with patch("sys.stdout", new_callable=io.StringIO) as output:
                self.assertEqual(cli.dispatch(options), 0)
        result = json.loads(output.getvalue())
        self.assertEqual(result["old_endpoint"], self.old)
        self.assertEqual(result["endpoint"], self.new)
        self.assertTrue(result["dry_run"])
        self.assertEqual(saved, {"endpoint": self.new, "model": "example-model"})
        self.assertFalse(history.binding_path(self.root).exists())

    def test_list_discovers_old_endpoint_and_counts_without_writes(self):
        before = {
            str(p.relative_to(self.root)): p.read_bytes()
            for p in self.root.rglob("*")
            if p.is_file()
        }
        rows = history.list_histories(self.root, self.new)
        old = next(r for r in rows if r["history_id"] == self.source.name)
        self.assertEqual(old["endpoints"], [self.old])
        self.assertEqual(old["sessions"], 1)
        self.assertFalse(old["default"])
        self.assertEqual(
            before,
            {
                str(p.relative_to(self.root)): p.read_bytes()
                for p in self.root.rglob("*")
                if p.is_file()
            },
        )

    def test_list_after_update_retains_old_and_new_addresses(self):
        history.update_endpoint(self.options)
        rows = history.list_histories(self.root, self.new)
        current = next(r for r in rows if r["default"])
        self.assertEqual(current["history_directory"], str(self.source))
        self.assertEqual(set(current["endpoints"]), {self.old, self.new})
        self.assertEqual(current["sessions"], 1)

    def test_list_missing_root_does_not_create_state(self):
        missing = self.root / "absent"
        self.assertEqual(history.list_histories(missing, self.new), [])
        self.assertFalse(missing.exists())

    def test_list_reports_unknown_database_instead_of_zero_sessions(self):
        with sqlite3.connect(self.target / "data/opencode/opencode.db") as c:
            c.execute("drop table session")
        rows = history.list_histories(self.root, self.new)
        target = next(r for r in rows if r["history_id"] == self.target.name)
        self.assertIsNone(target["sessions"])
        self.assertTrue(target["error"])
        self.assertEqual(len(rows), 2)

    def test_history_list_cli_table_and_json(self):
        from local_ai import cli

        for extra in ([], ["--json"]):
            with patch("local_ai.cli.settings", return_value={"endpoint": self.new}):
                options = cli.parser().parse_args(
                    ["client", "history", "list", "--state-dir", str(self.root), *extra]
                )
                with patch("sys.stdout", new_callable=io.StringIO) as output:
                    self.assertEqual(cli.dispatch(options), 0)
            if extra:
                self.assertEqual(len(json.loads(output.getvalue())), 2)
            else:
                self.assertIn(self.old, output.getvalue())
                self.assertIn("SESSIONS", output.getvalue())

    def test_fresh_history_identity_does_not_depend_on_any_address(self):
        empty = self.root / "fresh"
        a = history.resolve(empty, self.old)
        b = history.resolve(empty, self.new)
        self.assertEqual(a, b)
        self.assertFalse(empty.exists())

    def test_state_roots_preserve_user_isolation(self):
        history.update_endpoint(self.options)
        other = self.root / "another-user"
        key = history.resolve(other, self.next)
        self.assertNotEqual(other / "services" / key, self.source)
        self.assertFalse(other.exists())

    def test_every_route_is_remembered_without_reassigning_legacy_addresses(self):
        history.update_endpoint(self.options)
        history.remember_history(self.root, self.next, self.source.name, self.new)
        rows = history.list_histories(self.root, self.new)
        selected = next(r for r in rows if r["default"])
        self.assertEqual(set(selected["endpoints"]), {self.old, self.new, self.next})
        self.assertEqual(history.load(self.root)["endpoints"][self.old], self.source.name)

    def test_legacy_pinned_identity_is_understood_without_database_migration(self):
        atomic_json(
            history.binding_path(self.root),
            {
                "version": 1,
                "defaults": {"a" * 20: self.source.name},
                "endpoints": {},
            },
        )
        self.assertEqual(history.resolve(self.root, self.next), self.source.name)
        history.remember_history(self.root, self.next, self.source.name)
        self.assertEqual(history.load(self.root)["active"], self.source.name)
        self.assertEqual(history.session_count(self.source), 1)

    def test_selected_history_requires_explicit_current_route_for_resume(self):
        history.update_endpoint(self.options)
        context = json.loads((self.source / "connection.json").read_text())
        with self.assertRaisesRegex(ValueError, "Set the current endpoint"):
            history.current_context(context, {})

    def test_invalid_active_history_cannot_escape_state_root(self):
        atomic_json(
            history.binding_path(self.root),
            {
                "version": 1,
                "defaults": {},
                "endpoints": {},
                "active": "../../escape",
            },
        )
        with self.assertRaises(ValueError):
            history.resolve(self.root, self.new)
