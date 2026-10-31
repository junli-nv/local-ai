import argparse
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_ai import images, installlog
from local_ai.common import atomic_json, run
from local_ai.profiles import profile
from local_ai.server import validate_model


def model_fixture(root, locked=True):
    policy = profile("b300-tp4")
    directory = Path(root) / "models" / policy["model_directory"]
    directory.mkdir(parents=True)
    for filename in ["config.json", "tokenizer.json"]:
        (directory / filename).write_text("{}")
    header = json.dumps({"x": {"dtype": "F32", "shape": [1], "data_offsets": [0, 4]}}).encode()
    header += b" " * (-len(header) % 8)
    (directory / "part.safetensors").write_bytes(
        len(header).to_bytes(8, "little") + header + bytes(4)
    )
    (directory / "model.safetensors.index.json").write_text(
        json.dumps({"weight_map": {"x": "part.safetensors"}})
    )
    if locked:
        atomic_json(
            Path(root) / "models/model.lock.json",
            {"repo": policy["repo"], "revision": policy["revision"]},
        )
    return policy, directory


def options(root, action="pull"):
    return argparse.Namespace(group="image", action=action, data_dir=Path(root), install_log=None)


class CacheTests(unittest.TestCase):
    def test_complete_model_never_invokes_network_or_docker(self):
        with tempfile.TemporaryDirectory() as root:
            policy, _ = model_fixture(root)
            with (
                patch("local_ai.images.resolve_image", side_effect=AssertionError("no Docker")),
                patch("local_ai.images.download_command", side_effect=AssertionError("no network")),
            ):
                result = images.download_model(root, policy)
            self.assertFalse(result["network"])
            self.assertTrue(result["revision_verified"])

    def test_unprovenanced_complete_model_is_explicitly_unverified(self):
        with tempfile.TemporaryDirectory() as root:
            policy, _ = model_fixture(root, locked=False)
            result = images.download_model(root, policy)
            self.assertFalse(result["network"])
            self.assertFalse(result["revision_verified"])
            self.assertFalse((Path(root) / "models/model.lock.json").exists())

    def test_revision_conflict_is_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            policy, _ = model_fixture(root)
            atomic_json(
                Path(root) / "models/model.lock.json", {"repo": policy["repo"], "revision": "other"}
            )
            with patch(
                "local_ai.images.download_command", side_effect=AssertionError("no download")
            ):
                with self.assertRaisesRegex(ValueError, "revision conflicts"):
                    images.download_model(root, policy)

    def test_truncated_shard_is_rejected_without_network(self):
        with tempfile.TemporaryDirectory() as root:
            policy, directory = model_fixture(root)
            shard = directory / "part.safetensors"
            shard.write_bytes(shard.read_bytes()[:-1])
            with self.assertRaisesRegex(ValueError, "Truncated"):
                images.download_model(root, policy)

    def test_missing_shard_is_not_claimed_complete(self):
        with tempfile.TemporaryDirectory() as root:
            policy, directory = model_fixture(root)
            (directory / "part.safetensors").unlink()
            self.assertIsNone(images.cached_model(root, policy))

    def test_symlink_outside_model_is_rejected(self):
        with tempfile.TemporaryDirectory() as root:
            policy, directory = model_fixture(root)
            shard = directory / "part.safetensors"
            outside = Path(root) / "outside"
            shard.replace(outside)
            shard.symlink_to(outside)
            with self.assertRaisesRegex(ValueError, "Unsafe"):
                validate_model(root, policy)

    def test_cached_image_skips_pull_but_force_refreshes(self):
        policy = profile("b300-tp4")
        image = {
            "Id": "sha256:cached",
            "Architecture": "amd64",
            "Os": "linux",
            "RootFS": {},
            "Config": {},
        }
        with tempfile.TemporaryDirectory() as root:
            with (
                patch("local_ai.images.inspect_image", return_value=image),
                patch(
                    "local_ai.images.download_command",
                    return_value=subprocess.CompletedProcess([], 0),
                ) as download,
            ):
                result = images.pull(root, policy)
                self.assertFalse(result["network"])
                download.assert_not_called()
                result = images.pull(root, policy, force=True)
                self.assertTrue(result["network"])
                download.assert_called_once()

    def test_imported_image_lock_reuses_local_id_without_registry(self):
        policy = profile("b300-tp4")
        image = {
            "Id": "sha256:cached",
            "Architecture": "amd64",
            "Os": "linux",
            "RootFS": {},
            "Config": {},
        }
        with tempfile.TemporaryDirectory() as root:
            lock = {
                "reference": policy["image"],
                "platform": policy["platform"],
                "id": image["Id"],
                "tag": "local-export",
                "content_identity": images.image_identity(image),
            }
            atomic_json(images.lock_path(root, policy), lock)
            with (
                patch(
                    "local_ai.images.inspect_image",
                    side_effect=lambda ref, platform: image if ref == image["Id"] else None,
                ),
                patch(
                    "local_ai.images.download_command", side_effect=AssertionError("no registry")
                ),
            ):
                self.assertFalse(images.pull(root, policy)["network"])

    def test_wrong_platform_cache_is_rejected(self):
        policy = profile("b300-tp4")
        image = {"Id": "sha256:wrong", "Architecture": "arm64", "Os": "linux"}
        with (
            tempfile.TemporaryDirectory() as root,
            patch("local_ai.images.inspect_image", return_value=image),
        ):
            with self.assertRaisesRegex(ValueError, "architecture"):
                images.pull(root, policy)

    def test_invalid_index_object_has_clear_error(self):
        with tempfile.TemporaryDirectory() as root:
            policy, directory = model_fixture(root)
            (directory / "model.safetensors.index.json").write_text("[]")
            with self.assertRaises(ValueError):
                validate_model(root, policy)

    def test_stale_lock_with_no_image_fetches_instead_of_claiming_conflict(self):
        policy = profile("b300-tp4")
        image = {
            "Id": "sha256:new",
            "Architecture": "amd64",
            "Os": "linux",
            "RootFS": {},
            "Config": {},
        }
        with tempfile.TemporaryDirectory() as root:
            atomic_json(
                images.lock_path(root, policy),
                {
                    "reference": policy["image"],
                    "platform": policy["platform"],
                    "id": "sha256:gone",
                    "tag": "missing-tag",
                    "content_identity": "old",
                },
            )
            with (
                patch("local_ai.images.inspect_image", side_effect=[None, None, None, None, image]),
                patch(
                    "local_ai.images.download_command",
                    return_value=subprocess.CompletedProcess([], 0),
                ) as download,
            ):
                result = images.pull(root, policy)
            self.assertTrue(result["network"])
            download.assert_called_once()


class InstallationLogTests(unittest.TestCase):
    def test_stdout_stderr_command_and_timing_share_one_file(self):
        with tempfile.TemporaryDirectory() as root:
            with installlog.session(options(root)):
                result = run(
                    [
                        sys.executable,
                        "-c",
                        "import sys; print('hello'); print('detail',file=sys.stderr)",
                    ]
                )
            self.assertEqual(result.stdout, "hello\n")
            self.assertEqual(result.stderr, "detail\n")
            log = Path(root) / "install.log"
            text = log.read_text()
            for value in [
                "BEGIN",
                "command=",
                "STDOUT hello",
                "STDERR detail",
                "elapsed=",
                "exit=0",
                "DONE image pull",
            ]:
                self.assertIn(value, text)
            self.assertEqual(log.stat().st_mode & 0o777, 0o600)

    def test_failure_retains_exit_code_error_and_traceback(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(RuntimeError):
                with installlog.session(options(root)):
                    run(
                        [
                            sys.executable,
                            "-c",
                            "import sys; print('broken',file=sys.stderr); sys.exit(7)",
                        ]
                    )
            text = (Path(root) / "install.log").read_text()
            for value in ["exit=7", "STDERR broken", "FAIL image pull", "TRACEBACK"]:
                self.assertIn(value, text)

    def test_timeout_is_logged_and_process_is_reaped(self):
        with tempfile.TemporaryDirectory() as root:
            with self.assertRaises(subprocess.TimeoutExpired):
                with installlog.session(options(root)):
                    run(
                        [
                            sys.executable,
                            "-c",
                            "import time; print('started',flush=True); time.sleep(2)",
                        ],
                        timeout=0.05,
                    )
            text = (Path(root) / "install.log").read_text()
            self.assertIn("TimeoutExpired", text)
            self.assertIn("STDOUT started", text)

    def test_plan_does_not_create_log_or_directories(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "absent"
            args = argparse.Namespace(
                group="server", action="plan", data_dir=root, install_log=root / "custom.log"
            )
            with installlog.session(args):
                self.assertFalse(installlog.active())
            self.assertFalse(root.exists())

    def test_cli_plan_with_log_option_still_writes_nothing(self):
        import contextlib
        import io

        from local_ai.cli import main

        fixture = Path(__file__).parent / "fixtures/b300-tp4.json"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "absent"
            with contextlib.redirect_stdout(io.StringIO()):
                code = main(
                    [
                        "--install-log",
                        str(root / "install.log"),
                        "server",
                        "plan",
                        "--inventory",
                        str(fixture),
                        "--gpus",
                        "0,1,2,3",
                        "--data-dir",
                        str(root),
                    ]
                )
            self.assertEqual(code, 0)
            self.assertFalse(root.exists())

    def test_json_stdout_stays_machine_readable_with_install_progress(self):
        import contextlib
        import io

        from local_ai.cli import main

        with tempfile.TemporaryDirectory() as root:
            model_fixture(root)
            output, progress = io.StringIO(), io.StringIO()
            with contextlib.redirect_stdout(output), contextlib.redirect_stderr(progress):
                code = main(["model", "download", "--data-dir", root])
            self.assertEqual(code, 0)
            self.assertFalse(json.loads(output.getvalue())["network"])
            self.assertIn("REUSE", progress.getvalue())


class DocumentationContractTests(unittest.TestCase):
    def test_all_commands_and_long_options_have_manual_entries(self):
        from local_ai.cli import parser

        manuals = [
            Path(__file__).parents[1] / "docs" / p for p in ["commands.md", "en/commands.md"]
        ]
        texts = [p.read_text() for p in manuals]

        def visit(current, path):
            children = [a for a in current._actions if isinstance(a, argparse._SubParsersAction)]
            for action in current._actions:
                for option in action.option_strings:
                    if option.startswith("--"):
                        self.assertIsNotNone(action.help, (path, option))
                        for text in texts:
                            self.assertIn(option, text)
            if children:
                for name, child in children[0].choices.items():
                    visit(child, path + [name])
            else:
                for text in texts:
                    self.assertIn(" ".join(path), text)

        visit(parser(), [])

    def test_docker_export_temp_file_is_visible_in_progress(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "image.tar"
            temporary = Path(directory) / ".tmp-image.tar123"
            temporary.write_bytes(b"test-data")
            progress = installlog.artifact_progress(
                ["docker", "image", "save", "--output", str(output)]
            )
            self.assertIn(str(temporary), progress)
            self.assertIn("output_bytes=9", progress)

    def test_progress_file_disappearance_does_not_fail_installation(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "image.tar"
            with patch("local_ai.installlog.Path.stat", side_effect=FileNotFoundError):
                result = installlog.artifact_progress(["docker", "--output", str(output)])
            self.assertIsInstance(result, str)

    def test_documentation_links_shell_syntax_and_cli_examples(self):
        import contextlib
        import io
        import re
        import shlex
        from urllib.parse import unquote, urlsplit

        from local_ai.cli import parser

        root = Path(__file__).parents[1]
        files = [
            root / "README.md",
            root / "README.en.md",
            root / "AGENTS.md",
            *sorted((root / "docs").rglob("*.md")),
        ]
        for path in files:
            text = path.read_text()
            self.assertEqual(text.count("```") % 2, 0, path)
            for link in re.findall(r"\[[^\]]*\]\(([^)]+)\)", text):
                url = urlsplit(link)
                if not url.scheme and url.path:
                    self.assertTrue((path.parent / unquote(url.path)).exists(), (path, link))
            for block in re.findall(r"```bash\n(.*?)```", text, re.S):
                checked = subprocess.run(
                    ["/bin/bash", "-n"], input=block, text=True, capture_output=True
                )
                self.assertEqual(checked.returncode, 0, (path, checked.stderr))
                for line in block.replace(chr(92) + chr(10), " ").splitlines():
                    if line.strip().startswith("./local-ai "):
                        with (
                            contextlib.redirect_stdout(io.StringIO()),
                            contextlib.redirect_stderr(io.StringIO()),
                        ):
                            try:
                                parser().parse_args(shlex.split(line.strip(), comments=True)[1:])
                            except SystemExit as error:
                                self.assertEqual(error.code, 0, (path, line))

    def test_nonregular_log_path_is_rejected_without_blocking(self):
        import os

        with tempfile.TemporaryDirectory() as directory:
            fifo = Path(directory) / "log-pipe"
            os.mkfifo(fifo)
            mode = fifo.stat().st_mode
            with self.assertRaisesRegex(ValueError, "regular file"):
                installlog.Journal(fifo)
            self.assertEqual(fifo.stat().st_mode, mode)
