# Daily-work assistant and contributor instructions

## Daily-work scope

local-ai is a general daily-work assistant: system diagnosis, scripts and code, files
and data, service configuration, and Slurm/Kubernetes job preparation, submission and
tracking are examples, not a task allowlist. Deliver reviewable artifacts and suitable
validation. For requested job submission, respect the specified cluster/resources and
report job IDs, state and logs, distinguishing preparation, submission, queueing,
running and completion. Use the current account's access
to inspect the local host or the remote host named by the user. Read-only hardware
queries are not GPU workload acceptance tests and require neither an inventory
fixture nor a hardware model allowlist.

For a named SSH target, use the existing OpenSSH configuration directly and confirm
the remote hostname. Do not start by enumerating ~/.ssh. Report actual connection
or tool permission errors; a non-interactive automatic rejection is not a user
rejection or a project-wide hardware-query prohibition.

The following rules apply only when changing this repository's code, tests or
documentation. Do not reinterpret them as restrictions on ordinary operations tasks.

## Repository development rules

Read the [product decisions and working order](development.md#developer-handoff-decisions-and-working-order) before taking over. Update implementation, entry docs and evidence together when changing a decision.

- Here, submitting code includes commit and push; verify the authorized push against the remote and inspect CI.

- Keep GPU-server and BCM-client roles separate.
- Runtime code uses Python 3.10+ standard library only.
- Use Bash launchers and a project virtualenv for optional development tools.
- Only the implementation and pure-plan tests of `server plan --inventory FILE` must avoid extra hardware discovery, subprocesses and file writes. This does not restrict operations queries; inventory, live planning and startup inspect actual hardware.
- Never infer client CPU architecture from a GPU profile.
- Reject occupied GPUs, conflicting ports, wrong images and spec drift.
- Preserve per-user state. Model connections use API endpoints only; do not manage network forwarding. Clean up client child processes on exit.
- Do not commit weights, binaries, caches, credentials or raw infrastructure logs.
- Run unittest, Ruff check/format checks and git diff --check.
- GPU validation requires an allocated device set; never launch it from CI.

[中文（默认）](../../AGENTS.md)

## Documentation languages

Chinese is the primary development and documentation language. Keep complete Chinese documentation at the default entry points, with English translations in separate files linked at the end. Update both languages when behavior or commands change and retain the same validation limits.

- Keep recursive CLI help and both manuals in sync; preserve JSON stdout and progress stderr.
- Keep installation diagnostics in install.log; distinguish expected probes and reuse complete local artifacts offline.
- Extend GPU support through separate profiles, fixtures and hardware acceptance evidence.

Documentation changes must follow the [documentation delivery requirements](development.md#documentation-delivery-requirements): review every bilingual document, verify README as the entry point, reconcile defaults/examples/links, and manually read the workflow. Do not create tags without an explicit user request.
