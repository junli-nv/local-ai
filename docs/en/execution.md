# Managed commands, follow-ups and pause/stop

v2.0.0 includes automatic Bash backgrounding, completion messages, PTY input and SSH/Slurm/container adapters. Update the program, then exit/resume chat to load plugins. No model-server restart is required. The reference client remains OpenCode 1.19.5.

## Start here

In interactive chat, ordinary Bash waits about 400 ms for short commands, then returns a job_ ID for longer commands so you can send follow-ups. You may explicitly request a background task and completion report. The assistant uses local_ai_task to manage tasks. Submission is not completion.

Command-scoped Bash permission rules retain the native parser and synchronous Bash; use local_ai_task explicitly. --sync-bash also retains native Bash. Other synchronous tools can still block messages; responsiveness is not universal. [Batch pipelines](automation.md) use synchronous Bash by default to return actual results.

```bash
./local-ai client job start --command 'sleep 30; echo done'
./local-ai client job list
./local-ai client job status JOB_ID
./local-ai client job output JOB_ID
./local-ai client job pause JOB_ID
./local-ai client job resume JOB_ID
./local-ai client job stop JOB_ID
./local-ai client job remove JOB_ID
```

control_requested only records a pause/stop request. Query status to confirm paused or terminal=true. Local stop sends TERM, wakes paused processes, and uses KILL after one second if needed, only for verified owned process groups. remove requires a terminal task and retains its replay-prevention key; intentional reruns need a new request_id.

## Sessions, notifications and lifetime

```bash
./local-ai client job pause-session --session SES_ID --project /home/alice/project
./local-ai client job resume-session --session SES_ID --project /home/alice/project
./local-ai client job stop-session --session SES_ID --project /home/alice/project
```

Use the exact ses_ ID from job list; CLI tasks default to session=cli. pause-session gates new tools and pauses owned tasks. resume-session releases the gate and only resumes tasks paused by the session action. Individually paused tasks need individual resume. stop-session keeps the gate closed until explicit resume-session. Pausing cannot undo completed writes or sent model requests.

On v2.1.3, tasks whose complete terminal output has already been returned to the model through local_ai_task only show a completion/warning toast when chat is idle. No message is inserted and the model is not awakened to repeat that results were read or already reported. Status-only and partial reads still trigger stable-ID automatic processing, allowing the assistant to inspect output, consolidate results and continue authorized work. Contiguous read cursors persist in private task state across restarts. For older jobs, actual tool outputs in the latest 100 native messages are checked; uncertain cases retain automatic processing. CLI inspection does not consume chat notices.

Notices add no authorization. Busy, paused or held sessions defer delivery. --no-task-notifications disables notices for this invocation. Exiting/aborting chat does not stop tasks; resume and send a message to resume checking. No notification daemon runs outside chat. Restart/resume after updating the program; the original v2.1.2 tag does not include this change.

Local workers and adapter controllers use private code copies and survive chat exit/program updates. Reboot does not automatically restore or replay commands. Uncertain states are not completion. orphaned means a lost worker with possibly live processes; lost means incomplete final results. Inspect identity before acting. Deliberately detached descendants may escape local group control. This is not an OS sandbox.

## PTY input and adopting a process

```bash
./local-ai client job start --interactive --command 'read -r answer; echo "$answer"'
./local-ai client job input JOB_ID --data $'hello\n' --request-id answer-1
./local-ai client job adopt --pid 123456
```

PTY is local/new-task only. input accepts 1..16384 UTF-8 bytes including explicit newlines, with stable request_id deduplication; at most 64 pending inputs and 4096 input keys. adopt requires a same-user independent process-group leader and rejects the caller's ancestry. It neither reruns the command nor reattaches stdout/terminal. Natural exit is exited with unknown exit code, not proven success. Arbitrary existing TUIs cannot automatically become interactive managed tasks.

## SSH, Slurm and containers

```bash
./local-ai client job start --adapter ssh --host GPU001 --remote-project /raid/work --command 'sleep 30; echo done'
./local-ai client job start --adapter slurm --project /home/alice/project --submit-arg=--mem=128M --command 'hostname'
./local-ai client job start --adapter container --host GPU001 --image MY_PREPARED_IMAGE --command 'echo done'
```

Remote options require explicit --adapter. SSH requires Python 3 and noninteractive SSH on the target; the absolute target directory must exist. Slurm submits locally unless --host is supplied; the project/output directory must be shared between submit and compute hosts. One CPU is requested by default; memory uses site defaults unless explicitly supplied through --submit-arg. GPUs are not requested implicitly. --remote-project applies to SSH/Slurm.

Containers use prepared images only (--pull=never), NVIDIA_VISIBLE_DEVICES=void by default, no GPU allocation, no automatic project mounts, and the image's working directory. Docker permissions are required on the target. Remote containers use --host; local clients otherwise need no Docker. Remote PTY is unsupported. The same job ID supports status/output/pause/resume/stop; verify actual backend state after cancellation. Container labels, Slurm owner/job name and remote process identity are checked. Unreachable/unknown backends are not resubmitted.

## Output, limits and privacy

State defaults to ~/.local/state/local-ai/execution, scoped by user, real project path and session, independently of endpoint. Tools reject cross-session/project management; the current user can explicitly manage their own job IDs through CLI. Directories are 0700 and files 0600. Commands/input/output can contain sensitive content and are excluded from public offline exports and history migration archives.

output defaults to 16384 bytes; --limit accepts 1..65536. Reuse next_offset until terminal and all_output_delivered=true. text is a UTF-8 preview with possible replacement at page boundaries; data_base64 preserves bytes. Report any truncated=true coverage gap.

Default timeout is 3600 wall seconds including pauses, maximum 604800, with at most 32 unfinished tasks per state root. Local/SSH output above 64 MiB stops the task and marks a gap. Container snapshots retain at most 64 MiB and flag overflow/rotation without stopping the container. Slurm logs are paged on demand. Evaluate completed/failed/cancelled/timed_out with exit_code. A management command exiting 0 means the request was processed, not that its task succeeded.

[Parameters](commands.md#managed-command-tasks-v200) · [Measurements](client-steering.md) · [中文](../execution.md)


## Recovery and offline results on v2.0.1

```bash
./local-ai client job recover JOB_ID
./local-ai client job status JOB_ID
./local-ai client job output JOB_ID
```

recover verifies the recorded backend identity and restores monitoring without executing the original command again. Unconfirmed submissions are never replayed. Paused tasks remain paused and existing deadlines remain in effect. controller_running=false on an unfinished adapter task is also reported by doctor as controller_stopped.

Once terminal state is observed, status uses the recorded fact even if SSH later fails. The controller attempts to collect a contiguous output prefix for up to about 20 seconds plus the final bounded backend call, capped at 64 MiB. output_cache.complete=true means all observed output was retained; missing/large/slow output may require another recover or online output read. This cache does not expand backend capture limits or hide truncated=true.

Complete cached pages can be read without the backend. Partial cache reports coverage_gap=true and never all_output_delivered=true; reading past its available prefix fails with the missing byte range. It does not synthesize empty output. A changed backend output prefix is a coverage error. An already running controller from an older installation is retained; after it exits, explicit recover can collect results using current code. Removal still requires backend validation/cleanup.

This is task monitoring recovery, not cross-BCM task migration, arbitrary TUI reattachment or machine-reboot replay.

Since v2.0.2, log read failures preserve confirmed terminal state and exit code. Retry when a missing Slurm log appears; older empty caches incorrectly marked complete are rechecked. When the terminal cache is incomplete, recover checks the backend first and returns backend_unverified on failure while retaining the terminal state.

v2.0.2 validates the local cache file. If the file is missing or its length disagrees with the record, recover verifies the backend and rebuilds from byte zero. When output detects a conflicting backend prefix, it reports the error directly.
