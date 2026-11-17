"""Regressions for stale release examples and stale packaged documentation."""

import io
import tarfile
import tempfile
import unittest
from pathlib import Path

from scripts.check_release_docs import check, check_text


class GuideVersionTests(unittest.TestCase):
    def test_current_project_downloads_and_upgrade_examples_match_release(self):
        result = check(Path(__file__).resolve().parents[1])
        self.assertGreater(result["documents"], 30)
        self.assertGreater(result["current_version_references"], 10)

    def test_old_download_and_upgrade_examples_are_rejected(self):
        for text in (
            "https://github.com/junli-nv/local-ai/archive/refs/tags/v1.3.7.tar.gz",
            "--version v1.3.7",
            "local_ai_source=/tmp/local-ai-v1.3.7-source.tar.gz",
            "源码下载固定 v1.3.4",
        ):
            with self.assertRaises(ValueError):
                check_text("docs/offline.md", text, "1.4.0")
        self.assertEqual(check_text("docs/validation.md", "--version v1.3.7", "1.4.0"), 0)

    def test_stale_or_missing_packaged_manual_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "src/local_ai").mkdir(parents=True)
            (root / "src/local_ai/__init__.py").write_text('__version__ = "1.4.0"\n')
            (root / "pyproject.toml").write_text('version = "1.4.0"\n')
            (root / "README.md").write_text("Current manual\n")
            archive = root / "source.tar"
            with tarfile.open(archive, "w") as tar:
                data = b"Outdated manual\n"
                member = tarfile.TarInfo("local-ai/README.md")
                member.size = len(data)
                tar.addfile(member, io.BytesIO(data))
            with self.assertRaisesRegex(ValueError, "stale packaged"):
                check(root, archive)
