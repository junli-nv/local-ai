import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_ai.profiles import engine_args, profile, select_gpus
from local_ai.server import check_host_memory, plan


class B200Tests(unittest.TestCase):
    def setUp(self):
        path = Path(__file__).parent / "fixtures/b200-tp4.json"
        self.hardware = json.loads(path.read_text())

    def test_profiles_and_order(self):
        for name in ("b200-tp4", "b200-tp4-cpu"):
            policy = profile(name)
            selected = select_gpus(self.hardware, "6,3,5,4", policy)
            self.assertEqual([g["index"] for g in selected], [6, 3, 5, 4])
            self.assertEqual(policy["validation"], "hardware-validated-api-smoke")
            for key in ("image", "platform_digest", "repo", "revision", "platform"):
                self.assertEqual(policy[key], profile("b300-tp4")[key])

    def test_bad_selection(self):
        for value in ("3,4,5", "3,4,5,2", "3,GPU-b200-test-3,5,6"):
            with self.subTest(value=value), self.assertRaises(ValueError):
                select_gpus(self.hardware, value, profile("b200-tp4"))

    def test_hbm_boundary(self):
        policy = profile("b200-tp4")
        self.hardware["gpus"][0]["memory_mib"] = 179999
        with self.assertRaisesRegex(ValueError, "less HBM"):
            select_gpus(self.hardware, "3,4,5,6", policy)
        self.hardware["gpus"][0]["memory_mib"] = 180000
        self.assertEqual(len(select_gpus(self.hardware, "3,4,5,6", policy)), 4)

    def test_wrong_cpu_and_model(self):
        self.hardware["arch"] = "arm64"
        with self.assertRaises(ValueError):
            select_gpus(self.hardware, "3,4,5,6", profile("b200-tp4"))
        self.hardware["arch"] = "amd64"
        self.hardware["gpus"][0]["name"] = "NVIDIA B300"
        with self.assertRaisesRegex(ValueError, "GPU model"):
            select_gpus(self.hardware, "3,4,5,6", profile("b200-tp4"))

    def test_only_engram_placement_changes(self):
        gpu = engine_args(profile("b200-tp4"), 18000)
        cpu = engine_args(profile("b200-tp4-cpu"), 18000)
        index = gpu.index("--engram-config") + 1
        self.assertFalse(json.loads(gpu[index])["cpu_offload"])
        self.assertTrue(json.loads(cpu[index])["cpu_offload"])
        cpu[index] = gpu[index]
        self.assertEqual(cpu, gpu)

    def test_host_memory(self):
        check_host_memory(profile("b200-tp4"), available_gib=8)
        check_host_memory(profile("b200-tp4-cpu"), available_gib=256)
        with self.assertRaises(ValueError):
            check_host_memory(profile("b200-tp4-cpu"), available_gib=255)

    def test_pure_plan(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "absent"
            with patch("local_ai.common.subprocess.run", side_effect=AssertionError("no command")):
                for name in ("b200-tp4", "b200-tp4-cpu"):
                    result = plan(root, profile(name), "3,4,5,6", "a", 18000, self.hardware)
                    self.assertEqual(result["command"].count("--device"), 4)
            self.assertFalse(root.exists())
