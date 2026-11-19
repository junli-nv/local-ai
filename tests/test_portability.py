import json
import sqlite3
import tempfile
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from local_ai import diagnostics, history
from local_ai import portability as p
from local_ai.common import atomic_json


class PortabilityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = self.root / "source"
        self.key = "a" * 20
        self.state = self.source / "services" / self.key
        (self.state / "data/opencode").mkdir(parents=True)
        self.database = self.state / "data/opencode/opencode.db"
        with sqlite3.connect(self.database) as db:
            db.execute("create table session(id text, body text)")
            db.execute("insert into session values('ses_one','private conversation')")
        atomic_json(
            self.state / "connection.json",
            {
                "client_dir": str(self.root / "client"),
                "project": str(self.root),
                "endpoint": "http://old:18000/v1",
                "model": "model",
                "state": str(self.state),
            },
        )
        atomic_json(
            self.source / "history-bindings.json",
            {"version": 1, "defaults": {}, "endpoints": {}, "active": self.key},
        )
        (self.state / "data/opencode/auth.json").write_text("SECRET_CREDENTIAL")
        self.archive = self.root / "private.zip"
        self.mock = patch.object(p, "validate", return_value={"version": "1.19.5"})
        self.mock.start()
        self.addCleanup(self.mock.stop)

    def test_online_snapshot_restores_independently_and_reuses_archive(self):
        before = self.database.read_bytes()
        result = p.backup(self.source, self.archive)
        self.assertEqual(self.archive.stat().st_mode & 0o777, 0o600)
        self.assertFalse(result["auth_files_included"])
        with zipfile.ZipFile(self.archive) as z:
            self.assertFalse(any("auth" in n for n in z.namelist()))
        target = self.root / "target"
        restored = p.restore(target, self.archive, self.root / "client", "http://new:18000/v1")
        key = restored["histories"][0]["history_id"]
        database = target / "services" / key / "data/opencode/opencode.db"
        with sqlite3.connect(database) as db:
            self.assertEqual(
                db.execute("select * from session").fetchall(),
                [("ses_one", "private conversation")],
            )
        self.assertEqual(
            p.restore(target, self.archive, self.root / "client", "http://new:18000/v1")["reused"],
            True,
        )
        self.assertEqual(history.load(target)["active"], key)
        self.assertEqual(self.database.read_bytes(), before)

    def test_restore_preserves_existing_selection_until_explicit_select(self):
        p.backup(self.source, self.archive)
        existing = self.root / "existing"
        keep = "b" * 20
        folder = existing / "services" / keep / "data/opencode"
        folder.mkdir(parents=True)
        with sqlite3.connect(folder / "opencode.db") as db:
            db.execute("create table session(id text)")
            db.execute("insert into session values('ses_existing')")
        atomic_json(
            existing / "history-bindings.json",
            {"version": 1, "defaults": {}, "endpoints": {}, "active": keep},
        )
        restored = p.restore(existing, self.archive, self.root / "client", "http://new/v1")
        self.assertEqual(history.load(existing)["active"], keep)
        imported = restored["histories"][0]["history_id"]
        p.select(existing, imported)
        self.assertEqual(history.load(existing)["active"], imported)
        with self.assertRaises(ValueError):
            p.select(existing, "../outside")

    def test_rejects_version_mismatch_extra_entries_corruption_and_overwrite(self):
        p.backup(self.source, self.archive)
        with self.assertRaises(ValueError):
            p.backup(self.source, self.archive)
        with patch.object(p, "validate", return_value={"version": "different"}):
            with self.assertRaisesRegex(ValueError, "same native"):
                p.restore(self.root / "target", self.archive, self.root / "client", "http://new/v1")
        bad = self.root / "bad.zip"
        with zipfile.ZipFile(self.archive) as src, zipfile.ZipFile(bad, "w") as dst:
            for name in src.namelist():
                dst.writestr(name, src.read(name))
            dst.writestr("../outside", "bad")
        with self.assertRaisesRegex(ValueError, "Unexpected archive"):
            p.restore(self.root / "target", bad, self.root / "client", "http://new/v1")
        self.assertFalse((self.root / "outside").exists())

    def test_doctor_is_read_only_and_excludes_transcript_content(self):
        with patch.object(diagnostics, "validate", return_value={"version": "1.19.5"}):
            before = {
                str(f.relative_to(self.source)): f.stat().st_mtime_ns
                for f in self.source.rglob("*")
                if f.is_file()
            }
            report = diagnostics.inspect(self.source, self.root / "client")
            after = {
                str(f.relative_to(self.source)): f.stat().st_mtime_ns
                for f in self.source.rglob("*")
                if f.is_file()
            }
            self.assertEqual(before, after)
            self.assertTrue(report["read_only"])
            self.assertNotIn("private conversation", json.dumps(report))
            self.assertNotIn("SECRET_CREDENTIAL", json.dumps(report))
            missing = self.root / "absent"
            diagnostics.inspect(missing, self.root / "client")
            self.assertFalse(missing.exists())
