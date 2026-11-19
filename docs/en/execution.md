# Managed commands, follow-ups and pause/stop

This development-main feature is newer than the v1.4.4 tag and absent from its original downloads. Update the client program, then exit/resume chat so a new OpenCode process loads local_ai_task. No model-server restart is required. Validated OpenCode 1.19.5 is retained.

## Short examples

Ask in chat: "Run this long command as a background task, give me its ID, then answer my questions." The assistant should use local_ai_task start and promptly return a job_ ID. Continue asking questions, or request "pause this session's tasks", "resume", or "stop this session's tasks". Native permissions and account privileges still apply; model interpretation/tool selection require separate verification.

Direct terminal use on BCM does not depend on the model:

```bash
cd /home/alice/project
/raid/local-ai/local-ai client job start --command 'sleep 30; echo done'
/raid/local-ai/local-ai client job list
```

Replace JOB_ID with the returned job_ identifier:

```bash
/raid/local-ai/local-ai client job status JOB_ID
/raid/local-ai/local-ai client job pause JOB_ID
/raid/local-ai/local-ai client job resume JOB_ID
/raid/local-ai/local-ai client job stop JOB_ID
/raid/local-ai/local-ai client job output JOB_ID
```

start means submitted, not completed. control_requested from pause/stop is not confirmation of suspension/exit: inspect status for paused or terminal=true. Stop sends TERM and CONT so paused processes can exit; remaining group members receive KILL after one second. Only verified owned process groups are signalled.

Session controls require the exact OpenCode ses_ identity and original project path, both available in job list. CLI-created jobs default to session=cli:

```bash
/raid/local-ai/local-ai client job pause-session --session SES_ID --project /home/alice/project
/raid/local-ai/local-ai client job resume-session --session SES_ID --project /home/alice/project
/raid/local-ai/local-ai client job stop-session --session SES_ID --project /home/alice/project
```

pause-session gates subsequent tools and requests suspension of managed jobs. Explicit resume-session releases the gate and resumes only jobs paused by the session; individually paused jobs need their own resume. stop-session cancels owned jobs and keeps the gate closed until explicit resume-session. Pausing does not undo writes, retract model requests or adopt native tools already executing.

## Background and recovery boundaries

- Jobs are local noninteractive commands, with empty stdin and no PTY. They survive terminal/OpenCode exit. After reopening chat, use list/status/output to inspect them. Each job uses a private worker copy across program updates.
- Existing ordinary Bash/TUI processes are not adopted. Synchronous native Bash may still delay new messages until it returns. During-command follow-ups apply when the long command uses local_ai_task and another synchronous tool is not blocking the main conversation.
- No automatic model wake-up or periodic completion notification is provided. Return the task ID and stay conversational; the user or later tool calls inspect completion. Do not occupy the conversation with tight polling.
- Control covers owned local process groups and descendants inheriting that group. Deliberate setsid/daemonization, remotely submitted SSH jobs, Slurm and container jobs require separate execution/cancellation adapters.
- Reboot or worker loss never automatically replays a command. orphaned means the worker disappeared and a command may remain: inspect or request verified stop. lost means no live group members remain but final result/output is incomplete, never success.
- Clarify ambiguous targets when multiple jobs run. Natural-language control depends on the model; use CLI for direct control. This is not an OS sandbox.

## State, output and privacy

Private state/logs live under execution/ in the current user's state root, normally ~/.local/state/local-ai/execution, independent of endpoint. Directories are mode 0700, bound to resolved project paths and session identities. The tool rejects cross-session/project control; CLI can explicitly manage the current user's jobs by ID. This does not synchronize across users or BCM hosts.

start requires a stable request_id. Repeating the same operation in one session/project returns the original job; changed arguments are rejected. CLI creates a new key by default; supply --request-id when retrying. remove deletes terminal job files/logs but retains a replay-prevention tombstone. An intentional new run needs a new key.

output uses byte offset/next_offset, with 16384 bytes per page by default and a range of 1..65536. Reuse next_offset until terminal and all_output_delivered=true. text is a readable UTF-8 preview and may replace characters split across pages; data_base64 preserves exact bytes. Explain any truncated=true gap instead of presenting the remainder as complete.

Default timeout is 3600 wall seconds including pauses, maximum 604800. Each state root permits 32 unfinished jobs; combined stdout/stderr is limited to 64 MiB per job. Overflow stops the job as output_limit/truncated, never success. Other terminal states are completed, failed, cancelled, timed_out and lost; command exit status is exit_code. Existing tasks/report diagnostics remain distinct from client job execution.

Commands, arguments and output can contain secrets: keep them private. Public offline exports exclude these records. Execution asks for native Bash permission and external_directory permission for outside paths; explicit Bash denial prevents execution through the custom tool.

[Parameters and exit codes](commands.md#managed-command-tasks-development-main) · [Measurements](client-steering.md) · [中文](../execution.md)
