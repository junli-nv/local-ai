import argparse
import hashlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_ai import hub, preparation
from local_ai.cli import parser, preflight
from local_ai.profiles import profile

REVISION = "a" * 40


class Response(io.BytesIO):
    def __init__(self, data, status=200, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {}


def entry(name, data, lfs=False):
    digest = (
        hashlib.sha256(data).hexdigest()
        if lfs
        else hashlib.sha1(("blob %d\0" % len(data)).encode() + data).hexdigest()
    )
    return {"rfilename": name, "size": len(data), "digest": digest}


class HubTests(unittest.TestCase):
    def test_metadata_is_pinned_and_paths_are_checked(self):
        policy = {**profile("gb200-tp4"), "revision": REVISION}
        item = entry("config.json", b"{}")
        raw = {**item, "blobId": item["digest"]}
        payload = {"sha": REVISION, "siblings": [raw]}

        def response():
            return Response(json.dumps(payload).encode())

        with patch("local_ai.hub.urllib.request.urlopen", side_effect=lambda *a, **k: response()):
            self.assertEqual(hub.metadata(policy)[0]["digest"], item["digest"])
            for name in ("../escape", "/absolute", ".cache/file", "model.lock.json", "."):
                payload["siblings"][0]["rfilename"] = name
                with self.subTest(name=name), self.assertRaises(ValueError):
                    hub.metadata(policy)
            payload["sha"] = "b" * 40
            with self.assertRaisesRegex(ValueError, "revision differs"):
                hub.metadata(policy)

    def test_resume_and_ignored_range(self):
        for status in (200, 206):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as directory:
                part = Path(directory) / "part"
                part.write_bytes(b"ab")
                response = Response(
                    b"cdef" if status == 206 else b"abcdef",
                    status,
                    {"Content-Range": "bytes 2-5/6"} if status == 206 else {},
                )
                with patch("local_ai.hub.urllib.request.urlopen", return_value=response) as request:
                    hub.transfer("https://huggingface.co/file", part, 6)
                self.assertEqual(part.read_bytes(), b"abcdef")
                self.assertEqual(request.call_args.args[0].get_header("Range"), "bytes=2-")

    def test_corruption_reuse_and_symlinks(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            item = entry("weights", b"good", lfs=True)
            policy = {"repo": "example/model", "revision": REVISION}

            def corrupt(url, destination, size):
                destination.write_bytes(b"evil")

            with (
                patch("local_ai.hub.transfer", side_effect=corrupt),
                patch("local_ai.hub.time.sleep"),
            ):
                with self.assertRaisesRegex(ValueError, "checksum"):
                    hub.download_file(base, policy, item)
            self.assertFalse((base / "weights").exists())
            (base / "weights").write_bytes(b"good")
            with patch("local_ai.hub.transfer", side_effect=AssertionError("network")):
                hub.download_file(base, policy, item)
            (base / "link").symlink_to(base / "weights")
            with self.assertRaisesRegex(ValueError, "symbolic"):
                hub.safe_path(base, "link")

    def test_arm_model_download_and_reuse(self):
        from test_installation import model_fixture

        with tempfile.TemporaryDirectory() as source, tempfile.TemporaryDirectory() as target:
            _, directory = model_fixture(source)
            contents = {p.name: p.read_bytes() for p in directory.iterdir()}
            entries = [entry(n, d, n.endswith(".safetensors")) for n, d in contents.items()]
            policy = profile("gb200-tp4")

            def transfer(url, destination, size):
                destination.write_bytes(contents[url.rsplit("/", 1)[1]])

            with (
                patch("local_ai.hub.metadata", return_value=entries),
                patch("local_ai.hub.transfer", side_effect=transfer),
                patch("subprocess.run", side_effect=AssertionError("no target program")),
                patch("local_ai.server.inventory", side_effect=AssertionError("no GPU")),
            ):
                value = hub.download_model(target, policy)
                self.assertTrue(value["revision_verified"])
            with patch("local_ai.hub.metadata", side_effect=AssertionError("no network")):
                self.assertFalse(hub.download_model(target, policy)["network"])
            lock = Path(value["model"]) / "model.lock.json"
            self.assertEqual(json.loads(lock.read_text())["revision"], policy["revision"])

    def test_unlocked_local_files_are_verified_against_pinned_metadata(self):
        from test_installation import model_fixture

        with tempfile.TemporaryDirectory() as directory:
            policy, model = model_fixture(directory, locked=False)
            entries = [entry(p.name, p.read_bytes()) for p in model.iterdir()]
            with (
                patch("local_ai.hub.metadata", return_value=entries),
                patch("local_ai.hub.transfer", side_effect=AssertionError("reuse valid files")),
            ):
                result = hub.download_model(directory, policy)
            self.assertTrue(result["revision_verified"])
            self.assertTrue((model / "model.lock.json").exists())

    def test_bad_resume_and_short_response_are_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            part = Path(directory) / "part"
            part.write_bytes(b"ab")
            bad = Response(b"cdef", 206, {"Content-Range": "bytes 0-3/6"})
            with patch("local_ai.hub.urllib.request.urlopen", return_value=bad):
                with self.assertRaisesRegex(ValueError, "resumed"):
                    hub.transfer("https://huggingface.co/file", part, 6)
            with patch("local_ai.hub.urllib.request.urlopen", return_value=Response(b"x")):
                with self.assertRaisesRegex(OSError, "Incomplete"):
                    hub.transfer("https://huggingface.co/file", part, 6)


class PreparationTests(unittest.TestCase):
    def test_multiple_platforms_without_target_execution(self):
        with tempfile.TemporaryDirectory() as directory:
            options = argparse.Namespace(
                profile=["gb200-tp4", "b300-tp4"], data_dir=directory, force=False
            )
            seen = []

            def pull(root, policy, force=False):
                seen.append(policy["platform"])
                return {"network": False}

            with (
                patch("local_ai.preparation.images.pull", side_effect=pull),
                patch(
                    "local_ai.preparation.hub.download_model", return_value={"network": False}
                ) as model,
                patch(
                    "local_ai.preparation.ensure_archive",
                    return_value=Path(directory) / "image.tar",
                ),
                patch("local_ai.common.arch", side_effect=AssertionError("no architecture gate")),
                patch("subprocess.run", side_effect=AssertionError("no target execution")),
            ):
                result = preparation.prepare(options)
            self.assertEqual(set(seen), {"linux/amd64", "linux/arm64"})
            self.assertTrue(result["prepared"])
            model.assert_called_once()
            self.assertTrue(result["resources"][1]["model"]["shared"])
            self.assertFalse((Path(directory) / "installation.json").exists())

    def test_planning_only_rejected_before_resources(self):
        args = parser().parse_args(["prepare", "--profile", "rubin-tp2-framework"])
        with patch("local_ai.preparation.images.pull", side_effect=AssertionError("no Docker")):
            with self.assertRaisesRegex(ValueError, "not deployable"):
                preflight(args)

    def test_conflicting_model_revisions_rejected_before_download(self):
        first = profile("b300-tp4")
        second = dict(profile("gb200-tp4"), revision="b" * 40)
        with patch("local_ai.preparation.profile", side_effect=[first, second]):
            with self.assertRaisesRegex(ValueError, "conflicting"):
                preparation.policies(["b300-tp4", "gb200-tp4"])
