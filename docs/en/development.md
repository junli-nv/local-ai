# Development workflow

## Synchronize the remote baseline before every change

Before starting code, test or documentation changes, identify the actual Git checkout, branch, commit and working-tree state, then fetch current origin code and tags. Local tags or an installed program version do not establish the latest remote version. Record the baseline commit; recheck when resuming long work or collaborating across people or machines.

1. Inspect git status --short. Preserve existing changes and untracked files in a private backup or separate worktree. If stashing, retain its ID until application and validation succeed. Never overwrite another contributor's edits or force a pull.
2. Fetch remote code and tags. This example assumes a clean development checkout already on main; do not apply it blindly to an installation with unresolved edits:

```bash
git status --short
git fetch origin --tags
git merge --ff-only origin/main
git log -1 --oneline
git tag --list --sort=-version:refname
```

3. If main cannot fast-forward or a feature branch is behind, inspect the differences and merge or rebase according to the branch relationship. Resolve each conflict while preserving upstream additions and the requested change. A failed synchronization does not make a stale checkout suitable for release.
4. Recheck implementation, documentation and tests on the updated baseline. Results from before the merge do not validate the combined code.
5. Fetch again before committing, pushing or tagging. Check remote branches and existing tags, increment from the actual remote version, and integrate concurrent updates with another regression run. Never force-push main or reuse/move old tags.

### Review and regression before pushing

Review changes before committing and releasing. Exercise normal behavior and the full failure, retry, recovery, and subsequent query sequence through the affected entry points. For persisted state, check upgrades with old records and invalid caches, and compare CLI results, stored state, and both language guides. Fix reproduced findings and add regression coverage in the same batch before pushing the verified changes.

## Required version and artifact checks for every release

Keep language navigation immediately below the README titles. Use the README for current capabilities and instructions, with the current version, download commands, and release notes link in the installation section. Record changes in the notes for each release.

1. Confirm the target in src/local_ai/__init__.py and pyproject.toml. Review both languages of README, commands, deployment, offline, rich documents, architecture, development, performance, updates, templates and validation.
2. Align current source URLs, --version arguments, archive filenames and prose; updating README alone is insufficient. Preserve dates/versions in historical acceptance, explicitly saying "at that time". Released features must not remain described as development-only.
3. Run tests/test_doc_versions.py, scripts/check_release_docs.py --archive SOURCE_ARCHIVE and existing documentation contracts for CLI examples, Bash syntax, links, anchors and bilingual workflows, CI builds a source archive from HEAD and verifies its manuals; follow with manual review.
4. After commit and successful CI, build source/wheel artifacts from that exact commit. Inspect packaged documentation and observer.mjs, not just the checkout. Verify tag targets, Release assets and SHA256SUMS; download assets and check hashes.
5. Match installed documentation to the release commit. Only when the user explicitly requests revising an existing release, record old/new commits, revalidate and synchronize tag, source assets, checksums and notes. Retagging requires authorization and concurrency protection against the old tag object; never replace it silently.

## v1.4.0 client regression entry points

Beyond unittest/Ruff, run scripts/check-client.py, check-reasoning.py, check-instructions.py and check-observer.py
with --client-dir DIR for diagnostics/supervision/context changes. The observer mock validates native tools, resume,
usage and compaction hooks, not model quality. Explicitly run the three client workflow cases for real-model acceptance,
keeping private outputs out of Git. Preserve unknown values, incomplete streams/tools, overlapping spans, signal cleanup
and version-isolation coverage. Include observer.mjs in source, wheels and program updates without requiring standalone Node.js.

Additional decision (2026-11-17): keep general/BCM templates and setup guidance together in templates/opencode/, with English under en/. Since v1.4.3, client installation applies general rules by default; standalone updates/exports still only carry templates. client.prepare resolves personal rules before config isolation and explicitly loads them; personal files stay outside Git and bundles. See [persistent instruction setup](../../templates/opencode/en/agent-instructions.md). The general template follows direct user requests without imposing a default response language; user attribution requires original-message evidence, with summaries or indirect records identified as such. Long-task guidance calls for updates on stages/status changes, reasonably segmented waits, combined repetitive information and log files for large outputs, without fixed timing, line counts or a timer guarantee. Exit and restart OpenCode after installation applies or you edit personal rules.

[中文（默认）](../development.md)

## Developer handoff: decisions and working order

Pending requirement (2026-11-18): retain OpenCode and improve follow-ups, side questions, pause and stop handling during execution. Isolated API/TUI measurements and the managed execution adapter are now authorized and implemented. See [new-message responsiveness](client-steering.md) for objectives, execution, interpretation and future acceptance; see [managed execution](execution.md) for local task usage; no Codex migration is made.

Additional decision (2026-11-18): independently adapt task scope, actual verification, authorized continuity and outcome-first communication from a third-party Claude Code prompt collection and official best practices. Pin sources and map each adaptation in [prompt references](prompt-references.md). Do not import complete external prompts or Claude-specific mechanisms, change the general-assistant role/permission boundaries, or resume deferred async execution. Prompt installation/context checks do not establish better model performance.

These requirements were progressively agreed with the project owner on
2026-11-01. They guide product development, not restrictions on assistant tasks.
Update decisions, implementation and user docs together when requirements change.

### Shell completion decision

Commands and options are difficult to remember. `completion bash` derives subcommand, option
and fixed-choice candidates from argparse and the current catalog; Bash completes paths.
It is read-only, performs no hardware/network probes and never edits user startup files.
Currently supports Bash 3.2+; runtime dependencies remain standard-library-only.

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
| Prepare other platforms on any CPU | prepare targets profile images/models using standard-library HTTP weights; never execute foreign images or probe GPUs. Retain target install architecture checks; list profiles explicitly at export. |
| Develop before GB200/Rubin hardware is available | Add only an ARM64 GB200 TP4 candidate. Evaluate Rubin TP2 with CPU Engram from its 288GB/GPU nominal capacity, retaining a planning-only framework and unresolved image/memory guards. Mark fixtures synthetic; pure plans must not probe hardware or write files. Preserve existing recipes and acceptance levels |
| Pull failure appears to mean missing image | Separate expected inspect absence from pull failure; show actual error and full log path. Missing metadata.db concerns Docker/containerd storage |
| Share image/model materials | Share weights/export archives separately from active databases. --data-dir does not move Docker/containerd storage. Validate new storage schemes |
| BCM already reaches GPU | Use API endpoints; built-in model SSH tunnels and their old doctor are removed; v2 doctor is local aggregate diagnostics. External frp/nginx handle forwarding; operational SSH remains available |
| Connect via host IP | Explicit --host; 0.0.0.0 binds, while endpoints use a real host/IP. Preserve existing network/listener settings |
| Container runs without visible progress | Show logs and startup/loading/readiness/failure. READY requires health, not docker ps, a port or blank curl output |
| Unclear logs/status | install.log for preparation; instances/NAME/server.log for runtime. Clear messages, management JSON stdout, batch text by default, progress stderr and meaningful exit codes |
| Native resume loses context | opencode -s ID restores the associated endpoint and original project/private state using public metadata, handling empty lists and project scope without private database tables |
| Application copying fails | Default terminal selection/copy/paste; disable application mouse/clipboard shortcuts. Explain disabled click/wheel behavior and verify terminal modes |
| Fixed release blocks upgrades/offline use | Reference releases are validation records, not runtime allowlists. Reuse installs, detect imports, allow explicit releases/offline exports and test capabilities |
| Models/revisions change | Configure recipe identities, directories, names, engine/client capabilities and separate locks; do not inherit hardware acceptance or DeepSeek-specific settings |
| Directory installation and migration | The unpacked directory is the root, with ordinary src/. install prepares assets in place; export writes a complete dist/ bundle excluding dist/, instance state, histories and credentials. Reinstall/reconfigure after moving |
| One BCM, multiple model services | Initial endpoint is optional; config saves defaults and chat --endpoint/--model override one invocation. User-private history is independent of server and installation paths, including ad-hoc routes. Preserve session project directories. Inspect legacy records with client history list and associate once if needed, without database copies, nonempty-history merging, model guessing or endpoint fallback |
| Source-script delivery | Synchronize remote main and tags first. The user requested the v2.0.0 managed execution, portability and batch tag, preserving prior tags. Future tags still require explicit requests and a CI-passed commit; no automatic Release |
| Single-user speed and first-use compilation spikes | Keep the baseline unchanged; opt into DSpark and explicit bounded warmup. Separate API READY from WARMUP COMPLETE, persist compiler caches per recipe, invalidate completion on restart, and report actual coverage and concurrency tradeoffs |
| Around 400 ms TTFT seems high | Record method, input size, cache/load and timing first. Separate compilation, generation delay and reasoning content; avoid one-number conclusions |

Use the [manual](commands.md) and [deployment guide](deployment.md) for operations;
this section records design reasons.

### Current backlog state (2026-11-19)

- v2.0.0 includes updater activity checks, explicit program-only continuation and standalone rollback; history backups remain separate.
- Implemented: automatic interactive Bash backgrounding, owned task/session control, PTY/input/adoption, automatic completion messages, SSH/Slurm/container adapters, private history backup/restore/select and combined doctor.
- Batch defaults to text, with explicit --format json compatibility. Files/stdin provide one prompt source. Keep these contracts in both languages and real source archives.
- Actual-model controls, notifications and relocated-history continuation passed on BCM/HGX260. Native mock checks cover API/TUI timing and permission preservation; real CPU SSH/Docker/Slurm controls were verified. This is functional coverage, not a latency SLA or GPU performance acceptance.
- KV offloading and tar extraction remain low priority. Remote PTY, reboot replay and arbitrary TUI reattachment are not implemented.
- The user requested major tag v2.0.0. Fetch before edits and again before publication; tag the exact CI-passed commit, preserve old tags, and do not create a Release automatically.


### Low-priority backlog: KV cache offloading

Decision on 2026-11-17: defer integration. See [exploration](performance.md#kv-cache-offloading-low-priority-backlog-2026-11-17) for review triggers and validation steps.

### Low-priority backlog: faster tar offline imports

On 2026-11-18, the user reported slow offline tar extraction and preferred retaining tar while improving import speed later, at low priority. The user clarified that expanding the outer archive into the target directory is the main delay. Prioritize that stage, measuring source reads, target writes and decompression CPU separately for uncompressed .tar and .tar.gz. Verification and Docker image load are comparison stages, excluded from extraction timing. Then consider reduced duplicate I/O or compatible improvements without skipping integrity/image-identity checks. Research SquashFS only as an option with explicit tooling, mount and read-only-layout costs; do not introduce third-party dependencies or change offline defaults. This records the request without modifying export/import code or benchmarking large resources.

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

Additional decision (2026-11-16): provide `server benchmark --name a` on the GPU server, using its local API
and managed instance settings to measure deployment performance after a small warmup. Validate logic with a CPU mock API;
real GPU acceptance is separate. Deployment results do not rank GPUs independently, first chunks are not exact first-token
timestamps, and request output rates are not pure decode throughput.

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
6. Route installation diagnostics through installlog.py, keeping management JSON stdout separate from progress stderr, with explicit JSON mode for batch. Expected missing-object probes are not installation failures.
7. Validate local artifacts; distinguish verified and unverified provenance without fabricating locks. Preserve both archive checksums and imported-image content identity.
8. Run the unittest, Ruff and diff checks below. Fix failures without deleting or weakening existing acceptance tests.
9. Record hardware/version/method/results/limits for real GPU tests. CPU tests alone never promote a hardware validation level.
10. Review staged files, record release evidence, clean temporary containers/client-processes/resources, push and inspect CI.

Separate B200 TP4 profiles and the sanitized tests/fixtures/b200-tp4.json inventory now have bounded four-GPU API smoke acceptance; see validation for limits. Use the same workflow for later hardware. Do not relabel validated profiles.

## Reasoning variants during a session

The requested behavior preserves original defaults while allowing live user selection. Use model client.variants and native OpenCode Ctrl+T without adding local-ai flags or saved defaults. The normal variant must be an empty override; model-specific fields belong only to models declaring that recipe. Native SDK-generated variants merge with configuration, so disable unsupported medium/minimal and verify all actual request thinking fields.

Run PYTHONPATH=src python3 scripts/check-reasoning.py --client-dir /path/to/client. It uses temporary HOME/state, a local mock model and the native client to verify seven same-session variant requests, normal restoration and the next request after PTY Ctrl+T input. All temporary processes are cleaned up. It invokes no real GPU and proves no latency or answer-quality improvement. CI client-contract runs the same check.

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
| project | cluster-local-ai 1.4.4, Python>=3.10, no third-party runtime dependencies |
| project.scripts | Installed local-ai entry point: local_ai.cli:main |
| tool.setuptools | Find packages under src and include profiles.json |
| project.optional-dependencies | dev extra installs Ruff 0.14.2 |
| tool.ruff | Python 3.10 target, 100-character lines and lint rules |

The root Bash launcher adds src to PYTHONPATH and calls the same entry point. Model/GPU engine presets live in profiles.json/profiles.py. See the [command manual](commands.md).


## Documentation delivery requirements

Documentation correctness is a delivery condition. For every implementation, default or documentation change, carefully review both languages of README, command, deployment, offline, architecture, development, performance exploration, update and validation documents. Confirm unchanged documents do not conflict. Fixing one matching line is insufficient.

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

## Local benchmark development boundary

`benchmark.py` runs only through explicit `server benchmark`, never through import, plan, status, install or start.
After validating managed metadata, it uses local `/tokenize` and streaming `/v1/completions` with fresh prefixes to reduce cache reuse.
It neither clears caches nor changes recipes or starts/stops containers. It shares the instance warmup lock, without isolating business traffic.
Defaults are concurrency 1, 1024/256 tokens, one warmup round and three measured rounds. Reports bind to the spec fingerprint and container start;
a restart fails the run. Tokenization/warmup are excluded from measured summaries; API usage must match exactly, including special/reasoning output tokens.
Separate JSON records use permissions 0600 under the instance directory, excluded from Git/exports. They do not change warmup.json or status claims.

Use a temporary stdlib HTTP server to test streaming timing, concurrent wall-time denominators, partial failure records, timeout/cancellation cleanup and restarts.
CPU mocks establish tool logic only. Real API compatibility/performance requires allocated GPUs as described in [validation](validation.md).
See [local performance benchmark](commands.md#local-performance-benchmark) for metric definitions, defaults, exit codes and execution location.

## Testing and review rules

- Keep inventory-based plan generation deterministic and free of subprocesses/writes.
- Test rejected states and cleanup, not just a happy-path command.
- Require image config/layer identity after import; a tag alone is insufficient.
- CPU fixtures explicitly simulate the target recipe architecture. Port tests respect OS binding semantics: verify real conflicts across platforms and retain cross-interface conflict coverage on Linux.
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

Historical v1.4.4 work requested a new tag for general-template updates, prompt-source documentation and the message-response baseline probe. The development baseline is 97a8e25 and the latest existing remote tag is v1.4.3; preserve prior versions. Offline tar extraction optimization remains a low-priority follow-up.


The user requested committing, pushing and adding the v1.4.1 annotated tag; this does not automatically create a GitHub Release. Retain the v1.4.0 and historical v1.3.7 tags and acceptance records. The v1.4.0 GitHub Release was withdrawn at the user's earlier request; withdrawn version tags are not reused. Development continues on main/exact commits, with support limited by the validation record. Tests and CI are basic requirements; future tags require an explicit user request and do not automatically create GitHub Releases.

For routine delivery, review implementation and all documentation, validate appropriately, commit/push, and verify the remote commit/CI. For an explicitly requested version, assess installation paths, documentation consistency, compatibility and known issues. Align versions/evidence and create an annotated tag on the exact successful CI commit. Exact commits remain available for reproduction and rollback.

## Program updater maintenance

The standalone scripts/update.py must use only Python 3.10+ standard library and must not import target installation modules, execute install/Docker/client commands, or read/hash model shards. Keep its program-path allowlist separate from resources and custom catalogs. Preserve settings permissions/defaults, retire stale bundle receipts, keep backup format compatibility, and test source-only offline updates, malformed archives, rollback, partial failure and unchanged resource inodes. The helper remains in scripts/ when a target tag predates it, so existing source export includes it. Program upgrades do not automatically move tags. An explicitly requested retag must record the old target and newly validated commit; the earlier v1.2.0 retag included the updater at the user's request. Full operations live only in the [update guide](update.md).

## Directory installation implementation

paths.py uses the launcher location, not cwd or a fixed /raid/local-ai. Explicit --data-dir and LOCAL_AI_DATA_DIR remain compatible. deployment.py prepares assets in place and records relative settings. bundle.py streams program/model/image/client exports with archive and per-file SHA256. config/catalog.json carries recipes. Use ordinary source directories without hidden versions/symlinks. Exclude dist/ and private state. Installation does not start GPUs; new hosts recreate instances with local GPUs, ports and endpoints.

## Rich-document development

Keep ordinary chat as the entry point: users name a file or directory, and the assistant calls documents_read_document; do not add mandatory attachment flags. Keep parsing on BCM, preserve source labels, paginate explicitly, expose real errors and test native MCP image transport. Use random hidden codes for end-to-end PDF/image/Word/Excel/PPT checks. Record text versus rendering support separately; do not claim Codex parity from extension names.

## Maintaining managed execution

execution.py uses only Python stdlib; execution.mjs reuses the existing native SDK. Ship both in source, wheel and program updates without requiring a separate Node installation. Each running job uses a copied worker; upgrades retain that copy. Keep task schema/RPC backward compatible. Never delete private task state or treat program rollback as task cancellation.

Beyond full tests/Ruff, run check-steering.py in default and --managed modes, plus check-execution.py controls/denied. Preserve the synchronous baseline and native permissions. Cover stable keys, replay prevention, process identity, failed startup checkpoints, pause gates, confirmed stop, worker loss, output truncation and terminal exit. Client-contract CI retains private fixture evidence.

Real-model control/notifications/history relocation and real SSH/Slurm/container cancellation are recorded in v2.0.0 validation; strict airgap remains unverified. Mock API results alone do not establish live behavior. Synchronize [usage](execution.md), commands, architecture, offline and validation in both languages, explicitly distinguishing v2.1.3 from old tagged downloads.


v2.0.0 maintenance: retain each adapters.py controller copy with its task. Ship batch/portability modules in source and wheels. Recheck enhanced, policy and authorized live-model acceptance, including stable notice IDs, relocated project use, input idempotency and backend identity. Never upload private archives to CI or public packages.


### Post-v2.0.0 follow-up

Implemented in v2.0.1: exact unmarked-template migration with backups, chat argument intermixing, explicit verified adapter recovery and bounded terminal output caches. Create v2.0.1 as requested and preserve v2.0.0. The backlog below is recorded, not implemented in this delivery. Actual SSH recovery on HGX260 and injected transport failure passed; this is not physical network-isolation or cross-version database migration acceptance. Those, long-duration stress and remote PTYs remain separate follow-ups.

## Deferred backlog (2026-11-19)

The user considers these non-urgent. Record them for later work; none blocks v2.0.1.

| Item | Future acceptance |
|---|---|
| Real Slurm/container recovery | Exercise new recover paths after controller loss, original identity, single submission, terminal facts and complete cached output; prior basic controls do not establish this |
| Strict offline operation | Isolate networking and clear dependency caches for preparation/install/chat/migration; distinguish real disconnection from injected transport errors |
| Cross-OpenCode-version history migration | Design explicit compatibility checks, backups and rollback; restore currently requires matching native versions |
| Long-duration concurrent sessions | Check pause/stop races, completion messages, resource use and large-log coverage |
| Completion notifications with chat closed | Evaluate an independent mechanism; current notifications require a running chat |
| Remote PTYs and arbitrary existing TUI reattachment | Evaluate separately; local PTYs and monitor recovery do not provide these |
| KV cache offloading | Low priority: measure actual long-session benefits and pinned-engine compatibility before considering an optional startup setting |
| tar extraction time | Low priority: retain tar and measure verification, extraction and import separately before optimizing |

This delivery packages verified fixes as v2.0.1, pushes a new tag and updates BCM. Preserve old tags; do not create a GitHub Release automatically. See [release notes](release-2.0.1.md).

## v2.1.3: completion deduplication and BCM PDFs (2026-11-23)

Retain automatic continuation. Once complete task output reaches the model, only show a completion/warning toast; never insert an event that prompts a redundant reply. Persist contiguous read cursors per private task; inspect the latest 100 real tool messages for older state. The BCM template prioritizes /cm/shared/docs while excluding /cm/images. Poppler remains the PDF default; optional pypdf runs as an external text backend in a separate environment, keeping the application stdlib-only. Explicit document setup-pdf prepares a private user venv, with --wheel-dir for offline installation. Reading/doctor never installs or accesses package indexes. Without a renderer, auto warns that it returns text only; this does not validate scans or diagrams. Setup logs use private document-tools/install.log, progress stderr and result JSON stdout. These development changes are absent from the original v2.1.2 tag; this release is explicitly requested, with a new tag and GitHub Release while preserving older tags.
