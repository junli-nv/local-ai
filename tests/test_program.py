import hashlib
import json
import os
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from test_installation import model_fixture

from local_ai import bundle, deployment
from local_ai.cli import parser
from local_ai.common import arch
from local_ai.program import source_files


class PortableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.work = Path(self.temp.name)
        self.base = self.work / "download"
        repo = Path(__file__).parents[1]
        for name, path in source_files(repo).items():
            target = self.base / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        self.env = {
            k: v
            for k, v in os.environ.items()
            if k not in {"LOCAL_AI_ROOT", "LOCAL_AI_DATA_DIR", "LOCAL_AI_CATALOG", "PYTHONPATH"}
        }
        self.patch = patch.dict(
            os.environ, {**self.env, "LOCAL_AI_ROOT": str(self.base)}, clear=True
        )
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.client = self.base / "clients" / arch()
        (self.client / "bin").mkdir(parents=True)
        (self.client / "seed-cache").mkdir()
        header = bytearray(20)
        header[:4], header[4], header[5] = b"\x7fELF", 2, 1
        header[18:20] = (62 if arch() == "amd64" else 183).to_bytes(2, "little")
        binary = self.client / "bin/opencode"
        binary.write_bytes(header)
        binary.chmod(0o755)
        (self.client / "manifest.json").write_text(
            json.dumps(
                {
                    "version": "9.9.9",
                    "arch": arch(),
                    "sha256": hashlib.sha256(header).hexdigest(),
                    "source": "test fixture",
                }
            )
        )

    def invoke(self, base, *args):
        return subprocess.run(
            [str(base / "local-ai"), *args],
            cwd=self.work,
            env=self.env,
            text=True,
            capture_output=True,
        )

    def export(self, profiles=None):
        output = self.work / "portable.tar"
        args = ["export", "--output", str(output)]
        for name in profiles or []:
            args += ["--profile", name]
        return bundle.export(parser().parse_args(args))

    def unpack(self, result):
        target = self.work / "target"
        target.mkdir()
        with tarfile.open(result["archive"]) as tar:
            names = tar.getnames()
            self.assertIn("local-ai/src/local_ai/cli.py", names)
            self.assertIn("local-ai/install.sh", names)
            self.assertFalse(any(member.issym() for member in tar.getmembers()))
            tar.extractall(target, filter="data")
        renamed = target / "another-name"
        (target / "local-ai").rename(renamed)
        return renamed

    def test_export_rename_delete_source_and_offline_install(self):
        for name in [
            ".env",
            "credentials.json",
            "instances/a/spec.json",
            "users/private/history.db",
        ]:
            path = self.base / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text("must not travel")
        result = self.export()
        self.assertEqual(
            Path(result["sha256_file"]).read_text().split()[0],
            hashlib.sha256(Path(result["archive"]).read_bytes()).hexdigest(),
        )
        renamed = self.unpack(result)
        shutil.rmtree(self.base)
        self.assertFalse((renamed / ".env").exists())
        self.assertFalse((renamed / "credentials.json").exists())
        self.assertFalse((renamed / "instances").exists())
        self.assertFalse((renamed / "users").exists())
        installed = self.invoke(renamed, "install", "--role", "client", "--offline")
        self.assertEqual(installed.returncode, 0, installed.stderr)
        info = json.loads(installed.stdout)
        self.assertEqual(info["root"], str(renamed))
        self.assertEqual(info["source"], str(renamed / "src"))
        self.assertTrue(info["offline"])
        self.assertFalse((renamed / ".local-ai").exists())
        self.assertIn(str(renamed), self.invoke(renamed, "server", "stop", "--help").stdout)
        self.assertTrue((renamed / "src/local_ai/cli.py").is_file())

    def test_corruption_fails_before_resource_install(self):
        renamed = self.unpack(self.export())
        changed = renamed / "src/local_ai/operations.py"
        changed.write_text(changed.read_text() + "\n# changed after export\n")
        result = self.invoke(renamed, "install", "--role", "client", "--offline")
        self.assertEqual(result.returncode, 1)
        self.assertIn("checksum mismatch", result.stderr)

    def test_offline_client_never_downloads_and_saves_endpoint(self):
        args = parser().parse_args(
            [
                "install",
                "--role",
                "client",
                "--offline",
                "--endpoint",
                "http://GPU001:18000/v1",
            ]
        )
        with patch("urllib.request.urlopen", side_effect=AssertionError("no network")):
            result = deployment.install(args)
        self.assertTrue(result["installed"])
        self.assertEqual(parser().parse_args(["chat"]).endpoint, "http://GPU001:18000/v1")
        self.assertEqual(self.client.stat().st_mode & 0o777, 0o755)

    def test_default_endpoint_optional_preserved_and_reconfigurable_offline(self):
        with patch("urllib.request.urlopen", side_effect=AssertionError("no network")):
            for extra, expected in (
                ([], None),
                (["--endpoint", "http://GPU001:18000/v1"], "http://GPU001:18000/v1"),
                ([], "http://GPU001:18000/v1"),
                (["--endpoint", "http://GPU002:18000/v1"], "http://GPU002:18000/v1"),
            ):
                result = deployment.install(
                    parser().parse_args(["install", "--role", "client", "--offline", *extra])
                )
                self.assertEqual(result["client"]["status"], "already-present")
                self.assertFalse(result["client"]["network"])
                self.assertEqual(parser().parse_args(["chat"]).endpoint, expected)

    def test_missing_offline_client_never_falls_back_to_download(self):
        (self.client / "manifest.json").unlink()
        with patch("urllib.request.urlopen", side_effect=AssertionError("no network")):
            with self.assertRaisesRegex(ValueError, "no client"):
                deployment.install(parser().parse_args(["install", "--offline"]))

    def test_server_export_and_import_use_new_paths_without_starting_gpu(self):
        policy, _ = model_fixture(self.base)
        archive = deployment.archive_path(self.base, policy)
        archive.parent.mkdir()
        archive.write_bytes(b"image fixture")
        Path(str(archive) + ".lock.json").write_text(
            json.dumps(
                {
                    "reference": policy["image"],
                    "platform": policy["platform"],
                    "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
                }
            )
        )
        renamed = self.unpack(self.export(["b300-tp4"]))
        with patch.dict(os.environ, {"LOCAL_AI_ROOT": str(renamed)}):
            with (
                patch("local_ai.images.inspect_image", return_value=None),
                patch("local_ai.images.import_image", return_value={"imported": True}) as load,
                patch("local_ai.images.pull", side_effect=AssertionError("no download")),
                patch("local_ai.server.start", side_effect=AssertionError("no GPU start")),
            ):
                result = deployment.install(
                    parser().parse_args(["install", "--role", "server", "--offline"])
                )
        self.assertEqual(result["data_dir"], str(renamed))
        self.assertFalse(result["server"]["started"])
        self.assertEqual(load.call_args.args[0], renamed)

    def test_export_rejects_recursive_destination_and_unsafe_manifest(self):
        with self.assertRaisesRegex(ValueError, "outside"):
            bundle.export(parser().parse_args(["export", "--output", str(self.base / "copy.tar")]))
        (self.base / "bundle.json").write_text(
            json.dumps(
                {
                    "format": 1,
                    "files": {"../outside": "invalid"},
                }
            )
        )
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            bundle.verify(self.base)

    def test_default_dist_export_does_not_include_previous_archives(self):
        first = bundle.export(parser().parse_args(["export"]))
        self.assertEqual(Path(first["archive"]), self.base / "dist/local-ai.tar")
        second = bundle.export(parser().parse_args(["export"]))
        with tarfile.open(second["archive"]) as tar:
            self.assertFalse(any(name.startswith("local-ai/dist/") for name in tar.getnames()))
        self.assertTrue(Path(second["sha256_file"]).is_file())

    def test_compressed_export_can_be_unpacked_and_installed(self):
        result = bundle.export(
            parser().parse_args(["export", "--output", str(self.work / "portable.tar.gz")])
        )
        renamed = self.unpack(result)
        installed = self.invoke(renamed, "install", "--role", "client", "--offline")
        self.assertEqual(installed.returncode, 0, installed.stderr)

    def test_explicit_legacy_client_selection_overrides_default_same_architecture(self):
        result = bundle.export(parser().parse_args(["export", "--client-dir", str(self.client)]))
        self.assertEqual(result["clients"], [arch()])

    def test_installed_client_model_is_used_by_chat(self):
        options = parser().parse_args(
            ["install", "--role", "client", "--offline", "--model", "another-model"]
        )
        deployment.install(options)
        self.assertEqual(parser().parse_args(["chat"]).model, "another-model")

    def test_reinstall_allows_source_updates_but_still_checks_client_integrity(self):
        renamed = self.unpack(self.export())
        initial = self.invoke(renamed, "install", "--role", "client", "--offline")
        self.assertEqual(initial.returncode, 0, initial.stderr)
        readme = renamed / "README.md"
        readme.write_text(readme.read_text() + "\nupdated source documentation\n")
        repeated = self.invoke(renamed, "install", "--offline")
        self.assertEqual(repeated.returncode, 0, repeated.stderr)
        binary = renamed / "clients" / arch() / "bin/opencode"
        binary.write_bytes(binary.read_bytes() + b"corrupted")
        corrupt = self.invoke(renamed, "install", "--offline")
        self.assertEqual(corrupt.returncode, 1)
        self.assertIn("Client binary changed", corrupt.stderr)

    def test_unrecognized_client_cache_files_are_excluded(self):
        secret = self.client / "seed-cache/private-token"
        secret.write_text("must not travel")
        result = self.export()
        with tarfile.open(result["archive"]) as tar:
            self.assertFalse(any("private-token" in name for name in tar.getnames()))
