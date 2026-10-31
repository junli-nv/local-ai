import base64
import hashlib
import tarfile
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from local_ai.artifacts import extract_binary, seed_cache, verify_integrity
from local_ai.client import prepare, service_key
from local_ai.common import verify_elf
from local_ai.tunnel import Tunnel, destination, ssh_command


class ClientTests(unittest.TestCase):
    def test_ssh_argument_injection_is_rejected(self):
        for name in ["-oProxyCommand=bad", "host;bad", "host with spaces"]:
            with self.assertRaises(ValueError):
                destination(name)
        self.assertEqual(destination("user@gpu-a"), "user@gpu-a")

    def test_ssh_forward_is_loopback_and_not_persistent(self):
        cmd = ssh_command("gpu-a", "alice", 22, 28000, 18001)
        self.assertIn("127.0.0.1:28000:127.0.0.1:18001", cmd)
        self.assertIn("ExitOnForwardFailure=yes", cmd)
        self.assertNotIn("-f", cmd)
        self.assertEqual(cmd[-1], "alice@gpu-a")

    def test_history_key_tracks_server_not_ephemeral_port(self):
        a = service_key("gpu-a", "alice", 22, 18000, None)
        self.assertEqual(a, service_key("gpu-a", "alice", 22, 18000, None))
        self.assertNotEqual(a, service_key("gpu-a", "alice", 22, 18001, None))

    def test_tunnel_cleanup_runs_on_client_exception(self):
        with tempfile.TemporaryDirectory() as root:
            proc = Mock()
            proc.poll.return_value = None
            with patch("local_ai.tunnel.subprocess.Popen", return_value=proc):
                with self.assertRaises(RuntimeError):
                    with Tunnel("gpu-a", None, 22, 18000, 28000, Path(root) / "tunnel.log"):
                        raise RuntimeError("client failed")
            proc.terminate.assert_called_once()
            proc.wait.assert_called_once_with(timeout=3)

    def test_integrity_check_precedes_archive_execution(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "data"
            path.write_bytes(b"valid")
            checksum = "sha512-" + base64.b64encode(hashlib.sha512(b"valid").digest()).decode()
            verify_integrity(path, checksum)
            path.write_bytes(b"changed")
            with self.assertRaises(ValueError):
                verify_integrity(path, checksum)

    def test_archive_symlink_cannot_become_executable(self):
        with tempfile.TemporaryDirectory() as root:
            archive = Path(root) / "x.tgz"
            with tarfile.open(archive, "w:gz") as tar:
                info = tarfile.TarInfo("package/bin/opencode")
                info.type = tarfile.SYMTYPE
                info.linkname = "/etc/passwd"
                tar.addfile(info)
            with self.assertRaises(ValueError):
                extract_binary(archive, Path(root) / "out")

    def test_cache_seed_does_not_copy_private_databases(self):
        with tempfile.TemporaryDirectory() as root:
            source = Path(root) / "source"
            (source / "opencode").mkdir(parents=True)
            (source / "opencode/models.json").write_text("{}")
            (source / "opencode/opencode.db").write_text("private")
            (source / "auth.json").write_text("private")
            out = Path(root) / "out"
            seed_cache(source, out, "amd64")
            self.assertTrue((out / "opencode/models.json").exists())
            self.assertFalse((out / "auth.json").exists())
            self.assertFalse((out / "opencode/opencode.db").exists())

    def test_wrong_architecture_executable_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "elf"
            value = bytearray(20)
            value[:4] = b"\x7fELF"
            value[4] = 2
            value[5] = 1
            value[18:20] = (183).to_bytes(2, "little")
            path.write_bytes(value)
            self.assertEqual(verify_elf(path, "arm64"), "arm64")
            with self.assertRaises(ValueError):
                verify_elf(path, "amd64")

    def test_same_user_two_sessions_get_independent_connection_configs(self):
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            state = root / "state"
            state.mkdir()
            assets = root / "assets"
            (assets / "seed-cache").mkdir(parents=True)
            one = state / "one"
            two = state / "two"
            one.mkdir()
            two.mkdir()
            env1 = prepare(state, assets, one, "http://127.0.0.1:28000/v1", "model", root)
            env2 = prepare(state, assets, two, "http://127.0.0.1:28001/v1", "model", root)
            self.assertEqual(env1["XDG_DATA_HOME"], env2["XDG_DATA_HOME"])
            self.assertNotEqual(env1["OPENCODE_CONFIG"], env2["OPENCODE_CONFIG"])
            self.assertIn("28000", Path(env1["OPENCODE_CONFIG"]).read_text())
            self.assertIn("28001", Path(env2["OPENCODE_CONFIG"]).read_text())
            self.assertEqual(Path(env1["OPENCODE_CONFIG"]).stat().st_mode & 0o777, 0o600)
