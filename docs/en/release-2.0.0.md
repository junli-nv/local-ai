# v2.0.0: managed execution, history portability and batch pipelines

This is a major version because batch stdout changes from native JSON events to readable text by default. Existing event consumers must add --format json. Management commands still return JSON. Earlier tags are preserved.

## Usage changes

```bash
./local-ai chat run "Inspect the project and report results"
./local-ai chat run --prompt-file task.txt
./collect.sh | ./local-ai chat run --prompt-file -
./local-ai chat run "Task" --format json
```

Files supply prompt text, not implicitly executed scripts. Pipelines can feed script-produced material to the model and its text to another tool. See [batch input/output and exit semantics](automation.md).

## Added capabilities

- Interactive long Bash commands become managed tasks, allowing follow-ups. Task/session pause, resume, stop, full output and replay prevention are available. Completion messages reach a running chat, where the model inspects and reports results.
- Local PTY/input and verified process-group adoption; independent SSH, Slurm and container execution/cancellation adapters.
- Private online history snapshots, independent restore/selection and relocated-project mappings. Local conversations survive server changes; explicit archives move histories between BCMs.
- client doctor combines assets, histories, jobs, recent runs and request observations without transcript bodies; local/read-only by default.
- Updater activity checks, explicit active-client continuation and standalone rollback; program and history backups remain separate.

[Execution and limits](execution.md) · [Parameters](commands.md) · [Updates](update.md).

## Upgrade and acceptance

OpenCode 1.19.5, model API and inference profiles are retained. No vLLM restart is required. Program updates may preserve active clients; exit/resume chat afterward to load new plugins. Personal instructions and private histories are retained. History ZIPs contain unredacted conversations and are not public release assets.

Actual-model BCM/HGX260 acceptance covered follow-ups, frozen pause, same-task resume, confirmed stop, single execution, automatic completion summary, same-session restore and relocated-project reads. Actual CPU SSH/Docker/Slurm controls and text/JSON/file/stdin batch checks passed. Native mock tests also cover API/TUI timing and compound Bash denial/allow rules. See [validation](validation.md); these are not latency SLAs, air-gap validation or new GPU-profile acceptance.

Other synchronous tools can still block; command-scoped Bash policies retain native synchronous parsing. There is no cross-chat notification daemon, remote PTY or reboot replay. Adoption does not reattach output and cannot recover natural exit codes. KV offloading and tar extraction remain low priority.
