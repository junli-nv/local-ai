import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_ai.common import arch, atomic_json
from local_ai.images import image_identity, resolve_image, validate_image
from local_ai.profiles import engine_args, profile, select_gpus
from local_ai.server import conflicts, plan, validate_model


def hardware(cpu="amd64", count=8):
    return {
        "arch": cpu,
        "gpus": [
            {
                "index": i,
                "uuid": "GPU-test-%d" % i,
                "name": "NVIDIA B300" if cpu == "amd64" else "NVIDIA GB300",
                "memory_mib": 275040,
                "pci": "0000:%02x:00.0" % i,
            }
            for i in range(count)
        ],
    }


class PlatformTests(unittest.TestCase):
    def test_aliases(self):
        self.assertEqual(arch("x86_64"), "amd64")
        self.assertEqual(arch("aarch64"), "arm64")
        with self.assertRaises(ValueError):
            arch("unknown")

    def test_noncontiguous_selection_preserves_uuid_order(self):
        result = select_gpus(hardware(), "7,1,5,3", profile("b300-tp4"))
        self.assertEqual(
            [g["uuid"] for g in result], ["GPU-test-7", "GPU-test-1", "GPU-test-5", "GPU-test-3"]
        )

    def test_duplicate_gpu_is_rejected(self):
        with self.assertRaises(ValueError):
            select_gpus(hardware(), "0,GPU-test-0,2,3", profile("b300-tp4"))

    def test_wrong_cpu_and_missing_gpu_rejected(self):
        with self.assertRaises(ValueError):
            select_gpus(hardware(), "0,1,2,3", profile("gb300-tp4"))
        with self.assertRaises(ValueError):
            select_gpus(hardware(), "0,1,2,99", profile("b300-tp4"))

    def test_low_hbm_rejected(self):
        value = hardware()
        value["gpus"][0]["memory_mib"] = 140000
        with self.assertRaises(ValueError):
            select_gpus(value, "0,1,2,3", profile("b300-tp4"))

    def test_gb300_two_gpu_offloads_engram(self):
        policy = profile("gb300-tp2")
        selected = select_gpus(hardware("arm64", 2), "0,1", policy)
        args = engine_args(policy, 18001)
        self.assertEqual(len(selected), 2)
        self.assertTrue(json.loads(args[args.index("--engram-config") + 1])["cpu_offload"])
        self.assertNotIn("hardware-verified", policy["validation"])

    def test_plan_is_pure_and_platform_specific(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "absent"
            with patch(
                "local_ai.common.subprocess.run",
                side_effect=AssertionError("no subprocess allowed"),
            ):
                value = plan(
                    root, profile("gb300-tp4"), "0,1,2,3", "a", 18000, hardware("arm64", 4)
                )
            self.assertFalse(root.exists())
            args = value["command"]
            self.assertEqual(args[args.index("--platform") + 1], "linux/arm64")
            self.assertEqual(args.count("--device"), 4)
            compile(args[-1], "<entry>", "exec")

    def test_conflicts_ignore_unselected_busy_gpu(self):
        spec = {"gpus": ["GPU-test-4"], "port": 18001}
        conflicts(spec, [], [["GPU-test-0", "123"]])
        with self.assertRaises(RuntimeError):
            conflicts(spec, [], [["GPU-test-4", "123"]])
        container = {
            "Name": "/other",
            "State": {"Running": True},
            "Config": {"Labels": {"local-ai.port": "18001"}},
        }
        with self.assertRaises(RuntimeError):
            conflicts(spec, [container], [])

    def test_image_fingerprint_covers_config_and_layers(self):
        image = {
            "Architecture": "arm64",
            "Os": "linux",
            "RootFS": {"Layers": ["sha256:a"]},
            "Config": {"Env": ["A=1"]},
        }
        changed = copy.deepcopy(image)
        changed["Config"]["Env"] = ["A=2"]
        self.assertNotEqual(image_identity(image), image_identity(changed))
        validate_image(image, profile("gb300-tp4"))
        with self.assertRaises(ValueError):
            validate_image(image, profile("b300-tp4"))

    def test_offline_import_cannot_use_a_same_named_wrong_image(self):
        policy = profile("b300-tp4")
        with tempfile.TemporaryDirectory() as root:
            atomic_json(
                Path(root) / "images/amd64.lock.json",
                {
                    "reference": policy["image"],
                    "platform": policy["platform"],
                    "id": "sha256:x",
                    "tag": "local:tag",
                    "content_identity": "not-matching",
                },
            )
            image = {"Architecture": "amd64", "Os": "linux", "RootFS": {}, "Config": {}}
            with patch("local_ai.images.inspect_image", side_effect=[None, image, image]):
                with self.assertRaises(RuntimeError):
                    resolve_image(root, policy)

    def test_weight_index_traversal_rejected(self):
        policy = profile("b300-tp4")
        with tempfile.TemporaryDirectory() as root:
            model = Path(root) / "models" / policy["model_directory"]
            model.mkdir(parents=True)
            for name in ["config.json", "tokenizer.json"]:
                (model / name).write_text("{}")
            (model / "model.safetensors.index.json").write_text(
                json.dumps({"weight_map": {"x": "../../outside"}})
            )
            with self.assertRaises(ValueError):
                validate_model(root, policy)

    def test_cpu_offload_host_memory_guard(self):
        from local_ai.server import check_host_memory

        check_host_memory(profile("b300-tp4"), available_gib=8)
        check_host_memory(profile("gb300-tp2"), available_gib=512)
        with self.assertRaises(ValueError):
            check_host_memory(profile("gb300-tp2"), available_gib=192)

    def test_inspection_selects_arm64_even_on_an_amd64_preparation_host(self):
        from types import SimpleNamespace

        from local_ai.images import inspect_image

        def docker(command, **kwargs):
            platform = (
                command[command.index("--platform") + 1]
                if "--platform" in command
                else "linux/amd64"
            )
            return SimpleNamespace(
                returncode=0,
                stdout=json.dumps([{"Os": "linux", "Architecture": platform.split("/")[1]}]),
            )

        with patch("local_ai.images.run", side_effect=docker):
            value = inspect_image("repo@sha256:example", "linux/arm64")
        validate_image(value, profile("gb300-tp4"))
