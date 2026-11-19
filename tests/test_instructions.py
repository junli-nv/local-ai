import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_ai import cli, instructions


class InstructionTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.base = Path(temp.name)
        self.config = self.base / "config"
        env = patch.dict(os.environ, {"XDG_CONFIG_HOME": str(self.config)})
        env.start()
        self.addCleanup(env.stop)
        self.target = self.config / "opencode/AGENTS.md"

    def existing(self, value):
        self.target.parent.mkdir(parents=True, exist_ok=True)
        self.target.write_bytes(value)

    def test_first_install_defaults_and_reinstall_are_idempotent(self):
        result = instructions.apply()
        self.assertEqual(result["status"], "created")
        self.assertEqual(self.target.stat().st_mode & 0o777, 0o600)
        self.assertIn("长任务等待与进度汇报", self.target.read_text())
        self.assertNotIn("# BCM 场景约定", self.target.read_text())
        before = self.target.stat()
        self.assertEqual(instructions.apply()["status"], "unchanged")
        self.assertEqual(self.target.stat().st_ino, before.st_ino)
        self.assertFalse(list(self.target.parent.glob("AGENTS.md.bak-*")))

    def test_existing_bytes_preserved_and_private_backup_created(self):
        original = "# 私人规则\r\n保持我的配置".encode()
        self.existing(original)
        result = instructions.apply()
        self.assertTrue(self.target.read_bytes().startswith(original))
        backup = Path(result["backup"])
        self.assertEqual(backup.read_bytes(), original)
        self.assertEqual(backup.stat().st_mode & 0o777, 0o600)

    def test_reinstall_updates_only_managed_block(self):
        self.existing(b"personal prefix\n")
        instructions.apply()
        with self.target.open("ab") as stream:
            stream.write(b"personal suffix\n")
        previous = self.target.read_bytes()
        result = instructions.apply("bcm", "en")
        text = self.target.read_bytes()
        self.assertTrue(text.startswith(b"personal prefix\n\n"))
        self.assertTrue(text.endswith(b"personal suffix\n"))
        self.assertEqual(text.count(instructions.BEGIN), 1)
        self.assertIn(b"# Personal work instructions", text)
        self.assertIn(b"# BCM scenario instructions", text)
        self.assertNotIn("长任务等待与进度汇报".encode(), text)
        self.assertEqual(Path(result["backup"]).read_bytes(), previous)

    def test_template_update_is_applied_on_reinstall(self):
        instructions.apply()
        with patch(
            "local_ai.instructions.content",
            return_value=instructions.BEGIN + b"\nnew\n" + instructions.END,
        ):
            self.assertEqual(instructions.apply()["status"], "updated")
        self.assertIn(b"\nnew\n", self.target.read_bytes())

    def test_exact_legacy_copies_are_migrated_with_backup_and_custom_bytes_preserved(self):
        body = (
            instructions.content("general", "zh")
            .split(instructions.BEGIN + b"\n", 1)[1]
            .split(b"\n" + instructions.END)[0]
        )
        original = (
            b"MY PREFIX\r\n\r\n"
            + body
            + b"\n\n"
            + body
            + b"\n\n"
            + instructions.content("bcm", "zh")
            + b"\nMY SUFFIX\n"
        )
        self.existing(original)
        result = instructions.apply("bcm", "zh")
        self.assertEqual(result["legacy_copies_removed"], 2)
        self.assertEqual(Path(result["backup"]).read_bytes(), original)
        current = self.target.read_bytes()
        self.assertTrue(current.startswith(b"MY PREFIX\r\n\r\n"))
        self.assertTrue(current.endswith(b"\nMY SUFFIX\n"))
        self.assertEqual(current.count("# 个人全局工作约定".encode()), 1)
        self.assertEqual(instructions.apply("bcm", "zh")["status"], "unchanged")

    def test_modified_and_fenced_legacy_rules_are_preserved(self):
        block = instructions.content("general", "zh")
        body = block[len(instructions.BEGIN) + 1 : -len(instructions.END)].strip()
        fence = bytes([96]) * 3
        original = (
            fence
            + b"markdown\n"
            + body
            + b"\n"
            + fence
            + b"\n\n"
            + body.replace("回复语言".encode(), "我的回复语言".encode())
            + b"\n"
        )
        self.existing(original)
        instructions.apply()
        self.assertTrue(self.target.read_bytes().startswith(original))

    def test_unmarked_english_crlf_template_is_migrated(self):
        block = instructions.content("bcm", "en")
        body = block[len(instructions.BEGIN) + 1 : -len(instructions.END)].strip()
        self.existing(body.replace(b"\n", b"\r\n") + b"\r\n")
        result = instructions.apply("bcm", "en")
        self.assertEqual(result["legacy_copies_removed"], 1)
        self.assertEqual(self.target.read_bytes(), block + b"\n")

    def test_none_does_not_read_templates_or_create_configuration(self):
        with patch("local_ai.instructions.content", side_effect=AssertionError("no read")):
            self.assertEqual(instructions.apply("none"), {"status": "skipped"})
        self.assertFalse(self.config.exists())

    def test_none_preserves_existing_managed_block(self):
        instructions.apply()
        previous = self.target.read_bytes()
        instructions.apply("none")
        self.assertEqual(self.target.read_bytes(), previous)

    def test_malformed_markers_rejected_without_rewriting(self):
        for original in (
            instructions.BEGIN,
            instructions.END,
            instructions.END + instructions.BEGIN,
            instructions.BEGIN * 2 + instructions.END,
        ):
            with self.subTest(original=original):
                self.existing(original)
                with self.assertRaisesRegex(ValueError, "markers"):
                    instructions.apply()
                self.assertEqual(self.target.read_bytes(), original)
                self.assertFalse(list(self.target.parent.glob("AGENTS.md.bak-*")))

    def test_symlink_is_rejected_without_changing_destination(self):
        destination = self.base / "linked-rules"
        destination.write_bytes(b"mine")
        self.target.parent.mkdir(parents=True)
        self.target.symlink_to(destination)
        with self.assertRaisesRegex(ValueError, "symlink"):
            instructions.apply()
        self.assertEqual(destination.read_bytes(), b"mine")

    def test_replace_failure_preserves_original_and_backup(self):
        self.existing(b"original")
        with patch("local_ai.instructions.os.replace", side_effect=OSError("disk error")):
            with self.assertRaisesRegex(OSError, "disk error"):
                instructions.apply()
        self.assertEqual(self.target.read_bytes(), b"original")
        self.assertEqual(len(list(self.target.parent.glob("AGENTS.md.bak-*"))), 1)
        self.assertFalse(list(self.target.parent.glob(".AGENTS.md-*")))

    def test_missing_templates_fail_without_creating_user_files(self):
        with patch("local_ai.instructions.root", return_value=self.base / "missing"):
            with self.assertRaises(FileNotFoundError):
                instructions.apply()
        self.assertFalse(self.config.exists())

    def test_default_path_and_empty_xdg_match_client_loading(self):
        with (
            patch.dict(os.environ, {"XDG_CONFIG_HOME": ""}),
            patch("pathlib.Path.home", return_value=self.base),
        ):
            self.assertEqual(instructions.personal_path(), self.base / ".config/opencode/AGENTS.md")

    def test_lower_level_install_applies_rules_after_binary_install(self):
        args = cli.parser().parse_args(
            [
                "client",
                "install",
                "--client-dir",
                str(self.base / "assets"),
                "--instructions",
                "bcm",
                "--instructions-language",
                "en",
            ]
        )
        with patch("local_ai.artifacts.install", return_value={"network": False}):
            result = cli.dispatch(args)
        self.assertEqual(result["instructions"]["status"], "created")
        self.assertIn("# BCM scenario instructions", self.target.read_text())

    def test_failed_binary_install_does_not_apply_rules(self):
        with patch("local_ai.artifacts.install", side_effect=ValueError("binary invalid")):
            with self.assertRaisesRegex(ValueError, "binary invalid"):
                cli.dispatch(cli.parser().parse_args(["client", "install"]))
        self.assertFalse(self.config.exists())
