import contextlib
import importlib.util
import io
import json
import os
import subprocess
import sys
import tarfile
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

spec = importlib.util.spec_from_file_location(
    "program_updater", Path(__file__).parents[1] / "scripts/update.py"
)
updater = importlib.util.module_from_spec(spec)
spec.loader.exec_module(updater)


class UpdateTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.root = self.work / "installed"
        (self.root / "src/local_ai").mkdir(parents=True)
        (self.root / "local-ai").write_text("old launcher")
        (self.root / "src/local_ai/__init__.py").write_text('__version__ = "1.1.0"\n')
        (self.root / "src/local_ai/removed.py").write_text("old module")
        self.settings = {
            "version": "1.1.0",
            "role": "client",
            "endpoint": "http://GPU001:18000/v1",
            "model": "example",
            "default_profile": "example",
            "bundle_sha256": "old-hash",
        }
        (self.root / "installation.json").write_text(json.dumps(self.settings))
        (self.root / "installation.json").chmod(0o644)
        (self.root / "bundle.json").write_text("old bundle")
        self.assets = {}
        for directory in ("models", "images", "clients", "instances", "dist", "config"):
            path = self.root / directory / "keep"
            path.parent.mkdir()
            path.write_bytes((directory + " untouched").encode())
            self.assets[path] = (path.read_bytes(), path.stat().st_ino)
        self.archive = self.work / "source.tar.gz"
        self.make_archive()

    def make_archive(self, additions=()):
        files = {
            "package/local-ai": b"new launcher",
            "package/src/local_ai/__init__.py": b'__version__ = "1.2.0"\n',
            "package/src/local_ai/cli.py": b"new cli",
            "package/src/local_ai/profiles.json": b"{}",
            "package/docs/update.md": b"new documentation",
            "package/templates/opencode/AGENTS.general.md": b"new rules template",
        }
        with tarfile.open(self.archive, "w:gz") as archive:
            for name, value in files.items():
                member = tarfile.TarInfo(name)
                member.size, member.mode = len(value), 0o755 if name.endswith("local-ai") else 0o644
                archive.addfile(member, io.BytesIO(value))
            for member in additions:
                archive.addfile(member)

    def args(self, *extra):
        return updater.parser().parse_args(
            ["--root", str(self.root), "--archive", str(self.archive), *extra]
        )

    def assert_assets_untouched(self):
        for path, (content, inode) in self.assets.items():
            self.assertEqual(path.read_bytes(), content)
            self.assertEqual(path.stat().st_ino, inode)

    def update(self):
        with (
            patch("urllib.request.urlopen", side_effect=AssertionError("no network")),
            patch("subprocess.Popen", side_effect=AssertionError("no resource commands")),
        ):
            return updater.execute(self.args())

    def test_offline_program_update_preserves_resources_settings_and_permissions(self):
        result = self.update()
        self.assertEqual(result["version"], "1.2.0")
        self.assertFalse(result["resources_changed"])
        self.assertFalse(result["service_restarted"])
        self.assert_assets_untouched()
        settings = json.loads((self.root / "installation.json").read_text())
        expected = {**self.settings, "version": "1.2.0"}
        expected.pop("bundle_sha256")
        self.assertEqual(settings, expected)
        self.assertEqual((self.root / "installation.json").stat().st_mode & 0o777, 0o644)
        self.assertFalse((self.root / "bundle.json").exists())
        self.assertFalse((self.root / "src/local_ai/removed.py").exists())
        self.assertTrue((self.root / "scripts/update.py").is_file())
        self.assertEqual(
            (self.root / "templates/opencode/AGENTS.general.md").read_bytes(), b"new rules template"
        )
        backup = Path(result["backup"])
        self.assertTrue((backup / "program/src/local_ai/removed.py").is_file())
        self.assertEqual((backup / "metadata/bundle.json").read_text(), "old bundle")
        self.assertNotIn("models", {p.name for p in (backup / "program").iterdir()})

    def test_explicit_rollback_restores_old_program_and_metadata(self):
        result = self.update()
        args = updater.parser().parse_args(
            ["--root", str(self.root), "--rollback", result["backup"]]
        )
        rolled = updater.execute(args)
        self.assertEqual(rolled["version"], "1.1.0")
        self.assertEqual(updater.version(self.root), "1.1.0")
        self.assertEqual(json.loads((self.root / "installation.json").read_text()), self.settings)
        self.assertEqual((self.root / "bundle.json").read_text(), "old bundle")
        self.assertFalse((self.root / "docs").exists())
        self.assertFalse((self.root / "templates").exists())
        self.assertTrue((self.root / "src/local_ai/removed.py").exists())
        self.assert_assets_untouched()

    def test_mid_update_failure_restores_previous_program(self):
        with patch.object(updater, "write_settings", side_effect=OSError("disk write failed")):
            with self.assertRaisesRegex(OSError, "disk write failed"):
                self.update()
        self.assertEqual(updater.version(self.root), "1.1.0")
        self.assertEqual((self.root / "local-ai").read_text(), "old launcher")
        self.assertEqual((self.root / "bundle.json").read_text(), "old bundle")
        self.assertFalse((self.root / "scripts/update.py").exists())
        self.assert_assets_untouched()
        backup = next(self.work.glob("local-ai-backup-*"))
        self.assertEqual(
            json.loads((backup / "update.json").read_text())["state"], "failed-restored"
        )

    def test_bad_checksum_changes_no_program_files(self):
        with self.assertRaisesRegex(ValueError, "SHA256"):
            updater.execute(self.args("--sha256", "0" * 64))
        self.assertEqual(updater.version(self.root), "1.1.0")
        self.assertFalse(list(self.work.glob("local-ai-backup-*")))
        self.assert_assets_untouched()

    def test_archive_traversal_links_and_resource_bundles_are_rejected(self):
        for name, kind in (
            ("package/../../outside", tarfile.REGTYPE),
            ("/outside", tarfile.REGTYPE),
            ("package/src/link", tarfile.SYMTYPE),
            ("package/models", tarfile.DIRTYPE),
            ("package/installation.json", tarfile.REGTYPE),
            ("other/local-ai", tarfile.REGTYPE),
        ):
            with self.subTest(name=name):
                member = tarfile.TarInfo(name)
                member.type, member.linkname = kind, "/outside"
                self.make_archive([member])
                with self.assertRaises(ValueError):
                    self.update()
                self.assertEqual(updater.version(self.root), "1.1.0")
                self.assertFalse(list(self.work.glob("local-ai-backup-*")))
                self.assert_assets_untouched()

    def test_wrong_root_backup_is_rejected_before_restoring(self):
        result = self.update()
        backup = Path(result["backup"])
        metadata = json.loads((backup / "update.json").read_text())
        metadata["root"] = str(self.work / "another")
        (backup / "update.json").write_text(json.dumps(metadata))
        with self.assertRaisesRegex(ValueError, "another installation"):
            updater.restore(self.root, backup)
        self.assertEqual(updater.version(self.root), "1.2.0")
        self.assert_assets_untouched()

    def test_duplicate_update_is_rejected_before_source_download(self):
        with updater.locked(self.root):
            with self.assertRaisesRegex(RuntimeError, "Another program update"):
                self.update()

    def test_download_uses_explicit_project_tag_and_checks_embedded_version(self):
        args = updater.parser().parse_args(["--root", str(self.root), "--version", "v1.2.0"])
        with patch(
            "urllib.request.urlopen", return_value=io.BytesIO(self.archive.read_bytes())
        ) as request:
            result = updater.execute(args)
        self.assertEqual(result["version"], "1.2.0")
        self.assertEqual(
            request.call_args.args[0],
            "https://github.com/junli-nv/local-ai/archive/refs/tags/v1.2.0.tar.gz",
        )
        self.assert_assets_untouched()

    def test_mismatched_tag_rejected_before_installation(self):
        args = updater.parser().parse_args(["--root", str(self.root), "--version", "v1.9.0"])
        with patch("urllib.request.urlopen", return_value=io.BytesIO(self.archive.read_bytes())):
            with self.assertRaisesRegex(ValueError, "does not match"):
                updater.execute(args)
        self.assertEqual(updater.version(self.root), "1.1.0")
        self.assert_assets_untouched()

    def test_invalid_settings_rejected_before_backup_or_mutation(self):
        (self.root / "installation.json").write_text("[]")
        with self.assertRaisesRegex(ValueError, "must contain an object"):
            self.update()
        self.assertFalse(list(self.work.glob("local-ai-backup-*")))
        self.assertEqual(updater.version(self.root), "1.1.0")
        self.assert_assets_untouched()

    def test_linked_metadata_is_rejected_before_program_replacement(self):
        outside = self.work / "outside.json"
        outside.write_text(json.dumps(self.settings))
        (self.root / "installation.json").unlink()
        (self.root / "installation.json").symlink_to(outside)
        with self.assertRaisesRegex(ValueError, "regular metadata"):
            self.update()
        self.assertEqual(updater.version(self.root), "1.1.0")
        self.assertEqual(json.loads(outside.read_text()), self.settings)
        self.assertFalse(list(self.work.glob("local-ai-backup-*")))
        self.assert_assets_untouched()

    def test_rollback_recovers_when_interrupted_replacement_has_no_launcher_or_src(self):
        result = self.update()
        (self.root / "local-ai").unlink()
        updater.remove(self.root / "src")
        args = updater.parser().parse_args(
            ["--root", str(self.root), "--rollback", result["backup"]]
        )
        recovered = updater.execute(args)
        self.assertEqual(recovered["state"], "rolled-back")
        self.assertEqual(updater.version(self.root), "1.1.0")
        self.assertEqual((self.root / "local-ai").read_text(), "old launcher")
        self.assert_assets_untouched()

    def activity(self):
        return {
            "supported": True,
            "unreadable": 0,
            "processes": [
                {
                    "pid": 4711,
                    "kind": "opencode",
                    "executable": str(self.root / "clients/bin/opencode"),
                    "uid": 1000,
                }
            ],
        }

    def test_check_is_read_only_and_reports_active_without_prompts(self):
        args = ["--root", str(self.root), "--check"]
        with patch.object(updater, "client_activity", return_value=self.activity()):
            with contextlib.redirect_stdout(io.StringIO()) as output:
                self.assertEqual(updater.main(args), 3)
        result = json.loads(output.getvalue())
        self.assertFalse(result["ready"])
        self.assertFalse(result["history_backed_up"])
        self.assertFalse((self.root / ".update.lock").exists())
        self.assertFalse(list(self.work.glob("local-ai-backup-*")))
        self.assert_assets_untouched()

    def test_check_with_no_proc_never_claims_ready(self):
        with patch.object(
            updater,
            "client_activity",
            return_value={"supported": False, "processes": [], "unreadable": 0},
        ):
            result = updater.execute(
                updater.parser().parse_args(["--root", str(self.root), "--check"])
            )
        self.assertIsNone(result["ready"])

    def test_active_client_blocks_before_download_or_program_backup(self):
        args = updater.parser().parse_args(["--root", str(self.root), "--version", "v1.2.0"])
        with patch.object(updater, "client_activity", return_value=self.activity()):
            with patch("urllib.request.urlopen", side_effect=AssertionError("must not download")):
                with self.assertRaisesRegex(RuntimeError, "Active client.*4711"):
                    updater.execute(args)
        self.assertEqual(updater.version(self.root), "1.1.0")
        self.assertFalse(list(self.work.glob("local-ai-backup-*")))
        self.assert_assets_untouched()

    def test_client_starting_during_unpack_blocks_before_replacement(self):
        clear = {"supported": True, "processes": [], "unreadable": 0}
        with patch.object(updater, "client_activity", side_effect=[clear, self.activity()]):
            with self.assertRaisesRegex(RuntimeError, "Active client"):
                self.update()
        self.assertEqual(updater.version(self.root), "1.1.0")
        self.assertFalse(list(self.work.glob("local-ai-backup-*")))
        self.assert_assets_untouched()

    def test_explicit_active_override_never_signals_or_replaces_client(self):
        with patch.object(updater, "client_activity", return_value=self.activity()):
            with patch("os.kill", side_effect=AssertionError("no signals")):
                result = updater.execute(self.args("--allow-active-clients"))
        self.assertFalse(result["native_client_changed"])
        self.assertFalse(result["history_backed_up"])
        self.assertEqual(result["activity_check"]["processes"][0]["pid"], 4711)
        self.assertEqual(result["backup_scope"], "program-and-installation-metadata")
        self.assert_assets_untouched()

    def test_active_client_also_blocks_rollback(self):
        result = self.update()
        args = updater.parser().parse_args(
            ["--root", str(self.root), "--rollback", result["backup"]]
        )
        with patch.object(updater, "client_activity", return_value=self.activity()):
            with self.assertRaisesRegex(RuntimeError, "Active client"):
                updater.execute(args)
        self.assertEqual(updater.version(self.root), "1.2.0")

    def test_saved_recovery_command_works_without_installed_launcher_or_script(self):
        result = self.update()
        (self.root / "local-ai").unlink()
        updater.remove(self.root / "scripts")
        command = result["rollback_command"]
        self.assertEqual(Path(command[1]).parent, Path(result["backup"]))
        completed = subprocess.run(command, capture_output=True, text=True, timeout=15)
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertEqual(json.loads(completed.stdout)["state"], "rolled-back")
        self.assertEqual(updater.version(self.root), "1.1.0")
        self.assert_assets_untouched()

    @unittest.skipUnless(Path("/proc/self/exe").exists(), "requires Linux procfs")
    def test_real_process_detected_without_stopping_it(self):
        # A renamed system utility can be a multicall binary (CI coreutils).
        # Use a genuine Python launcher owned by this installation instead.
        ready = self.root / "process-ready"
        launcher = self.root / "local-ai"
        launcher.write_text(
            "from pathlib import Path\n"
            + f"Path({str(ready)!r}).write_text('ready')\n"
            + "import time\ntime.sleep(60)\n"
        )
        child = subprocess.Popen(
            [sys.executable, str(launcher)], stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        try:
            deadline = time.monotonic() + 5
            while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
                time.sleep(0.01)
            self.assertTrue(ready.exists(), "fixture launcher did not become ready")
            report = updater.client_activity(self.root)
            self.assertIn(child.pid, [item["pid"] for item in report["processes"]])
            with self.assertRaisesRegex(RuntimeError, "Active client"):
                self.update()
            self.assertIsNone(child.poll())
        finally:
            if child.poll() is None:
                child.terminate()
            child.communicate(timeout=5)


class ActivityScanTests(unittest.TestCase):
    def test_association_boundaries_deleted_executable_and_launcher(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "install"
            root.mkdir()
            proc = Path(tmp) / "proc"
            proc.mkdir()

            def process(pid, executable, args=(), cwd=None, environment=b""):
                entry = proc / str(pid)
                entry.mkdir()
                (entry / "exe").symlink_to(executable)
                (entry / "cwd").symlink_to(cwd or root, target_is_directory=True)
                (entry / "cmdline").write_bytes(b"\0".join(os.fsencode(x) for x in args))
                (entry / "environ").write_bytes(environment)

            process(4711, str(root / "clients/amd64/bin/opencode") + " (deleted)")
            process(4712, root.parent / "install-other/clients/bin/opencode")
            process(4713, "/usr/bin/python3", ["python3", str(root / "local-ai")])
            process(
                4714,
                "/usr/bin/python3",
                ["python3", "-m", "local_ai.cli"],
                cwd=root.parent,
                environment=b"SECRET=not-in-report\0PYTHONPATH=" + os.fsencode(root / "src"),
            )
            process(4715, "/bin/echo", ["echo", str(root / "local-ai")])
            process(
                4716,
                "/usr/bin/python3",
                ["python3", "-m", "local_ai.cli"],
                environment=b"PYTHONPATH=/other/src",
            )
            report = updater.client_activity(root, proc)
            self.assertEqual([p["pid"] for p in report["processes"]], [4711, 4713, 4714])
            self.assertNotIn("SECRET", json.dumps(report))
            self.assertNotIn("not-in-report", json.dumps(report))
            self.assertFalse(updater.client_activity(root, proc / "missing")["supported"])
