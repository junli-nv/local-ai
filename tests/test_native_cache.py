import json
import tempfile
import unittest
from pathlib import Path

from local_ai.native_cache import complete, prime


def fixture(path, version="1.19.5"):
    module = path / "node_modules/@opencode-ai/plugin"
    module.mkdir(parents=True)
    (module / "package.json").write_text(json.dumps({"version": version}))
    (path / "package.json").write_text(
        json.dumps({"dependencies": {"@opencode-ai/plugin": version}})
    )
    (path / "package-lock.json").write_text(
        json.dumps(
            {
                "packages": {
                    "": {"dependencies": {"@opencode-ai/plugin": version}},
                    "node_modules/@opencode-ai/plugin": {"version": version},
                }
            }
        )
    )
    (path / "opencode.json").write_text('{"private_connection":"do-not-copy"}')


class NativeCacheTests(unittest.TestCase):
    def test_matching_dependencies_are_copied_without_connection_or_shared_writes(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            state = root / "state"
            assets = root / "assets"
            assets.mkdir()
            (assets / "manifest.json").write_text(
                json.dumps({"version": "1.19.5", "sha256": "binary"})
            )
            source = state / "logs/old/config/opencode"
            fixture(source)
            first = state / "logs/one"
            first.mkdir()
            second = state / "logs/two"
            second.mkdir()
            self.assertTrue(prime(state, assets, first))
            self.assertTrue(prime(state, assets, second))
            target = first / "config/opencode"
            self.assertFalse((target / "opencode.json").exists())
            self.assertNotEqual(
                (source / "package.json").stat().st_ino, (target / "package.json").stat().st_ino
            )
            (target / "package.json").write_text("{}")
            self.assertTrue(complete(second / "config/opencode", "1.19.5"))
            self.assertTrue(complete(source, "1.19.5"))

    def test_version_mismatch_or_missing_lock_never_fakes_installation(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            state = root / "state"
            assets = root / "assets"
            assets.mkdir()
            (assets / "manifest.json").write_text('{"version":"2.0.0"}')
            source = state / "logs/old/config/opencode"
            fixture(source)
            self.assertFalse(prime(state, assets, state / "logs/new"))
            self.assertFalse((state / "logs/new/config/opencode/node_modules").exists())
            (source / "package-lock.json").unlink()
            self.assertFalse(complete(source, "1.19.5"))

    def test_unknown_manifest_does_not_create_dependency_install(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            self.assertFalse(prime(root, root / "assets", root / "session"))
            self.assertFalse((root / "session").exists())
