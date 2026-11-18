# v1.4.4: General instructions and message-response baseline

General OpenCode templates add reading before changes, bounded scope, actual verification, authorized task continuity and outcome-first reporting. Adaptations reference a third-party Claude Code prompt collection; sources, pinned commits and mappings are documented in [prompt references](prompt-references.md). BCM templates retain their existing responsibilities.

- Templates ship with source and offline bundles. Reference documentation lives in docs/; installation and chat do not download prompts.
- Automatic personal-rule installation from v1.4.3 is retained. After updating source, run ./local-ai install --role client as the actual chat user (optionally --instructions bcm) to update the personal managed block, then exit/resume OpenCode. The standalone updater does not apply rules.
- New scripts/check-steering.py measures API/TUI follow-ups using isolated configuration and a local mock model. The Linux AMD64/OpenCode 1.19.5 baseline shows prompt receipt but model delivery after the five-second command finishes. Immediate responsiveness, asynchronous execution and stopping are not implemented. See [message-response checks](client-steering.md) for procedure and limitations.
- Retaining tar and improving outer-archive extraction time is recorded as a low-priority follow-up. This version does not change the format or claim performance improvements.

See [validation](validation.md) for scope. At the user's request, create and push an annotated v1.4.4 tag on the exact CI-passed commit, preserve existing tags and do not create a GitHub Release.

[中文](../release-1.4.4.md)
