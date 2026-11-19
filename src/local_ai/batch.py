"""Batch prompt input and clean answer output; raw native events stay in private logs."""

import json
import re
import sys
from pathlib import Path

MAX_PROMPT = 1 << 20
ANSI = re.compile(r"\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))")


def prompt(options):
    inline = getattr(options, "run", None)
    positional = getattr(options, "prompt", None)
    filename = getattr(options, "prompt_file", None)
    action = getattr(options, "chat_command", None)
    if sum(v is not None for v in (inline, positional, filename)) > 1:
        raise ValueError("Choose one prompt: positional text, --run, or --prompt-file")
    if positional is not None and action != "run":
        raise ValueError('Use chat run "prompt"')
    text = positional if positional is not None else inline
    if filename is not None or (action == "run" and text is None and not sys.stdin.isatty()):
        if filename is None or str(filename) == "-":
            stream = sys.stdin.buffer
            data = stream.read(MAX_PROMPT + 1)
        else:
            path = Path(filename).expanduser()
            if not path.is_file():
                raise ValueError("Prompt file must be a regular UTF-8 file")
            with path.open("rb") as stream:
                data = stream.read(MAX_PROMPT + 1)
        if len(data) > MAX_PROMPT:
            raise ValueError("Prompt input exceeds 1 MiB")
        text = data.decode("utf-8")
    if action == "run" and text is None:
        raise ValueError("chat run requires a prompt, --prompt-file, or piped standard input")
    if text is not None and (not text.strip() or len(text.encode()) > MAX_PROMPT):
        raise ValueError("Prompt must be nonempty UTF-8 text up to 1 MiB")
    return text


class TextOutput:
    def __init__(self, stream=None, errors=None):
        self.stream = stream or sys.stdout
        self.errors = errors or sys.stderr
        self.buffer = b""
        self.parts = {}
        self.failed = False
        self.wrote = False
        self.newline = True

    def line(self, data):
        try:
            row = json.loads(data)
        except (ValueError, UnicodeError):
            if data.strip():
                print(
                    "local-ai: non-JSON native output: " + data[:1000].decode(errors="replace"),
                    file=self.errors,
                )
            return
        if not isinstance(row, dict):
            self.failed = True
            print("local-ai: invalid native event; inspect the private log", file=self.errors)
            return
        if row.get("type") == "error":
            self.failed = True
            print("local-ai: " + str(row.get("error", {})), file=self.errors)
        if row.get("type") != "text":
            return
        part = row.get("part") or {}
        text = part.get("text")
        if not isinstance(text, str):
            return
        key = part.get("id")
        previous = self.parts.get(key, "") if key else ""
        if key:
            self.parts[key] = text
        if previous and text.startswith(previous):
            text = text[len(previous) :]
        text = ANSI.sub("", text)
        if text:
            self.stream.write(text)
            self.stream.flush()
            self.wrote = True
            self.newline = text.endswith("\n")

    def feed(self, data):
        self.buffer += data
        while b"\n" in self.buffer:
            row, self.buffer = self.buffer.split(b"\n", 1)
            self.line(row)
        if len(self.buffer) > MAX_PROMPT:
            self.failed = True
            raise ValueError("Native event exceeds 1 MiB; inspect the complete private log")

    def finish(self):
        if self.buffer:
            self.line(self.buffer)
        if self.wrote and not self.newline:
            self.stream.write("\n")
            self.stream.flush()
