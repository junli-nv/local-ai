import importlib.util
import json
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "steering_probe", Path(__file__).parents[1] / "scripts/check-steering.py"
)
probe = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(probe)


class SteeringProbeTests(unittest.TestCase):
    def events(self):
        return {
            "tool_started": 1,
            "follow_up_submitted": 2,
            "follow_up_persisted_observed": 3,
            "follow_up_in_model_request": 4,
            "tool_finished": 5,
            "ack_persisted_observed": 6,
        }

    def test_distinguishes_receipt_from_model_delivery(self):
        events = self.events()
        self.assertEqual(probe.classify(events), "during_tool")
        events["follow_up_in_model_request"] = 7
        events["ack_persisted_observed"] = 8
        self.assertEqual(probe.classify(events), "after_tool")

    def test_missing_or_invalid_evidence_cannot_count_as_responsive(self):
        for key in self.events():
            events = self.events()
            events[key] = None
            with self.subTest(key=key), self.assertRaisesRegex(ValueError, "Incomplete"):
                probe.classify(events)
        for changed in (
            {"follow_up_submitted": 0},
            {"follow_up_submitted": 8},
            {"follow_up_in_model_request": 0},
        ):
            with self.subTest(changed=changed), self.assertRaises(ValueError):
                probe.classify({**self.events(), **changed})

    def test_title_requests_do_not_count_as_model_delivery(self):
        with tempfile.TemporaryDirectory() as folder:
            model = probe.Model(Path(folder), 0.01)
            payload = {"messages": [{"role": "user", "content": probe.FOLLOWUP}]}
            model.reply(payload)
            self.assertIsNone(model.delivered)
            model.reply({**payload, "tools": [{"function": {"name": "bash"}}]})
            self.assertIsNotNone(model.delivered)

    def test_mock_issues_shell_command_once_then_acknowledges_followup(self):
        with tempfile.TemporaryDirectory() as folder:
            model = probe.Model(Path(folder), 0.01)
            payload = {
                "messages": [{"role": "user", "content": probe.INITIAL}],
                "tools": [{"function": {"name": "bash"}}],
            }
            delta, reason = model.reply(payload)
            self.assertEqual(reason, "tool_calls")
            self.assertEqual(delta["tool_calls"][0]["function"]["name"], "bash")
            self.assertEqual(model.reply(payload)[1], "stop")
            payload["messages"].append({"role": "user", "content": probe.FOLLOWUP})
            self.assertEqual(model.reply(payload), ({"content": probe.ACK}, "stop"))
            self.assertEqual(model.tool_calls, 1)

    def test_fixture_command_quotes_paths_and_produces_real_timestamps(self):
        with tempfile.TemporaryDirectory(prefix="steering ' fixture ") as folder:
            root = Path(folder)
            result = subprocess.run(
                shlex.split(probe.fixture_command(root, 0.01)),
                capture_output=True,
                text=True,
                timeout=5,
                check=True,
            )
            self.assertEqual(result.stdout.strip(), "TOOL_DONE")
            self.assertEqual((root / "tool-runs.txt").read_text().splitlines(), ["RUN"])
            self.assertLess(
                json.loads((root / "tool-start.json").read_text()),
                json.loads((root / "tool-end.json").read_text()),
            )

    def test_invalid_options_do_not_validate_or_create_resources(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(probe, "validate") as validate:
            output = Path(folder) / "evidence"
            for hold, timeout in (
                (0, 90),
                (-1, 90),
                (float("nan"), 90),
                (float("inf"), 90),
                (61, 90),
                (5, 5),
                (5, float("nan")),
            ):
                with self.subTest(hold=hold, timeout=timeout), self.assertRaises(ValueError):
                    probe.check(Path("/no-client"), output, hold=hold, timeout=timeout)
            self.assertFalse(output.exists())
            validate.assert_not_called()

    def test_existing_output_is_preserved(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(probe, "validate") as validate:
            output = Path(folder)
            sentinel = output / "report.json"
            sentinel.write_text("original")
            with self.assertRaisesRegex(ValueError, "new evidence"):
                probe.check(Path("/no-client"), output)
            self.assertEqual(sentinel.read_text(), "original")
            validate.assert_not_called()

    def test_failed_native_case_saves_failure_without_claiming_success(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(probe, "validate", return_value={"version": "test"}),
            patch.object(probe, "run_case", side_effect=RuntimeError("native failure")),
        ):
            output = Path(folder) / "evidence"
            with self.assertRaisesRegex(RuntimeError, "native failure"):
                probe.check(Path("/mock-client"), output)
            report = json.loads((output / "report.json").read_text())
            self.assertEqual(report["state"], "failed")
            self.assertNotIn("immediate_delivery_in_all_cases", report)

    def test_successful_measurement_does_not_claim_target_is_met(self):
        with (
            tempfile.TemporaryDirectory() as folder,
            patch.object(probe, "validate", return_value={"version": "test"}),
            patch.object(probe, "run_case", return_value={"delivery_phase": "after_tool"}),
        ):
            output = Path(folder) / "evidence"
            report = probe.check(Path("/mock-client"), output, mode="api")
            self.assertEqual(report["state"], "measured")
            self.assertFalse(report["immediate_delivery_in_all_cases"])
