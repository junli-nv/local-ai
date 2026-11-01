import copy
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_ai.client import config
from local_ai.common import atomic_json
from local_ai.images import cached_model
from local_ai.profiles import catalog, engine_args, profile
from local_ai.server import plan


class ModelCatalogTests(unittest.TestCase):
    def test_external_model_recipe_does_not_inherit_deepseek_engine_or_client_options(self):
        data = catalog()
        other = copy.deepcopy(data["models"][data["default_model"]])
        other.update(
            repo="example/OtherModel",
            revision="new-revision",
            model_directory="OtherModel-new",
            served_name="OtherModel",
            engine_options={"--max-model-len": 8192, "--enable-auto-tool-choice": True},
            environment={},
            client={"limit": {"context": 8192, "output": 1024}},
        )
        data["models"]["other"] = other
        data["default_model"] = "other"
        data.pop("model")
        data["profiles"]["other-tp4"] = {
            **data["profiles"]["b300-tp4"],
            "model": "other",
            "validation": "custom-unvalidated",
        }
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "catalog.json"
            atomic_json(path, data)
            with patch.dict(os.environ, {"LOCAL_AI_CATALOG": str(path)}):
                policy = profile("other-tp4")
                args = engine_args(policy, 18000)
                self.assertIn("/models/OtherModel-new", args)
                self.assertNotIn("--engram-config", args)
                self.assertNotIn("--tokenizer-mode", args)
                self.assertNotIn("deepseek_v41", args)
                self.assertEqual(catalog()["model"]["served_name"], "OtherModel")
                model = config("http://gpu:18000/v1", "OtherModel")["provider"]["local-deepseek"][
                    "models"
                ]["OtherModel"]
                self.assertNotIn("interleaved", model)
                self.assertEqual(model["limit"]["context"], 8192)

    def test_revision_locks_belong_to_each_model_directory(self):
        first = profile("b300-tp4")
        second = {**first, "repo": "example/Other", "revision": "other", "model_directory": "Other"}
        with tempfile.TemporaryDirectory() as root:
            for policy in [first, second]:
                model = Path(root) / "models" / policy["model_directory"]
                model.mkdir(parents=True)
                atomic_json(
                    model / "model.lock.json",
                    {"repo": policy["repo"], "revision": policy["revision"]},
                )
            with patch("local_ai.server.validate_model"):
                self.assertTrue(cached_model(root, first)["revision_verified"])
                self.assertTrue(cached_model(root, second)["revision_verified"])
                with self.assertRaisesRegex(ValueError, "revision conflicts"):
                    cached_model(root, {**second, "revision": "different"})

    def test_unknown_api_model_has_no_deepseek_specific_metadata(self):
        model = config("http://gpu:18000/v1", "external-model")["provider"]["local-deepseek"][
            "models"
        ]["external-model"]
        self.assertNotIn("interleaved", model)
        self.assertNotIn("limit", model)

    def test_recipe_cannot_override_managed_listener(self):
        policy = profile("b300-tp4")
        policy["engine_options"] = {"--host": "0.0.0.0"}
        with self.assertRaisesRegex(ValueError, "reserved engine option"):
            engine_args(policy, 18000)

    def test_engine_environment_changes_instance_identity(self):
        fixture = Path(__file__).parent / "fixtures/b300-tp4.json"
        hardware = json.loads(fixture.read_text())
        policy = profile("b300-tp4")
        original = plan("/tmp/local-ai-test", policy, "0,1,2,3", "a", 18000, hardware)
        changed = plan(
            "/tmp/local-ai-test", {**policy, "environment": {}}, "0,1,2,3", "a", 18000, hardware
        )
        self.assertNotIn("environment", original["spec"])
        self.assertIn("environment", changed["spec"])
        self.assertNotEqual(original["spec"], changed["spec"])

    def test_new_revision_changes_identity_even_with_the_same_directory(self):
        hardware = json.loads((Path(__file__).parent / "fixtures/b300-tp4.json").read_text())
        policy = profile("b300-tp4")
        original = plan("/tmp/local-ai-test", policy, "0,1,2,3", "a", 18000, hardware)
        changed = plan(
            "/tmp/local-ai-test", {**policy, "revision": "new"}, "0,1,2,3", "a", 18000, hardware
        )
        self.assertNotIn("model_identity", original["spec"])
        self.assertEqual(changed["spec"]["model_identity"]["revision"], "new")
        self.assertNotEqual(original["spec"], changed["spec"])
