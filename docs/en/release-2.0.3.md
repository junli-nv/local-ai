# v2.0.3: interactive exit resume command

After closing an interactive local-ai chat with Ctrl-C, copy the displayed local-ai chat --session command to restore the same session. It carries the original project and history path and retains temporary model or endpoint overrides. Regular sessions use the current saved connection.

Verified with OpenCode 1.19.5, including Ctrl-C, a project path with spaces, and replay of the displayed command. Already running clients load the new hint on their next launch.

[Command guide](commands.md#resume-and-terminal-clipboard) · [中文](../release-2.0.3.md)
