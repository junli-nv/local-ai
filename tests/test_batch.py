import argparse
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from local_ai.batch import TextOutput, prompt
from local_ai.cli import parser


class BatchTests(unittest.TestCase):
    def test_positional_legacy_file_and_piped_input(self):
        self.assertEqual(prompt(parser().parse_args(["chat", "run", "hello"])), "hello")
        self.assertEqual(prompt(parser().parse_args(["chat", "--run", "hello"])), "hello")
        with tempfile.TemporaryDirectory() as directory:
            file = Path(directory) / "task.sh"
            file.write_text("Read these instructions; do not execute this file")
            args = parser().parse_args(["chat", "run", "--prompt-file", str(file)])
            self.assertEqual(prompt(args), file.read_text())
        with patch("sys.stdin", io.TextIOWrapper(io.BytesIO("你好\n".encode()))):
            self.assertEqual(
                prompt(parser().parse_args(["chat", "run", "--prompt-file", "-"])), "你好\n"
            )

    def test_prompt_and_options_accept_both_orders_and_literal_delimiter(self):
        for argv in [
            ["chat", "run", "--format", "json", "hello"],
            ["chat", "--project", "/tmp", "run", "hello", "--format", "json"],
            ["chat", "run", "--project", "/tmp", "hello", "--format=json"],
            ["chat", "run", "hello", "--format", "json"],
        ]:
            with self.subTest(argv=argv):
                options = parser().parse_args(argv)
                self.assertEqual(prompt(options), "hello")
                self.assertEqual(options.output_format, "json")
        self.assertEqual(prompt(parser().parse_args(["chat", "run", "--", "--format"])), "--format")
        with self.assertRaises(SystemExit):
            parser().parse_args(["chat", "run", "--unknown", "hello"])
        with self.assertRaises(SystemExit):
            parser().parse_args(["chat", "run", "hello", "extra"])

    def test_conflicting_empty_and_oversized_prompts_are_rejected(self):
        for args in [
            argparse.Namespace(run="one", prompt="two"),
            argparse.Namespace(run=""),
            argparse.Namespace(run="x" * ((1 << 20) + 1)),
        ]:
            with self.subTest(args=args), self.assertRaises(ValueError):
                prompt(args)

    def test_clean_stdout_keeps_only_answer_text_and_unicode(self):
        output, errors = io.StringIO(), io.StringIO()
        renderer = TextOutput(output, errors)
        rows = [
            {"type": "reasoning", "part": {"text": "private thought"}},
            {"type": "tool_use", "part": {"text": "command result"}},
            {"type": "text", "part": {"id": "one", "text": "你好"}},
            {"type": "text", "part": {"id": "one", "text": "你好，世界"}},
            {"type": "text", "part": {"id": "one", "text": "你好，世界"}},
            {"type": "error", "error": {"message": "failure"}},
        ]
        data = ("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n").encode()
        for byte in data:
            renderer.feed(bytes([byte]))
        renderer.finish()
        self.assertEqual(output.getvalue(), "你好，世界\n")
        self.assertTrue(renderer.failed)
        self.assertIn("failure", errors.getvalue())

    def test_native_warning_is_stderr_and_final_partial_line_is_handled(self):
        output, errors = io.StringIO(), io.StringIO()
        renderer = TextOutput(output, errors)
        renderer.feed(b"native warning\n")
        renderer.feed(json.dumps({"type": "text", "part": {"text": "answer"}}).encode())
        renderer.finish()
        self.assertEqual(output.getvalue(), "answer\n")
        self.assertIn("native warning", errors.getvalue())
