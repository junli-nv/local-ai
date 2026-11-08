import json
import tempfile
import unittest
from pathlib import Path

from local_ai.client import config, prepare
from local_ai.profiles import engine_args, profile


class ReasoningTests(unittest.TestCase):
    def test_default_keeps_model_behavior_and_server_args(self):
        cfg = config("http://GPU001:18000/v1", "DeepSeek-V4.1-Flash")
        model = cfg["provider"]["local-deepseek"]["models"]["DeepSeek-V4.1-Flash"]
        self.assertEqual(model["variants"]["normal"], {})
        self.assertNotIn("default", model["variants"])
        self.assertNotIn("options", model)
        self.assertNotIn("variant", cfg)
        self.assertTrue(model["reasoning"])
        self.assertEqual(model["interleaved"], {"field": "reasoning_content"})
        self.assertEqual(model["limit"], {"context": 131072, "output": 32768})
        for name in ("b200-tp4", "b200-tp4-cpu", "b300-tp4"):
            args = engine_args(profile(name), 18000)
            self.assertNotIn("chat_template_kwargs", " ".join(args))
            self.assertNotIn("reasoning_effort", " ".join(args))

    def test_switches_are_available_in_each_invocation_config(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            state, assets = root / "state", root / "assets"
            state.mkdir()
            (assets / "seed-cache").mkdir(parents=True)
            for name in ("first", "resumed"):
                session = state / name
                session.mkdir()
                env = prepare(
                    state, assets, session, "http://GPU001:18000/v1", "DeepSeek-V4.1-Flash", root
                )
                file_cfg = json.loads(Path(env["OPENCODE_CONFIG"]).read_text())
                self.assertEqual(file_cfg, json.loads(env["OPENCODE_CONFIG_CONTENT"]))
                model = file_cfg["provider"]["local-deepseek"]["models"]["DeepSeek-V4.1-Flash"]
                self.assertEqual(
                    [key for key, value in model["variants"].items() if not value.get("disabled")],
                    ["normal", "low", "high", "xhigh", "max", "none"],
                )
                self.assertEqual(
                    model["variants"]["none"]["chat_template_kwargs"], {"thinking": False}
                )
                self.assertNotIn("options", model)

    def test_other_models_do_not_inherit_deepseek_controls(self):
        cfg = config("http://GPU001:18000/v1", "another-model")
        self.assertNotIn("variants", cfg["provider"]["local-deepseek"]["models"]["another-model"])
        custom = {"reasoning": True, "variants": {"custom": {"reasoningEffort": "low"}}}
        cfg = config("http://GPU001:18000/v1", "another-model", custom)
        self.assertEqual(
            cfg["provider"]["local-deepseek"]["models"]["another-model"]["variants"],
            custom["variants"],
        )
