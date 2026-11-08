import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_ai.profiles import catalog, client_options, profile, select_gpus
from local_ai.server import check_host_memory, plan


class RTX6000DTests(unittest.TestCase):
    def test_original_catalog_is_unchanged(self):
        value = copy.deepcopy(catalog())
        value.pop("model", None)
        value["profiles"].pop("rtx6000d-tp8")
        value["models"].pop("deepseek-v4.1-flash-sm120")
        actual = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
        self.assertEqual(actual, "d8002bb16d9f7fbb7bb8d0a7a8d61dff5a9610de546b54d809ee0cb3f77600f3")

    def test_plan_and_client_are_isolated(self):
        policy = profile("rtx6000d-tp8")
        fixture = json.loads((Path(__file__).parent / "fixtures/rtx6000d-tp8.json").read_text())
        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "absent"
            with patch("local_ai.common.subprocess.run", side_effect=AssertionError):
                result = plan(target, policy, "0,1,2,3,4,5,6,7", "rtx", 18000, fixture)
            self.assertFalse(target.exists())
        self.assertEqual(result["command"].count("--device"), 8)
        args = result["spec"]["args"]
        attention = json.loads(args[args.index("--attention-config") + 1])
        self.assertEqual(attention["indexer_kv_dtype"], "fp8")
        self.assertNotIn("indexer_sparse_logits", attention)
        self.assertNotIn("--speculative-config", args)
        self.assertIn("--enforce-eager", args)
        options = client_options(policy["served_name"])
        self.assertEqual(options["limit"]["context"], 32768)
        self.assertEqual(options["modalities"]["input"], ["text"])
        self.assertEqual(options["interleaved"]["field"], "reasoning")
        self.assertEqual(policy["validation"], "experimental-hardware-validated-api-smoke")

    def test_wrong_resources_rejected(self):
        policy = profile("rtx6000d-tp8")
        fixture = json.loads((Path(__file__).parent / "fixtures/rtx6000d-tp8.json").read_text())
        for selectors in ["0,1,2,3", "0,1,2,3,4,5,6,6", "0,1,2,3,4,5,6,99"]:
            with self.subTest(selectors=selectors), self.assertRaises(ValueError):
                select_gpus(fixture, selectors, policy)
        for field, value in [("name", "NVIDIA B300"), ("memory_mib", 80000)]:
            bad = copy.deepcopy(fixture)
            bad["gpus"][0][field] = value
            with self.subTest(field=field), self.assertRaises(ValueError):
                select_gpus(bad, "0,1,2,3,4,5,6,7", policy)
        bad = copy.deepcopy(fixture)
        bad["arch"] = "arm64"
        with self.assertRaises(ValueError):
            select_gpus(bad, "0,1,2,3,4,5,6,7", policy)
        with self.assertRaises(ValueError):
            check_host_memory(policy, available_gib=128)
        check_host_memory(policy, available_gib=256)
