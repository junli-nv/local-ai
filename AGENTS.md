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
