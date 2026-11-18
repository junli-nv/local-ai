# v1.4.3: apply personal instructions during client installation

Client installation applies Chinese general rules to the actual running user's global OpenCode AGENTS.md by default, removing the initial manual copy. Both install --role client/both and lower-level client install support this; server-only installation does not configure personal rules.

- --instructions general (default) applies general rules, bcm adds BCM rules, and none leaves all personal rules untouched without removing an installed block.
- --instructions-language zh (default)/en selects template language, not response language.
- Preserve existing content, create a private backup before changes and atomically replace the target. Reinstallation updates only the local-ai managed block; unchanged contents cause no write.
- Keep personal changes outside the managed block. Repair symlinks, other-user files or damaged markers, or explicitly skip. sudo/root configures only its running user, without inferring a chat account.
- Source updates/exports do not apply personal rules. Rerun client installation as the actual chat user after upgrading to apply new templates, including offline. Exit and resume the original OpenCode session afterward.

General rules include long-task waiting/progress guidance without fixed timing, line counts, headings or hard timer guarantees. Installation starts no GPU and changes no models, images or inference parameters; v1.4.2 user-local history/server decoupling is retained. See [setup and backup recovery](../../templates/opencode/en/agent-instructions.md) and [validation](validation.md).

At the user's request, create an annotated v1.4.3 tag on the exact CI-passed commit, preserving existing tags without creating a GitHub Release.

[中文](../release-1.4.3.md)
