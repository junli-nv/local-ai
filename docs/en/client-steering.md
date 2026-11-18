# New messages during OpenCode execution: requirement and baseline probe

## Objective and current scope

User-confirmed objective on 2026-11-18: incorporate follow-up requirements, side questions, pause and stop requests while the original task is still progressing, without waiting for the entire task. Prefer the validated OpenCode route, retaining models, GPU services, sessions and airgap deployment. Codex is a later alternative, not part of this implementation.

Only step one is implemented: an isolated baseline probe to locate delays at terminal input, native session persistence or tool/model-request boundaries. It changes no runtime configuration, native client, queue or execution tool and does not implement the deferred general background-task system.

## Running the isolated probe

Run from feature-bearing source on a BCM/development Linux host or CPU CI with an installed native client. Examples use /raid/local-ai; substitute the actual client architecture directory. The probe uses a loopback mock model and temporary files, without real model/GPU requests or scheduler submissions.

```bash
cd /raid/local-ai
PYTHONPATH=src python3 scripts/check-steering.py --client-dir /raid/local-ai/clients/amd64 --output /tmp/local-ai-steering-evidence
```

--client-dir and --output are required. --output must not exist; use a new directory each time. --mode is api, tui or both (default). --hold-seconds defaults to 5 and must be positive and at most 60. --timeout is the deadline per case, defaults to 90 seconds and must exceed the hold duration. These are configurable measurement windows, not response guarantees or global progress-update intervals.

Both cases first start the same harmless Shell wait through the native API. After confirming command startup, api submits a follow-up through the session API; tui attaches the real TUI and enters text plus Enter through a pseudoterminal. The mock returns a fixed tool call and acknowledgement to remove model-decision variation. This does not test a live model's interpretation of natural language.

Project, session configuration, caches and history are temporary; personal OpenCode/Claude instructions are not loaded. The fixed command writes timestamps and a single-execution marker only inside the temporary project. The client may still need prepared SDK/plugin dependencies; provision these for strict airgap use. The probe adds no download step and loopback tests do not establish disconnected-network acceptance. Cleanup aborts the isolated session and reaps its client processes on completion/failure.

## Evidence and interpretation

The new evidence directory has mode 0700. report.json, api/tui-events.json and backend logs are private files. Events are seconds relative to one monotonic-clock origin, without real prompts, credentials or user task data. All API/TUI evidence comes from this mock session; logs may contain temporary paths. CPU CI retains evidence artifacts, including partial evidence on failure.

| Event or field | Meaning |
|---|---|
| tool_started / tool_finished | Start/end timestamps written by the mock command itself |
| follow_up_submitted | Probe begins API submission or writes terminal input |
| follow_up_persisted_observed | First poll observing the stored user message; not the exact receive timestamp |
| follow_up_in_model_request | Mock API first receives the follow-up in a main-session model request; title/no-tool requests excluded |
| ack_persisted_observed | First observed mock acknowledgement in an assistant message; not proof of natural-language understanding |
| delivery_phase | during_tool means delivery before command completion; after_tool means later |
| backend_visible_before_tool_end | Whether persistence was observed before completion, separating receipt from model delivery |
| command_runs_once | Confirms the follow-up did not repeat command execution |

Exit 0 and state=measured mean a complete measurement, not that responsiveness is achieved. immediate_delivery_in_all_cases is true only when every measured case delivers during_tool and applies only to that window. Missing events, unexpected tool termination, lost messages, repeated commands, timeouts and native failures exit nonzero with a failure report; do not reinterpret failure as simply unsupported immediate delivery.

## Follow-up work

- Compare current and isolated candidate clients to identify reusable native steering before considering a narrow execution-tool adapter. Preserve the validated client.
- Separate streaming generation, short tools, long Shell calls and explicit queue mode. This probe measures one follow-up during a long Shell call only.
- Verify new constraints affect subsequent actions, questions are answered before continuing, pauses prevent new steps and explicit stops are confirmed against process state.
- Distinguish pausing the assistant from cancelling a command. Ordinary follow-ups must not implicitly kill work; clarify ambiguous targets when several tasks run.
- Retain session recovery, exactly-once writes, permissions, cleanup, disconnected operation and existing client contracts in future acceptance.
- Recording this requirement does not authorize a background system, client migration or remote-service changes.

## Where the Claude-derived template changes live

Commit 8855c7d changes both general templates: authorized continuation and mid-task questions under task execution, a new Changes and verification section, and outcome-first final reporting. The BCM-specific template is unchanged. See [prompt references](prompt-references.md) for sources, fragment versions and mappings.

These changes are on main after the published v1.4.3 tag. Downloading/reinstalling the original v1.4.3 archive cannot provide them. Use source containing those commits and rerun client installation as the actual chat user to update the personal managed block, then exit/resume chat. Existing tags are unchanged; the new responsiveness requirement is not presented as a capability already implemented by prompts.

[Development](development.md) · [中文](../client-steering.md)
