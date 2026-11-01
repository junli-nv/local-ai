# Development workflow

[中文（默认）](../development.md)

## Scope of development rules

These conventions apply when changing this repository, not to ordinary operations
tasks. See [AGENTS.md](../../AGENTS.md) and its
[English version](contributor-instructions.md). Only the pure
`server plan --inventory FILE` feature must avoid additional hardware probes,
subprocesses and file writes. User-requested local or SSH hardware queries are
normal operations. [operations.py](../../src/local_ai/operations.py) supplies
general operations guidance, written to each private chat session and loaded
through its client configuration.

## Developer handoff and contribution conventions

1. Read README topology, the command manual, architecture and validation record first. Keep raw infrastructure evidence in ignored runtime paths.
2. Keep command entry points in cli.py. Every new command needs recursive help, option meanings/defaults, execution location and matching Chinese/English documentation.
3. Keep GPU policy, server CPU/image platform and client architecture independent. Add profiles and inventory fixtures; never hardcode real hosts or GPU UUIDs.
4. Generate engine arguments through profiles.py. Pin model revisions and image manifest/platform digests rather than mutable tags.
5. Plans with supplied inventory must not spawn processes or write files. Validate live occupancy, CDI and platform at start.
6. Route installation diagnostics through installlog.py, keeping JSON stdout separate from progress stderr. Expected missing-object probes are not installation failures.
7. Validate local artifacts; distinguish verified and unverified provenance without fabricating locks. Preserve both archive checksums and imported-image content identity.
8. Run the unittest, Ruff and diff checks below. Fix failures without deleting or weakening existing acceptance tests.
9. Record hardware/version/method/results/limits for real GPU tests. CPU tests alone never promote a hardware validation level.
10. Review staged files, record release evidence, clean temporary containers/client-processes/resources, push and inspect CI.

Use the profile workflow below when B200 or later hardware becomes available. Do not relabel a validated profile as support for an untested GPU.

## Development without a GPU

Base sanitized inventories on the [existing fixture](../../tests/fixtures/b300-tp4.json). Validate argument generation and rejection cases first.
This command probes no real GPUs, starts no container and creates no data directory:

```bash
./local-ai server plan --host 0.0.0.0 --profile b300-tp4 --gpus 0,1,2,3 --inventory tests/fixtures/b300-tp4.json --data-dir /tmp/local-ai-plan
```

See [profiles.json](../../src/local_ai/profiles.json), [engine arguments](../../src/local_ai/profiles.py),
[policy tests](../../tests/test_policy.py) and [installation/cache/documentation tests](../../tests/test_installation.py).

## Project configuration

pyproject.toml configures Python packaging and developer tools; ordinary source-checkout usage does not require editing it.

| Section | Purpose here |
|---|---|
| build-system | setuptools>=68 build backend |
| project | cluster-local-ai 0.1.0, Python>=3.10, no third-party runtime dependencies |
| project.scripts | Installed local-ai entry point: local_ai.cli:main |
| tool.setuptools | Find packages under src and include profiles.json |
| project.optional-dependencies | dev extra installs Ruff 0.14.2 |
| tool.ruff | Python 3.10 target, 100-character lines and lint rules |

The root Bash launcher adds src to PYTHONPATH and calls the same entry point. Model/GPU engine presets live in profiles.json/profiles.py. See the [command manual](commands.md).


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

Editable installation (-e) reflects source changes immediately; .[dev] includes developer tools. unittest -s selects the test directory and -v lists test names. ruff check checks rules; ruff format --check verifies formatting without editing. git diff --check finds whitespace errors.

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
- Test two sessions keep stable history but separate endpoint connection configs.
- Verify execution location with hostname, not merely a successful model reply.
- Keep raw logs and customer infrastructure identifiers under ignored runtime
  paths. Commit sanitized aggregate validation records only.
- CI must not start GPU work or change Slurm, firmware or networking.
- Preserve production service state while refactoring and publishing code.

Before pushing, inspect staged files for models, binaries, caches, credentials
or private paths. Run all checks. Commit source, tests, docs and CI together.
Use small changes when adding a new profile; include its acceptance evidence
before changing its advertised validation status.
