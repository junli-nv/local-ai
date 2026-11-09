import copy
import hashlib
import io
import json
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

from local_ai import bundle, deployment, images, server
from local_ai.cli import main, parser
from local_ai.completion import candidates
from local_ai.profiles import (
    catalog,
    deployment_blockers,
    engine_args,
    profile,
    require_deployable,
    select_gpus,
)


class NextPlatformTests(unittest.TestCase):
    def test_v133_catalog_entries_remain_identical(self):
        original = copy.deepcopy(catalog())
        original.pop("model", None)
        for name in ("gb200-tp4", "rubin-tp2-framework"):
            original["profiles"].pop(name)
        digest = hashlib.sha256(json.dumps(original, sort_keys=True).encode()).hexdigest()
        self.assertEqual(digest, "159a03ceabb7b606407641f8af16a133176e11ef0af8ce39025e335f4cdf895c")

    def setUp(self):
        fixtures = Path(__file__).parent / "fixtures"
        self.gb200 = json.loads((fixtures / "gb200-tp4.json").read_text())
        self.rubin = json.loads((fixtures / "rubin-tp2.json").read_text())

    def test_gb200_uses_arm_image_and_b200_engine_baseline(self):
        policy = profile("gb200-tp4")
        self.assertEqual(
            (policy["arch"], policy["platform"], policy["tp"]), ("arm64", "linux/arm64", 4)
        )
        self.assertEqual(policy["platform_digest"], profile("gb300-tp4")["platform_digest"])
        self.assertEqual(engine_args(policy, 18000), engine_args(profile("b200-tp4"), 18000))
        self.assertEqual(policy["validation"], "experimental-no-local-hardware")
        self.assertEqual(deployment_blockers(policy), [])

    def test_gb200_selection_preserves_uuid_order_and_accepts_reported_b200_name(self):
        self.assertTrue(self.gb200["synthetic"])
        self.gb200["gpus"][0]["name"] = "NVIDIA B200"
        selected = select_gpus(self.gb200, "3,0,2,1", profile("gb200-tp4"))
        self.assertEqual([g["index"] for g in selected], [3, 0, 2, 1])

    def test_gb200_rejects_bad_card_count_duplicates_and_missing_devices(self):
        for selectors in ("0,1", "0,1,2,3,4", "0,1,2,99", "0,1,2,GPU-gb200-tp4-synthetic-0"):
            with self.subTest(selectors=selectors), self.assertRaises(ValueError):
                select_gpus(self.gb200, selectors, profile("gb200-tp4"))

    def test_gb200_rejects_wrong_cpu_gpu_and_low_hbm(self):
        for field, value, message in (
            ("arch", "amd64", "CPU architecture"),
            ("name", "NVIDIA GB300", "GPU model"),
            ("memory_mib", 179999, "less HBM"),
        ):
            hardware = copy.deepcopy(self.gb200)
            if field == "arch":
                hardware[field] = value
            else:
                hardware["gpus"][0][field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                select_gpus(hardware, "0,1,2,3", profile("gb200-tp4"))
        self.gb200["gpus"][0]["memory_mib"] = 180000
        self.assertEqual(len(select_gpus(self.gb200, "0,1,2,3", profile("gb200-tp4"))), 4)

    def test_gb200_image_platform_is_checked(self):
        with self.assertRaisesRegex(ValueError, "architecture"):
            images.validate_image({"Os": "linux", "Architecture": "amd64"}, profile("gb200-tp4"))

    def test_new_plans_are_pure_and_framework_is_not_executable(self):
        policies = [profile("gb200-tp4"), profile("rubin-tp2-framework")]
        original_open = Path.open

        def read_only(path, mode="r", *args, **kwargs):
            if any(flag in mode for flag in "wax+"):
                raise AssertionError("file write")
            return original_open(path, mode, *args, **kwargs)

        with tempfile.TemporaryDirectory() as directory:
            target = Path(directory) / "absent"
            with (
                patch("subprocess.run", side_effect=AssertionError("subprocess")),
                patch("pathlib.Path.mkdir", side_effect=AssertionError("mkdir")),
                patch("pathlib.Path.open", new=read_only),
            ):
                gb = server.plan(target, policies[0], "0,1,2,3", "a", 18000, self.gb200)
                rb = server.plan(target, policies[1], "0,1", "a", 18000, self.rubin)
            self.assertFalse(target.exists())
        self.assertTrue(gb["deployable"])
        self.assertEqual(gb["command"].count("--device"), 4)
        self.assertIn("linux/arm64", gb["command"])
        self.assertFalse(rb["deployable"])
        for value in (rb["command"], rb["spec"]["image"], rb["spec"]["args"]):
            self.assertIsNone(value)
        self.assertEqual(len(rb["blockers"]), 4)
        self.assertTrue(self.rubin["synthetic"])
        self.assertEqual(policies[1]["tp"], 2)
        self.assertTrue(policies[1]["engine_options"]["--engram-config"]["cpu_offload"])
        self.assertEqual(policies[1]["nominal_vram_gb"], 288)
        self.assertEqual(policies[1]["min_host_available_gib"], 256)

    def test_framework_still_checks_cpu_card_count_and_gpu_family(self):
        policy = profile("rubin-tp2-framework")
        with self.assertRaises(ValueError):
            select_gpus(self.rubin, "0", policy)
        self.rubin["arch"] = "amd64"
        with self.assertRaisesRegex(ValueError, "CPU architecture"):
            select_gpus(self.rubin, "0,1", policy)
        self.rubin["arch"] = "arm64"
        self.rubin["gpus"][0]["name"] = "NVIDIA GB300"
        with self.assertRaisesRegex(ValueError, "GPU model"):
            select_gpus(self.rubin, "0,1", policy)

    def test_clearing_framework_flag_alone_does_not_enable_deployment(self):
        policy = profile("rubin-tp2-framework")
        policy["planning_only"] = False
        with self.assertRaisesRegex(ValueError, "image is unresolved"):
            require_deployable(policy)
        with self.assertRaisesRegex(ValueError, "min_vram_mib is unresolved"):
            select_gpus(self.rubin, "0,1", policy)

    def test_filling_image_alone_does_not_enable_framework(self):
        policy = profile("rubin-tp2-framework")
        for key in ("image", "image_tag", "platform_digest", "min_vram_mib"):
            policy[key] = profile("gb200-tp4")[key]
        with self.assertRaisesRegex(ValueError, "planning_only"):
            require_deployable(policy)

    def test_framework_cli_rejects_mutations_before_logging_or_hardware_probes(self):
        commands = [
            ["install", "--role", "server"],
            ["install", "--role", "both"],
            ["server", "start", "--gpus", "0,1"],
            ["image", "pull"],
            ["image", "pull", "--force"],
            ["image", "export", "--output", "never.tar"],
            ["image", "import", "--archive", "absent.tar", "--lock", "absent.json"],
            ["model", "download"],
            ["export"],
        ]
        with (
            patch("local_ai.installlog.session", side_effect=AssertionError("journal")),
            patch("local_ai.server.inventory", side_effect=AssertionError("hardware")),
            patch("subprocess.run", side_effect=AssertionError("subprocess")),
            patch("pathlib.Path.mkdir", side_effect=AssertionError("mkdir")),
        ):
            for command in commands:
                with (
                    self.subTest(command=command),
                    redirect_stdout(io.StringIO()) as out,
                    redirect_stderr(io.StringIO()) as err,
                ):
                    self.assertEqual(main([*command, "--profile", "rubin-tp2-framework"]), 1)
                    self.assertEqual(out.getvalue(), "")
                    self.assertIn("not deployable", err.getvalue())

    def test_framework_library_operations_also_refuse_before_side_effects(self):
        policy = profile("rubin-tp2-framework")
        options = parser().parse_args(["install", "--role", "server", "--profile", policy["name"]])
        export = parser().parse_args(["export", "--profile", policy["name"]])
        calls = [
            lambda: images.resolve_image("absent", policy),
            lambda: images.pull("absent", policy, force=True),
            lambda: images.export_image("absent", policy, "never.tar"),
            lambda: images.import_image("absent", policy, "absent.tar", "absent.json"),
            lambda: images.download_model("absent", policy),
            lambda: deployment.ensure_archive("absent", policy),
            lambda: deployment.install(options),
            lambda: bundle.export(export),
            lambda: server.start({}, policy),
        ]
        with (
            patch("subprocess.run", side_effect=AssertionError("subprocess")),
            patch("pathlib.Path.mkdir", side_effect=AssertionError("mkdir")),
            patch("local_ai.server.validate_model", side_effect=AssertionError("model read")),
        ):
            for index, operation in enumerate(calls):
                with (
                    self.subTest(index=index),
                    self.assertRaisesRegex(ValueError, "not deployable"),
                ):
                    operation()

    def test_new_profiles_are_exposed_to_help_and_completion(self):
        for name in ("gb200-tp4", "rubin-tp2-framework"):
            self.assertIn(
                name,
                parser().format_help()
                + parser()._subparsers._group_actions[0].choices["install"].format_help(),
            )
            self.assertIn(name, candidates(parser(), ["server", "plan", "--profile", ""])[1])
