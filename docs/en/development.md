# Development workflow

[中文（默认）](../development.md)

## Developer handoff: decisions and working order

These requirements were progressively agreed with the project owner on
2026-11-01. They guide product development, not restrictions on assistant tasks.
Update decisions, implementation and user docs together when requirements change.

### Purpose and documentation

local-ai is a daily-work assistant for diagnosis, scripts, data, services and
Slurm/Kubernetes jobs. These examples are not allowlists. Gather real system
evidence. Development rules, pure inventory planning and deployment checks must
not prohibit ordinary hardware queries or requested compute jobs. Distinguish
script preparation, job submission and completion.

GPU hosts run inference; BCM tools run as the current user. Model API access
and SSH operations are separate paths.

| Material | Responsibility |
|---|---|
| [README](../../README.en.md) | First-use path, required prerequisites, startup/readiness/log hints; do not bury essential steps elsewhere |
| [Deployment](deployment.md) | Platform, storage, CDI, network and recovery details linked from README |
| [Commands](commands.md) | Commands, options, defaults, execution host, outputs and exit codes matching recursive help |
| This page and [architecture](architecture.md) | Workflow, reasons, module responsibilities and extensions |
| [Validation](validation.md) | Actual environment, method, results and untested limits |
| [AGENTS](../../AGENTS.md) and [operations.py](../../src/local_ai/operations.py) | Repository rules versus general session guidance, with distinct scope |

Chinese is primary; maintain English separately and synchronize both entry paths.

### Agreed decisions

| Feedback | Behavior to preserve |
|---|---|
| Pull failure appears to mean missing image | Separate expected inspect absence from pull failure; show actual error and full log path. Missing metadata.db concerns Docker/containerd storage |
| Share image/model materials | Share weights/export archives separately from active databases. --data-dir does not move Docker/containerd storage. Validate new storage schemes |
| BCM already reaches GPU | Use API endpoints; built-in model SSH tunnels/client doctor are removed. External frp/nginx handle forwarding; operational SSH remains available |
| Connect via host IP | Explicit --host; 0.0.0.0 binds, while endpoints use a real host/IP. Preserve existing network/listener settings |
| Container runs without visible progress | Show logs and startup/loading/readiness/failure. READY requires health, not docker ps, a port or blank curl output |
| Unclear logs/status | install.log for preparation; instances/NAME/server.log for runtime. Clear messages, JSON stdout, progress stderr and meaningful exit codes |
| Native resume loses context | opencode -s ID restores endpoint/project/private state using public metadata, handling empty lists and project scope without private database tables |
| Application copying fails | Default terminal selection/copy/paste; disable application mouse/clipboard shortcuts. Explain disabled click/wheel behavior and verify terminal modes |
| Fixed release blocks upgrades/offline use | Reference releases are validation records, not runtime allowlists. Reuse installs, detect imports, allow explicit releases/offline exports and test capabilities |
| Models/revisions change | Configure recipe identities, directories, names, engine/client capabilities and separate locks; do not inherit hardware acceptance or DeepSeek-specific settings |
| Directory installation and migration | The unpacked directory is the root, with ordinary src/. install prepares assets in place; export writes a complete dist/ bundle excluding dist/, instance state, histories and credentials. Reinstall/reconfigure after moving |
| One BCM, multiple model services | Initial installation endpoint is optional; change defaults through config or direct file editing, not reinstallation. chat --endpoint/--model override one invocation without rewriting defaults. Separate endpoint history/cache and resume original connection; never silently fall back to the default node |
| Source-script delivery | Deliver main/exact commits during development; passing checks does not trigger tags; formal versions require explicit request and quality review |
| Single-user speed and first-use compilation spikes | Keep the baseline unchanged; opt into DSpark and explicit bounded warmup. Separate API READY from WARMUP COMPLETE, persist compiler caches per recipe, invalidate completion on restart, and report actual coverage and concurrency tradeoffs |
| Around 400 ms TTFT seems high | Record method, input size, cache/load and timing first. Separate compilation, generation delay and reasoning content; avoid one-number conclusions |

Use the [manual](commands.md) and [deployment guide](deployment.md) for operations;
this section records design reasons.

### Working order for each request

1. **Understand result and host.** Read this section, AGENTS, README, relevant
   modules/commands and evidence. Separate product changes from assistant tasks.
2. **Reproduce with evidence.** Use authorized connections/accounts and confirm
   hostname. Retrieve available logs directly. Read complete relevant output,
   exit codes and errors; summaries or snapshots are not full evidence.
3. **Locate the layer.** Separate runtime, storage/network, inference, client and
   terminal. Containerd failure does not prove image absence; copying in another
   window does not establish every clipboard path.
4. **Implement reviewable configuration.** Exact identities provide reproducibility,
   not version/model allowlists. Preserve services/state, validate candidates
   separately, and include messages, logs, exit codes and recovery.
5. **Validate appropriately.** Run unittest/Ruff/diff checks; native checks for
   client adapters and streaming/reasoning/tool round trips for models. Test
   rejection, old state and cleanup without weakening cases. Hardware/jobs need
   actual authorization/resources. Disclose untested terminal/platform boundaries.
6. **Update entry docs.** Synchronize recursive help, README, Chinese/English
   manuals, deployment and validation. Walk through first use: execution location,
   logs, success criteria and recovery.
7. **Commit and deliver.** Inspect staging for artifacts, credentials and raw
   infrastructure logs. Here, submitting code includes commit and push. Verify
   the authorized push against the remote and inspect CI. Clean your temporary
   resources without affecting production. Report change/reason/checks/limits/
   activation; disclose pending CI or CPU-only validation.

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
| project | cluster-local-ai 1.1.0, Python>=3.10, no third-party runtime dependencies |
| project.scripts | Installed local-ai entry point: local_ai.cli:main |
| tool.setuptools | Find packages under src and include profiles.json |
| project.optional-dependencies | dev extra installs Ruff 0.14.2 |
| tool.ruff | Python 3.10 target, 100-character lines and lint rules |

The root Bash launcher adds src to PYTHONPATH and calls the same entry point. Model/GPU engine presets live in profiles.json/profiles.py. See the [command manual](commands.md).


## Documentation delivery requirements

Documentation correctness is a delivery condition. For every implementation, default or documentation change, carefully review both languages of README, command, deployment, offline, architecture, development, performance exploration and validation documents. Confirm unchanged documents do not conflict. Fixing one matching line is insufficient.

1. **README is the entry point.** Walk the first-use path: prerequisites, source download, installation, configuration, startup, readiness, logs, client usage and migration links. Include necessary steps without hidden assumptions.
2. **Match actual behavior.** Check options/defaults, saved settings, execution host, output and exit codes against --help, implementation and evidence. Distinguish program, runtime data and private user state.
3. **Keep examples consistent.** Main workflow: GPU001, bcm-headnode, /raid/local-ai, a and 18000. Introduce b/18001 only in the two-instance section, with both server/client commands. Explain changes of host, path, user, model or address before using them.
4. **Make steps executable.** State host, user and working directory, input/output files, logs and success criteria. An endpoint saved by install is optional for chat. Explain invocation overrides versus persistent settings. Check quotes, ordering and prerequisite files.
5. **Keep concise responsibilities.** README owns one complete main path; deployment expands special cases/recovery; the manual owns parameters. All complete export/transfer/import procedures belong in the offline guide, which retains two independently executable routes; README explains source/target roles and links there. Link to sections instead of copying whole workflows or appending duplicate sections.
6. **Synchronize languages.** Match hosts, paths, ports, defaults, sequence and validation scope. Date historical records and label old behavior; do not present it as current installation guidance.
7. **Check every reference.** Verify relative links, anchors, source URLs and version status. Fix references when removing tags/changing headings. Clearly state development status without treating a source version as a stability promise.
8. **Review before delivery.** Run existing documentation contracts for Bash syntax, CLI examples, links and option coverage, then manually read workflows and bilingual differences. Automated checks do not replace semantic review. State reviewed scope, inconsistencies fixed and unverified items in the commit description; fix conflicts before committing.

## Setup and checks

Runtime code uses Python's standard library only. Optional developer tools belong
in a project virtualenv, not OS-managed Python:
```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check src tests scripts
.venv/bin/ruff format --check src tests scripts
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

## Performance investigation handoff

Keep optimization rationale, tested engine settings, failed approaches and follow-up questions in the [exploration record](performance.md). Keep measurements in validation.md and operational commands in deployment.md. Update these together when experiments change a decision; preserve SGLang findings even while vLLM remains the only managed engine.

## Inference warmup changes

Keep model-specific speculation and graph sizes in the profile, not global engine defaults. warmup.py runs only after explicit server warmup or start --warmup. Imports, plan, status and install must never trigger synthetic inference. Status reads warmup.json and verifies spec fingerprint and container StartedAt.

Changes must cover partial failure, deadline/cancellation, duplicate warmup rejection, wrong deployment metadata, exact API token counts, and stale records after restart. On allocated GPUs compare identical streaming payloads in separate processes/caches, with and without explicit warmup. Measure first requests as well as warmed requests, preserve production, and record cache reuse separately from in-memory graph reuse. Do not describe finite coverage as eliminating all JIT. See [validation](validation.md) for evidence.

## Testing and review rules

- Keep inventory-based plan generation deterministic and free of subprocesses/writes.
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

## Model and client compatibility

The default DeepSeek recipe is not a model allowlist. profiles.json stores models
with repo/revision, model_directory, served_name, image, engine_options,
environment and client capabilities. default_model selects the client default;
hardware profiles reference a model. Profile engine_options override model
options; objects/arrays become JSON, true emits a flag and false/null omits it.
Listener, port, model path and TP remain managed. DeepSeek parsers, Engram and
reasoning metadata belong only to its recipe.

Copy the bundled catalog, add a model/profile and select your file:

```bash
export LOCAL_AI_CATALOG=/home/alice/local-ai-profiles.json
./local-ai profiles
```

Use a distinct model_directory for each model/revision. Each contains its own
model.lock.json; matching legacy root locks remain readable. chat --model
selects another OpenAI-compatible model. Declare reasoning, tool_call,
interleaved and limit in its client metadata. Unknown models do not inherit
DeepSeek metadata. New recipes do not inherit previous hardware validation.

Downloading currently uses Hugging Face snapshots; validation covers indexed
sharded safetensors and serving uses vLLM. Other formats/engines need adapters.
Generating a configuration does not validate hardware or model tool calls.

There is no runtime client-version allowlist. With no --version, installation
reuses the installed release or detects the imported binary's version. Only a
first online download uses the reference release. Explicit versions, local
binaries and offline archives remain available. Test candidates separately:

```bash
PYTHONPATH=src .venv/bin/python scripts/check-client.py --client-dir /home/alice/client-candidate
```

This checks native session HTTP APIs, public JSON, resume and terminal
mouse/paste modes in temporary state without GPUs or inference. CI checks the
reference release; manual workflow client_version selects candidates.
Also verify actual terminal copying, model tool round trips and history
migration. Exit clients and back up history before switching. Restore the
original backup when downgrading across incompatible database migrations.

## Delivery and version labels

Deliver development source from main and exact commits. Existing v1.0.0/v1.1.0 tags have been withdrawn; the source version is not a stability promise. Tests and CI are basic requirements, not automatic release readiness. Do not create tags or GitHub Releases without an explicit user request.

For routine delivery, review implementation and all documentation, validate appropriately, commit/push, and verify the remote commit/CI. If a formal version is explicitly requested later, assess complete installation paths, documentation consistency, compatibility and known issues first. Only then align versions/evidence and tag the exact successful CI commit. Exact commits remain available for reproduction and rollback.

## Directory installation implementation

paths.py uses the launcher location, not cwd or a fixed /raid/local-ai. Explicit --data-dir and LOCAL_AI_DATA_DIR remain compatible. deployment.py prepares assets in place and records relative settings. bundle.py streams program/model/image/client exports with archive and per-file SHA256. config/catalog.json carries recipes. Use ordinary source directories without hidden versions/symlinks. Exclude dist/ and private state. Installation does not start GPUs; new hosts recreate instances with local GPUs, ports and endpoints.
