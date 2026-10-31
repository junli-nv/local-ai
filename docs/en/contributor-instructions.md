# Contributor instructions

- Keep GPU-server and BCM-client roles separate.
- Runtime code uses Python 3.10+ standard library only.
- Use Bash launchers and a project virtualenv for optional development tools.
- Planning with supplied inventory must not probe hardware or write files.
- Never infer client CPU architecture from a GPU profile.
- Reject occupied GPUs, conflicting ports, wrong images and spec drift.
- Preserve per-user state and owned SSH-tunnel cleanup.
- Do not commit weights, binaries, caches, credentials or raw infrastructure logs.
- Run unittest, Ruff check/format checks and git diff --check.
- GPU validation requires an allocated device set; never launch it from CI.

[中文（默认）](../../AGENTS.md)

## Documentation languages

Chinese is the primary development and documentation language. Keep complete Chinese documentation at the default entry points, with English translations in separate files linked at the end. Update both languages when behavior or commands change and retain the same validation limits.

- Keep recursive CLI help and both manuals in sync; preserve JSON stdout and progress stderr.
- Keep installation diagnostics in install.log; distinguish expected probes and reuse complete local artifacts offline.
- Extend GPU support through separate profiles, fixtures and hardware acceptance evidence.
