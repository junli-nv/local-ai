# Development workflow

[中文（默认）](../development.md)

## Setup and checks

Runtime code uses Python's standard library only. Optional developer tools belong
in a project virtualenv, not OS-managed Python:
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
git diff --check
```

CPU-only CI tests policy and failure boundaries. It cannot establish CUDA kernel
compatibility, hardware memory requirements, topology or throughput.

## Add a hardware profile

1. Check the upstream model recipe and actual local GPU count, HBM, server CPU
   architecture, interconnect and host RAM.
2. Verify the container manifest contains that platform. Record the pinned
   manifest-list digest and selected platform child digest.
3. Add policy to `src/local_ai/profiles.json`: architecture/platform, local TP,
   Engram placement, GPU family, conservative HBM guard and validation level.
4. Keep engine argument generation in profiles.py. Never add GPU branches to the
   BCM client or derive its binary architecture from the server.
5. Test valid and invalid GPU selection, duplicate indices/UUID aliases, missing
   devices, wrong CPU/image and insufficient memory.
6. Plan with `server plan --inventory FIXTURE.json`. Inventory fixtures are
   accepted only by plan; start always probes the actual GPU host.
7. On allocated hardware: prepare the pinned image/weights, start, wait for API
   health, test streaming and a native tool roundtrip, then an actual BCM
   edit/test/hostname task. Inspect memory and logs, then stop.
8. Record exact versions, methodology, results and limits in validation.md.
   Never upgrade a profile to hardware-verified based only on unit tests.

A two-GPU GB300 OS instance needs a TP2 profile and enough host RAM. Tensor
parallelism across OS instances is a separate orchestration feature, not just a
new profile JSON entry.

## Add or upgrade a model

Change repository/revision, tokenizer/parsers, model directory and client
capabilities together. Test streaming termination, reasoning transport,
tool-call/result roundtrips and an actual file-edit/test task.
Never silently point an existing served-model name at a different revision.
Record thinking/quantization changes separately from runtime optimizations.

## Client and offline artifacts

Select the native binary on BCM, independently of the server platform.
An online installation uses an exact NPM package release and verifies SHA256 or
SHA512 integrity before extracting/executing the allowlisted binary.
Imported binaries require matching ELF architecture, optional SHA256 and the
requested version. CPU architecture alone is not an entire ABI compatibility
test: check target distro/shared libraries and CPU instruction support.

Asset exports include only the installed binary, allowlisted public cache and
manifest. They exclude histories, auth files and SSH keys.
Model weights are architecture-independent; images, client binaries and cached
executables are architecture-specific. Never reuse AMD64 caches on ARM64.

## Testing and review rules

- Keep plan generation deterministic and free of subprocesses/writes.
- Test rejected states and cleanup, not just a happy-path command.
- Require image config/layer identity after import; a tag alone is insufficient.
- Test two sessions keep stable history but separate temporary tunnel configs.
- Verify execution location with hostname, not merely a successful model reply.
- Keep raw logs and customer infrastructure identifiers under ignored runtime
  paths. Commit sanitized aggregate validation records only.
- CI must not start GPU work or change Slurm, firmware or networking.
- Preserve production service state while refactoring and publishing code.

Before pushing, inspect staged files for models, binaries, caches, credentials
or private paths. Run all checks. Commit source, tests, docs and CI together.
Use small changes when adding a new profile; include its acceptance evidence
before changing its advertised validation status.
