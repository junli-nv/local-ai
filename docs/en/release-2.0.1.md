# v2.0.1: client reliability fixes

This release packages completed post-v2.0.0 fixes, not deferred features. OpenCode remains 1.19.5.

- Personal instruction installation backs up and migrates exact legacy template copies, preserving custom text and fenced examples.
- chat run accepts options before or after its prompt, retaining text/JSON/file/stdin behavior.
- client job recover verifies existing SSH/Slurm/container identity and restores monitoring without resubmission. Confirmed terminal facts and bounded contiguous output caches remain readable after connection failure, with explicit partial coverage.
- Native controls acceptance now waits for confirmed asynchronous completion, preserving permission, pause, stop and single-start assertions.
- Current download, update and offline examples are aligned; [deferred work](development.md#deferred-backlog-2026-11-19) is recorded.

Existing sessions and personal configuration are retained. Exit/resume chat after client update to load plugins; no model-server restart is required. History restore still requires matching native OpenCode versions. New recovery acceptance covers actual SSH; Slurm/container recovery, strict offline and sustained stress remain follow-ups. See [validation](validation.md).

[中文](../release-2.0.1.md)
