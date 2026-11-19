# Batch pipelines, history migration and diagnostics

## Chain chat with scripts

v2.0.0 defaults to readable assistant text (possibly Markdown), without a JSON wrapper, ANSI controls, reasoning or tool panels on stdout. Progress/errors use stderr. This is pipeline output rather than a TUI screen replica.

```bash
./local-ai chat run "Summarize the current project"
./local-ai chat run --prompt-file task.txt
./collect.sh | ./local-ai chat run --prompt-file -
./local-ai chat run "Task" --format json
```

--prompt-file reads UTF-8 prompt text, even for a .sh file; it does not implicitly execute it. In the pipeline, Bash executes collect.sh and its output becomes the prompt. Choose exactly one source: positional prompt, legacy --run, file or stdin. Input must be nonempty and at most 1 MiB. chat run with no prompt also reads nonterminal stdin.

Legacy chat --run remains supported but also defaults to text. Existing consumers of native newline-delimited events must add --format json. Raw events remain in private terminal.log. Text streams incrementally and cannot be retracted if a later error occurs; check exit codes, e.g. Bash set -o pipefail. Batch timeout returns 124, interrupts 130/143; other native failures remain failures. Explicit background tasks are not automatically cancelled when batch exits.

Batch retains synchronous Bash and asks the assistant to finish and verify before answering. Return only a background ID when background submission was requested. Script and tool contents add no authorization; execution permissions still apply.

## Switch servers or move to another BCM

Within one user's state root, endpoint changes reuse local history:

```bash
./local-ai config set endpoint http://GPU002:18000/v1
./local-ai chat --session SES_ID --project /home/alice/project
./local-ai client history list
```

For legacy endpoint-scoped histories, use list to find the old URL, then client history update-endpoint --old OLD_URL to associate it with the current URL. This is legacy compatibility, not a recurring requirement for normal server changes. Model tool/context compatibility still matters.

On another BCM/state root, run as the history's owner:

```bash
./local-ai client history backup --output /home/alice/private-history.zip
./local-ai client history restore --archive /home/alice/private-history.zip --endpoint http://GPU002:18000/v1 --select
./local-ai client history list
./local-ai chat --session SES_ID --project /home/alice/project
```

Transfer the ZIP privately. Install a matching OpenCode version on the destination; --client-dir can select its assets. backup uses SQLite online snapshots, preserves sources and refuses to overwrite an archive. restore verifies hashes/database integrity and creates independent history IDs without merging/overwriting existing populated histories. Existing selection is retained unless --select is explicit; an empty destination selects automatically. Reimporting the same archive is idempotent. client history select HISTORY_ID selects later. --state-dir names each host's state root.

Archives are mode 0600 and contain **full, unredacted conversations**, possibly including pasted secrets. auth.json, SSH keys, caches and task logs are excluded, but this is not a public offline export. Project files, managed tasks and running processes are not migrated. Copy projects separately. A program update backup is not a history backup.

If the project path changed, add --project /home/alice/new-project to restore and use the same chat --project with --session SES_ID; opencode -s SES_ID also uses the saved mapping. Conversation paths and native database schema are not rewritten. The current directory is explicitly supplied to the model; access to the new location may require native permission confirmation. Explicit session IDs are preferred because native --continue directory filtering may miss older paths. Restore's --endpoint changes imported history metadata, not installation.json; configure the default server separately.

## Combined diagnostics

```bash
./local-ai client doctor
./local-ai client doctor --check-endpoint
```

By default this reads local metadata only: native assets, histories, managed tasks, recent runs, model-request timings/usage and issues. It does not request inference or print conversations, command output or request bodies. --check-endpoint explicitly checks API readiness; --limit defaults to 20. Missing observations remain unknown, not proof of health. Exit 0 means a report was generated; inspect issues and task states.

[Execution and backends](execution.md) · [Parameters](commands.md) · [中文](../automation.md)


Legacy clients without connection.json can be backed up when launch records still contain a selected provider, project and installed client. The archive marks legacy-launch-config metadata; a historical tunnel URL is never contacted. Restore always uses your explicit/configured destination endpoint. Missing metadata/assets still fail rather than guessing or skipping history.


Post-v2.0.0 main fixes argument ordering: chat run --format json "Task" and chat run "Task" --format json are equivalent. The original v2.0.0 archive requires the positional prompt immediately after run. See [recovery](execution.md) for restoring lost task monitors and cached results.
