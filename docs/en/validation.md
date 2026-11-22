# Validation record

## v2.1.1 OpenCode input cursor

The session resume test checks that the generated `tui.json` selects a vertical cursor and disables blinking. Visual behavior during Chinese IME composition has yet to be tested.

## v2.1.0 client metrics sampling

Five scrapes of the HGX260 vLLM metrics endpoint from BCM succeeded at two-second intervals. The command exited after about eight seconds.
The service was idle during the live check, so latency was reported as having too few samples.
Regression fixtures cover queueing, cache hits, preemptions, counter resets and failed scrapes.
Tests also check the English default and explicit Chinese output.

## v2.0.3 interactive exit verification

On BCM, OpenCode 1.19.5 passed a disposable PTY check for Ctrl-C, a project path with spaces, and replay of the displayed resume command. The installed client also opened and resumed an existing session twice without sending any messages. The message count was preserved. All 342 unit tests, Ruff and bilingual documentation contracts passed.

## v2.0.1 tag preparation (2026-11-19)

Based on remote main fef6db9, this delivery packages its verified fixes and changes only version/documentation, recording deferred work without new features. BCM Linux/Python 3.12 passed all 337 unit tests and Ruff checks/format. All 56 manuals and 30 current-version references agree; documentation contracts cover CLI examples, relative links and Bash syntax. The update guide's stale version=1.4.4 output text was also corrected.

Native-client, actual SSH and model evidence remains in the following section. Require complete CI on the new commit before tagging, then verify the actual tag source archive and wheel. The BCM update retains active clients, personal configuration, native binaries and history without restarting inference. Real Slurm/container recovery, strict offline, cross-version migration and long-duration stress remain unverified backlog items.


## Post-v2.0.0 main follow-up (2026-11-19)

CI caught a timing assumption in the controls probe: it checked the marker immediately after a Bash tool returned, although Bash can return an asynchronous job ID. The probe now deliberately backgrounds that resumed command, waits for its exact job ID to reach successful terminal state, and checks exact file content, retaining all pause/permission/single-execution assertions.


The controls fixture disables unrelated automatic completion prompts using the supported setting; enhanced separately validates notification delivery. The forced asynchronous resume path passed repeated native runs.

337 unit tests, Ruff lint/format, documentation CLI examples and current-version checks passed. Native OpenCode 1.19.5 enhanced/policy cases passed with automatic completion delivery and compound-command permissions preserved.

The actual previously duplicated BCM AGENTS backup was migrated in isolated configuration: two exact copies removed, selected general+BCM content retained, repeat application unchanged. Tests also preserve edited rules, fenced examples, CRLF and private backups.

scripts/check-recovery.py ran against HGX260 with a short CPU-only SSH command: kill local controller, inject a transport exception, recover concurrently, retain one monitor/original remote ID, execute once, confirm completion and read complete cached output with all SSH calls forbidden. Temporary test files were cleaned. Transport failure was injected in the client, not a physical network outage. Partial/gapped/changed cache, unknown submissions and cancellation before submission are separately covered by tests.

Real-model batch text and JSON runs with options before the positional prompt passed in isolated state against the existing HGX260 API. No inference restart or new GPU allocation. Raw evidence remains private on BCM; strict air-gap, long-duration stress and cross-OpenCode-version history migration remain unverified.


## v2.0.0 client acceptance (2026-11-19)

Environment: BCM Linux AMD64, Python 3.12, native OpenCode 1.19.5; existing HGX260 DeepSeek-V4.1-Flash API. Private isolated histories/projects were used; production sessions were not used as fixtures.

- scripts/check-live-execution.py: actual model passed follow-up during task, heartbeat freeze on pause, explicit same-task resume, confirmed stop, command once, automatic completion summary, same-session history restore and relocated-project read. The current-project context correction was tested after reproducing old-directory access. Native permission confirmation remains required for new paths.
- Actual SSH and CPU-only prepared Docker image on HGX260, plus a one-CPU/128-MiB Slurm job: start, pause, resume, stop from paused state, complete output and cleanup passed. No inference restart or GPU allocation.
- Real-model workflow regression: edit-test, diagnose and resume passed; resume used the same session and appended exactly once.
- Batch: UTF-8 file/text, stdin/text and stdin/native JSON passed with the real model; readable text fed another program.
- Native mock cases controls, denied, enhanced and policy passed, including permitted commands and compound-command denial. API/TUI timing is functional evidence, not a real-model latency promise.
- Unit coverage includes PTY/input idempotency, owned-group adoption, notice leases, private snapshot safety, backend identity checks and incomplete accounting. Packaging/docs checks compare actual source archives with current manuals.

- Final local regression: 329 tests passed plus Ruff lint/format. A complete private BCM snapshot of four histories was restored into isolated state with all 38 original session IDs retained, including pre-endpoint tunnel launch records.

Private raw evidence is retained on BCM under the acceptance workspace, not published. Offline/air-gap behavior, other synchronous tools, arbitrary TUI reattachment and reboot replay are not established. GPU profiles and performance conclusions retain their earlier acceptance scope below.


## Development main: updater protection and candidate client (2026-11-19)

All 298 local unit tests, Ruff lint/format and source-archive documentation checks pass. The 21 targeted updater tests pass, covering read-only checks, real Linux process detection/liveness, similar-path boundaries/environment privacy, clients starting during unpack, explicit continuation, active rollback refusal and standalone recovery with installed launcher/scripts removed. Resource contents/inodes are preserved; program backup is not called history backup.

The initial CI fixture renamed system sleep to opencode; the runner's multicall coreutils binary exited under that name, failing detection. Replace it with an installation-owned Python launcher and readiness marker, retaining real process/liveness assertions rather than skipping the case. This was not a Python-version or product detection failure.

Same-host OpenCode 1.19.5/1.19.6 API/TUI all measured after_tool: follow-ups reached the model about 5.08–5.11 seconds after submission, after the five-second tool completed. Retain the active version; upgrading alone did not solve delivery. See [candidate comparison](client-steering.md). This does not validate natural-language pause/stop, airgap operation or GPU behavior.

## Portable local test fixtures: 2026-11-18

Synchronized remote main bcc35e4 and latest tag v1.4.4 before editing, then reproduced both existing failures. Port tests no longer require a configured 127.0.0.2 on macOS. Actual checks also showed macOS permits overlapping specific/wildcard binds with SO_REUSEADDR. All platforms now verify a real wildcard listener conflict; Linux retains the original cross-interface scenario. Add a check that the selected address reaches bind. The offline server migration test explicitly simulates its AMD64 fixture architecture, retaining assertions for renamed import paths, no downloads and no GPU startup. Production port checks and architecture validation are unchanged.

Local macOS ARM64/Python 3.14 ran all 289 unittest cases: 288 passed, only the optional FFmpeg test skipped, and no errors or failures. Ruff lint/format, documentation versions and patch checks are separate delivery checks; CI after push verifies Linux branches. Manually reviewed bilingual development guidance and validation records. README, commands, defaults and installation/update/offline behavior are unchanged; no version or tag changes.

## v1.4.4 tag preparation: 2026-11-18

The user explicitly requested a new tag and push. Synchronized remote main 97a8e25 and tags before editing; the latest existing tag was v1.4.3. Synchronize runtime/package versions, README, online/offline update examples, bilingual release notes and template-version guidance without moving historical tags. Scope includes earlier general-template adaptations, prompt sources under docs/ and the isolated responsiveness probe; neither immediate responsiveness nor faster tar extraction is implemented.

Local macOS ARM64/Python 3.14 ran all 288 unittest cases: 285 passed, one optional FFmpeg skip and two existing platform errors (127.0.0.2 binding and an AMD64 server fixture). Ruff lint/format, version checks across 48 documents and git diff --check passed. Manually reviewed bilingual entry points, defaults, installation/update/offline workflows, examples and links. Linux tests and native-client checks must pass CI after push before tagging the exact commit. Release checks also require building and inspecting source/wheel artifacts from that commit and verifying the downloaded GitHub tag archive. No GitHub Release is created.

## OpenCode in-flight message baseline probe: 2026-11-18

The user approved isolated measurements and recording follow-up requirements, not native-client modifications or a general async system. Synchronized main 196a19b and tag v1.4.3 before editing. scripts/check-steering.py starts a loopback mock API and temporary native session, then submits follow-ups through the API and real TUI input. Record command start/end, submission, observed backend persistence, first main-session model request and observed mock acknowledgement, verifying exactly-once command execution. Configuration, history and files are isolated; no real model/GPU requests or personal configuration changes. CI retains evidence. state=measured does not mean immediate responsiveness is achieved.

Local macOS ARM64/Python 3.14 ran 288 unittest cases: 285 passed, one optional FFmpeg skip and two existing platform errors (127.0.0.2 binding and an AMD64 server fixture). Nine new cases cover persistence versus model delivery, missing evidence, title-request exclusion, fixed commands/path quoting, failure reports, invalid parameters and after_tool not implying success. Ruff lint/format, documentation contracts, version references across 46 documents and patch checks passed. Linux native API/TUI measurements run in CI; this does not extend acceptance to live-model understanding, stopping behavior or disconnected operation. See [message responsiveness](client-steering.md) for bilingual requirements and probe interpretation.

Native Linux AMD64/OpenCode 1.19.5 measurements completed at 6020cdd after fixing the initialization timeout. CI 44326930925 passed all checks and retains the steering-probe artifact. API/TUI first observed stored messages about 0.070/0.242 seconds after submission, but model delivery took about 5.006/5.023 seconds, after the five-second command. Both classified after_tool; commands executed once and messages/mock acknowledgements were complete. The baseline probe is complete; immediate responsiveness is not implemented. No raw logs are committed. See the requirement page for events and scope; the first session-creation timeout preceded measurement and is not a product conclusion.

Also clarify that Claude-derived changes are in commit 8855c7d's general templates: authorized continuity, Changes and verification, and outcome-first reporting. BCM templates are unchanged. These commits postdate the published v1.4.3 tag and are absent from its archive. Preserve the existing version/tag without repacking it.

The user subsequently requested retaining tar and improving outer-archive extraction speed at low priority (the user clarified this is the main delay); recorded in the development backlog. Read-only review confirms bundle.py defaults to uncompressed tar with optional gzip, while offline workflows also verify archives/files and import images. No SquashFS format change, skipped verification or real-resource performance claim is introduced.

## Move prompt references into docs: 2026-11-18

At the user's request, move both prompt-references.md files from templates/opencode/ to docs/ and docs/en/, updating setup/development entries and internal relative links. Preserve sources, pinned commits and adaptation mappings. Actual AGENTS templates and install/chat code are unchanged; reference documents are not loaded at runtime and trigger no network download. Synchronize remote main 8855c7d before editing.

Local macOS ARM64/Python 3.14 ran 279 cases: 276 passed, one optional FFmpeg skip and two existing platform errors (127.0.0.2 binding and an AMD64 server fixture). Ruff lint/format, version checks across 44 documents, documentation contracts and patch checks passed. Reviewed bilingual entry points and moved relative links. No personal configuration changes or moved version tags.

## Claude Code prompt references and general-template adaptations: 2026-11-18

Synchronized remote main 5c56813 and tag v1.4.3 before development. At the user's request, located third-party Claude Code prompts, primarily Piebald-AI/claude-code-system-prompts at pinned commit be7338dd7770a426141be50d89aa54fb6cfd62de. Read four files and recorded their individual ccVersion labels, using the official system-prompt overview and best practices for scope and supplementary guidance. Bilingual references map sources to adaptations and distinguish third-party collection, official disclosure, local wording and unverified claims. They do not present the collection as one complete official prompt used in a request.

General templates add reading before changes, bounded scope, actual verification, authorized continuity and outcome-first communication, preserving language, attribution, BCM, permissions and progress guidance. No Claude-specific tools or deferred async/queue work is introduced. Update setup guidance, README entries and developer decisions. These are main-branch template changes after v1.4.3 without moving its tag. Use source containing this change and rerun client installation to update the personal managed block. No actual personal rules or remote systems were modified.

Local macOS ARM64/Python 3.14 ran 279 cases: 276 passed, one optional FFmpeg skip and two existing platform errors (127.0.0.2 binding and an AMD64 server fixture). Ruff lint/format, documentation contracts, version references across 44 documents and patch checks passed. Reviewed both languages, source links, reference versions, main workflows and compatibility with existing bilingual guides. Installation/context checks do not establish improved model performance. No new live-model A/B results were produced; a broad collection guarantees neither model capability nor client mechanisms.

## v1.4.3 automatic personal instructions during client installation: 2026-11-18

Synchronized remote main cfd4da0 and latest tag v1.4.2 before editing. install --role client/both and client install now apply Chinese general rules by default, with --instructions general/bcm/none and --instructions-language zh/en. Installation and chat share personal-path resolution using the actual running user and XDG_CONFIG_HOME, without inferring another account from sudo. Preserve existing content, make private backups before changes and atomically replace the managed block under a lock; unchanged reinstalls do not write. Missing templates, damaged markers, symlinks, other-user files and write failures are explicit errors. Server-only installs, standalone updates and exports do not modify personal rules. Offline installation needs no template download. Test personal paths are isolated in temporary directories.

Local macOS ARM64/Python 3.14 ran 279 unittest cases: 276 passed, one optional FFmpeg skip and two existing platform errors (127.0.0.2 binding and an AMD64 server fixture). All 13 new rule cases and two unified-install role/skip cases passed, covering exact backup bytes, idempotence, preserved outside content, template updates, language/BCM selection, failure preservation and default paths. Ruff lint/format, Bash/CLI/document-link contracts and current-version references passed. Reviewed README, commands, deployment, offline, architecture, development, updates, performance and bilingual templates, retaining historical version statements and GPU acceptance boundaries. Native check-instructions.py now verifies installed templates in model context, backups of prior personal rules and unchanged files during chat through Linux native-client CI. Linux binaries were not run on this host; context delivery does not prove live-model compliance with every rule.

At the user's explicit request, create an annotated v1.4.3 tag on the exact CI-passed commit, retaining existing tags without a GitHub Release.

## General-template waiting and progress guidance: 2026-11-18

Fetched remote main and tags before editing; confirmed baseline 199f702 and latest tag v1.4.2. Both general templates now include the user-approved guidance: reasonably segmented waits, proactive updates on stages/status changes, combined repetitive information, log files for large outputs, continued authorized work after reporting, and accurate job states. No fixed wait duration, reporting interval, line count or heading is required. Blocking tool calls may delay updates; prompts provide no timer guarantee. Align README entries, developer decisions and personal-rule setup guidance. Manually merge the actual personal AGENTS.md and exit/restart OpenCode; templates are not applied automatically.

The complete local macOS ARM64/Python 3.14 unittest rerun outside the sandbox ran 264 cases: 261 passed, one optional FFmpeg skip and two existing platform errors (127.0.0.2 binding and an AMD64 server fixture on ARM64). Initial sandbox errors from denied local mock-API port binding are not product conclusions. Ruff lint/format, documentation contracts (Bash syntax, relative links, CLI examples), version references across 40 documents and git diff --check passed. Reviewed both languages of the rules, setup/restart steps, README flow and the scope of existing command, deployment, offline, architecture, development, performance and update guidance. This changes templates/documentation only, adds no timer and changes no personal rules. Live-model progress-reporting behavior was not revalidated.

## v1.4.2 session/server decoupling: 2026-11-18

Synchronize the development baseline to remote main 53e9050, preserving v1.4.1 and subsequent documentation changes before integrating this feature. All 264 CPU cases, Ruff rules/format and patch checks passed. Twenty-three history cases cover shared saved/ad-hoc routing, user-state isolation, installation-directory changes, legacy recognition, read-only discovery and visible errors, nonempty-target rejection, idempotence and metadata rollback.

Native restore/terminal modes, reasoning variants/Ctrl+T, personal/project instructions in context, observation and compaction passed on Linux AMD64 / OpenCode 1.19.5. Failover uses two local mock APIs: execute a tool on the first, stop it and verify its port is unreachable, then restore the same conversation at a different address. The replacement receives the original user message and tool results; the ledger contains FIRST and SECOND exactly once each. Subsequent compaction passes. scripts/check-observer.py and CI include this scenario in disposable state without real GPU inference.

The real client had 29 old sessions and an empty replacement-address database. Association preserved SHA256, inode and session/message/part counts for all four databases; the old main retained 29 / 4632 / 18097 records. chat --check was ready at the replacement using the original state directory. Public native metadata located the requested old session; resume selected its original project and replacement address, with the final chat invocation mocked and no real inference request. Raw records, session IDs and infrastructure paths remain private.

No database moves, binary upgrades or GPU restarts. Project paths retain work location/session ownership; Linux users provide access isolation, unlike directories within one account. Legacy databases are not automatically merged. Cross-BCM copying, other models and arbitrary future database formats remain unvalidated; unknown formats reject legacy association. Create only the requested new tag after successful CI, retaining prior tags without automatically creating a GitHub Release. See [replacement and recovery](commands.md#replace-a-server-and-retain-sessions).

## Check refresh units before listing CDI devices: 2026-11-18

Checked the automatic-refresh mechanism against NVIDIA's CDI documentation. Both languages now check nvidia-cdi-refresh.service and .path before listing devices in README, prerequisites, both offline routes and future GB200/Rubin acceptance queries; deployment guidance links to the same procedure. Explain successful one-shot inactive (dead), status=0/SUCCESS, enabled/active (waiting) for .path, nonzero status exits and missing units on older releases. README centralizes logs, enabling, refreshing, manual generation and duplicate-definition handling. Offline startup is a separate code block after selected UUID verification. This is a documentation correction with no remote service queries/changes or additional GPU/Toolkit hardware acceptance.

The local macOS ARM64/Python 3.14 suite ran 241 cases: 236 passed, one optional FFmpeg skip and four errors. Two are existing platform limits (127.0.0.2 binding and an AMD64 server fixture); two endpoint cases encounter sandbox restrictions on user state/resume-launcher writes. Existing documentation contracts (Bash syntax, relative links and CLI examples), version references across 38 documents, Ruff lint/format and git diff --check passed. Reviewed new commands, execution locations, status meanings, both offline routes and the README flow in both languages. Runtime implementation and tests were not changed.

## General-template project locations and chat directory: 2026-11-18

The user identified missing project-location and chat-directory sections when copying the general template alone. Local Git history contains neither heading nor the complete paragraphs; /home was mentioned only in the BCM template, while project sizing and native background-read limitations appeared only in the setup guide. The previous language-rule commit did not delete these sections. Add both supplied sections to both general templates and align setup guidance; omit the topic-extension comment as subsequently requested. Preserve BCM discovery scope and authorization limits. Personal AGENTS.md still requires manual merging; no user files are changed automatically. This corrects template coverage without new live-client or model-behavior acceptance.

## Response-language and user-attribution template revision: 2026-11-17

Both general templates now prioritize explicit language requests, otherwise following the user's latest direct request. Logs, quotations, tool output and summaries do not trigger a language switch. When unclear, retain the user's previous direct-conversation language, or ask if none is available; impose no default language. User quotations or paraphrases require original-message evidence, and indirect records must be identified. Update setup guidance and developer decisions. Templates remain opt-in; no personal files, plugins or runtime behavior were changed.

The local macOS ARM64/Python 3.14 suite with a canonical temporary path ran 241 cases: 238 passed, one optional FFmpeg skip and two known platform errors (127.0.0.2 binding and an AMD64 server fixture on ARM64). Ruff lint/format and whitespace checks passed. Initial /var versus /private/var alias assertion differences disappeared with the canonical temporary path; tests were not modified. No new live-model language-compliance test was performed; wording is not an enforcement guarantee.

At the user's request, commit and push, then recreate the annotated v1.4.1 tag on the exact CI-passed commit. The previous tag object is fe2ae72e80d2245152336263cf1ba51584655831, pointing to 2a77608c988bc595c3e7986e5350aa36f0d14461. Protect the remote update by checking that old object. Do not create a GitHub Release, build a wheel or upload release assets.

## B200/GB300 four-GPU hardware status confirmation: 2026-11-17

The user explicitly confirmed successful physical-hardware validation of `b200-tp4-cpu`, `b200-tp4` and `gb300-tp4`. Keep the existing detailed B200 methods/results in the 2026-11-08 record. GB300 TP4 status is based on this user confirmation; no additional environment, workload, performance or raw logs were supplied, so those details are not invented. Align README, deployment/offline guidance and profiles metadata. Retain `gb300-tp2` as unvalidated at the user's request. This does not expand acceptance to GB300 use of B300 DSpark, full-context boundaries, sustained stability or unspecified scenarios. Earlier statements that GB300 was unvalidated describe their historical scope; this section is the current four-GPU status.

## v1.4.1 version label: 2026-11-17

At the user's request, align program metadata and current download/update examples, commit and push, then create a new annotated `v1.4.1` tag on the exact CI-passed commit. Keep the original `v1.4.0` tag and do not recreate its withdrawn GitHub Release. This version includes the offline documentation corrections below and hardware-status updates. Inference parameters, models, images and installation behavior are unchanged. Users still configure npm offline mode explicitly; system startup files are not written automatically.

The complete local macOS ARM64/Python 3.14 suite ran 241 cases: 238 passed, one optional FFmpeg skip and two known platform errors (127.0.0.2 binding and an AMD64 server fixture). Ruff lint/format, whitespace, version references across 38 documents and existing documentation contracts passed. Catalog comparison confirmed only GB300 TP4 validation metadata changed; TP2 and all inference settings remain intact. Baseline hash checks explicitly verify the new metadata before restoring its historical value for the original hashes, preserving checks on all other content.

## Air-gapped client startup report and documentation correction: 2026-11-17

User-reported result: the server API worked while OpenCode waited at startup. With `npm_config_offline=true`, a complete chat returned `LOCAL_AI_OK` in about nine seconds with exit code 0; the user confirmed it worked. Update the bilingual offline procedures, README and command examples around B300/GB300, plus advance preparation of Docker packages and dependencies for the target Ubuntu release and architecture (no packages downloaded or installed). No remote test was rerun for this documentation change, and it adds no GB300 hardware acceptance. `install --offline` and the chat npm environment variable control different stages. Document system-wide `/etc/profile.d/local-ai.sh` setup for dedicated air-gapped nodes and the personal `~/.profile` alternative, including PATH, interactive Bash completion, current-shell loading, checks, resumption and login/non-login Bash behavior. The npm offline variable is offline/air-gapped only; PATH and completion work online too. No actual system or user startup files were changed.

Local macOS ARM64/Python 3.14 checks with isolated temporary/state directories: 241 unittest cases, 238 passed, one optional FFmpeg skip and two environment errors (unavailable 127.0.0.2 binding and an AMD64 server fixture on ARM64). Eight documentation checks, version references across 36 documents, Ruff lint/format and git diff --check passed. Newly prefixed offline CLI examples in both languages were parsed separately.

## v1.4.0 documentation correction and release withdrawal: 2026-11-17

The initial v1.4.0 release used commit 83b9366a55984e0d9e1676802deb3bb7d8f418cd. Correct bilingual offline downloads, document-upgrade guidance, release status and historical wording; add a version-reference contract and a developer release checklist. The user subsequently requested removing the GitHub Release and download assets, then committing and pushing the corrections only. Preserve the original tag and commit history without retagging or repacking. Runtime implementation and version remain unchanged. The original v1.4.0 tag archive does not contain these documentation corrections; use a source commit containing this change.

Additional release checks: 238 CPU cases, native reasoning/Ctrl+T, native observer under the offline flag, plugin inclusion in the wheel and v1.3.7 source upgrade/rollback passed. Model/client/instance sentinel contents and inodes, endpoint settings and permissions were preserved. One local mock startup measured about 5.7 seconds with reused dependencies versus 5.1 without the plugin and 12.6 for unseeded plugin initialization; this is not GPU or task-speed acceptance.

## v1.4.0 client acceptance: 2026-11-17

Validated on Linux AMD64 with OpenCode 1.19.5, still NPM latest when checked; no binary upgrade.
CPU mocks cover byte-preserving forwarding, actual usage, unknown cache counts, HTTP errors without proxy retries,
truncated streams, unresolved tools, PID reuse and deadline cleanup. Native tools/resume/compaction with a mock API
verify two tool writes, same-session resumption, cache usage, summary preservation requirements and exactly-once append.
Interactive acceptance verifies restored history, disabled mouse capture, bracketed paste and normal exit.

A real DeepSeek-V4.1-Flash API passed isolated edit-test, diagnose and resume cases: unchanged tests pass after repair,
diagnosis JSON is correct, and resuming the same conversation appends once, with actual tools observed.
All four launches recorded native events and left no unresolved tools. The API omitted per-request cached-token
details, correctly reported as unknown. Raw prompts/events/session IDs/infrastructure paths remain private.

Direct plugin loading exposed repeated SDK initialization in fresh config directories. Reuse genuine matching
dependencies/locks while preserving per-launch configs; cold initialization is not model TTFT.
Remaining native regression and CI gate the release. These small cases do not establish perfect long-context memory,
task speedups, sustained concurrency or new GPU support. Real-GPU server benchmark acceptance remains separate.
See [release notes](release-1.4.0.md).

## KV cache offloading assessment: 2026-11-17

Read-only assistant metadata, /metrics, startup arguments and logs; no conversation bodies, cache resets, synthetic inference or restarts. Sanitized aggregates only.

- Client: 2026-11-01 01:22 to 11-17 01:52 UTC; 29 conversations, 4,111 model calls with input tokens and completion times, not user questions. Input median 62,772, P95 95,876, maximum 119,240 tokens.
- Deployment: DeepSeek-V4.1-Flash, B300 TP4, FP8 KV, GPU Engram, 131072 context, four active sequences, memory fraction 0.80, FLASHINFER_MLA_SPARSE_DSV41; no KV offloading.
- Server: all traffic since instance start on 2026-11-08; 2,855 TTFT samples, 174,118,517 prefix-query tokens, 167,013,120 hit tokens (95.9%), zero preemptions.
- TTFT mean 0.300 seconds; 90.3% at most 0.25 seconds, 96.9% at most 1 second. Cumulative prefill 770.361 seconds, decode 9,148.168, end-to-end 10,004.498.
- Startup: 84.15 GiB available KV memory, 20,545,504 logical GPU KV tokens; model/backend-specific, not guaranteed concurrency for arbitrary workloads.

Zero client cache reads conflict with server hits and cannot establish recomputation. Client/server populations differ. Client durations are not pure inference latency; server phase times are not task durations; first tokens may be reasoning.

Conclusion: low-priority backlog, with no clear KV capacity bottleneck. No offloading A/B test or pinned-image compatibility validation. New content also misses; the remaining 4.1% is not all eviction loss. See [exploration](performance.md#kv-cache-offloading-low-priority-backlog-2026-11-17).

## Persistent instruction templates and loading: 2026-11-17

This pre-v1.4.0 check covered Chinese/English general and BCM references with colocated setup instructions.
Both follow the question language unless explicitly overridden. Templates are opt-in and never replace personal files.
Personal AGENTS.md is now explicitly referenced using the pre-isolation XDG_CONFIG_HOME or ~/.config,
while model/session configuration stays isolated. Regressions cover default/custom paths including spaces,
unchanged personal contents/inode/permissions, no import of other personal configuration, and template export/update/rollback.
Documentation contracts now include template links, Bash syntax and CLI examples. A native local-mock context check
is included in client CI; actual Linux results are recorded separately.

The macOS ARM64/Python 3.14 suite ran 220 tests: 217 passed, two known platform errors and one optional FFmpeg skip.
Errors concern unavailable 127.0.0.2 binding and an AMD64 server fixture on ARM64; existing cases remain intact.
Ruff lint/format and patch whitespace checks passed. Context delivery does not guarantee model compliance,
and no hardware acceptance is expanded.



All 220 tests passed on Linux AMD64/Python 3.12. Native OpenCode 1.19.5 with a local mock API confirmed
personal/project/built-in instructions in actual requests, unchanged personal files and continued session isolation.
An initial live-model fixture exposed find -not -path filtering results while still traversing mock images.
Templates now require component selection and provide a pruning example, explicitly rejecting output filters as traversal exclusions.
No real image tree was involved. A subsequent native glob bypassed shell exclusions; templates now cover
all file tools and prohibit broad parallel fallbacks. Native internal threads also read files when mock images
were inside the project, so setup guidance requires small projects and discloses the absence of enforced isolation.
With fixtures outside the project and narrowly allowed disposable external access, two live-model cross-language
cases (Chinese template/English question and English template/Chinese question) found and read the intended script
without executing it. strace recorded zero mock-image opens/traversals in each case; final replies followed the
question language. Some progress prose remained English with the English template. These two small samples do not
prove reliable compliance in all contexts. Raw traces remain in temporary host storage outside Git; no real
compute-node image tree was scanned.

## Local benchmark tool logic: 2026-11-16

This preserves the 2026-11-16 pre-release check: development source then added `server benchmark --name a` without changing the then-current version or v1.3.7 tag. It is now released in v1.4.0.
No model is deployed locally. Validation used macOS ARM64, Python 3.14 and a temporary stdlib HTTP server only.
No real GPU service was started or contacted; no model performance numbers or expanded hardware support are claimed.

Twelve new tests cover empty stream chunks versus first output, real HTTP streaming timing, exact API token counts,
warmup/tokenization exclusion, concurrency and round-wall-time throughput, mean/median/nearest-rank P95, separate JSON/0600 permissions,
actual CLI metadata loading and JSON stdout, zero warmup, HTTP errors/disconnects/early termination/missing usage,
timeouts during tokenization/streaming, cancellation records, stopped/unhealthy/missing-identity rejection, restart invalidation,
option bounds and the shared benchmark/warmup lock. Timing assertions concern mock pacing, not engine speed.

The full suite ran 219 tests: 214 passed, four environment-related errors and one optional-FFmpeg skip.
The pre-change HEAD suite ran 207 tests with the same four errors and one skip under matching conditions:
two client tests lack permission to write ~/.local/bin, macOS cannot bind 127.0.0.2, and an AMD64 offline server fixture
does not match this ARM64 host. No existing tests were changed, deleted or skipped. Runs used TMPDIR=/private/tmp and
separate temporary XDG_STATE_HOME directories to isolate connection state. Ruff checks, formatting for 57 files, Git whitespace
checks and bilingual documentation command/option coverage, CLI examples, Bash syntax and local-link checks passed.
Linux CI and native OpenCode acceptance were not run; this feature does not change the client.

Reviewed Chinese/English README, commands, deployment, offline, architecture, development, performance, update and historical validation limits.
At that historical check the command was development-source-only and old tagged downloads were v1.3.7. Corrected the English offline guide's outdated
version statement to match its actual download commands. Reports remain in ignored instance directories and are excluded from export.
GPU acceptance must separately check API compatibility, actual token counts, warmup/summaries and cancellation on an allocated ready instance,
with default single concurrency and explicit concurrency. Record model/revision, image, hardware and other load. Synthetic request rates,
small-sample P95 and cross-profile comparisons do not establish independent GPU rankings or production SLAs.

[中文（默认）](../validation.md)

Dates: 2026-10-31 through 2026-11-01. Infrastructure hostnames, IPs, GPU UUIDs, credentials and raw
user logs are intentionally omitted from this public record.

The 2026-10-31 integration records below describe the previous client. Tunnel entries are historical; the current client uses API endpoints without built-in forwarding or a separate environment-doctor command. New local HTTP regressions cover direct connections, model checks, retry and no SSH subprocess. They do not constitute new GPU acceptance.

Version labels 1.0.0/1.1.0 below identify historical candidate checks whose tags were withdrawn. The program version at that historical check was v1.3.7; templates and instruction forwarding are now released in v1.4.0; each acceptance record retains its original date, method and limits. Tagging does not expand support.

## GB200 candidate and Rubin framework: 2026-11-09

No target hardware is available. Adds only ARM64 gb200-tp4 and rubin-tp2-framework without
changing existing models/recipes or existing tags; update the version for this release. GB200 retains B200 TP4 engine
parameters without hardware validation. Rubin's official 288GB HBM4/GPU motivates two GPUs
with CPU Engram offload and a provisional 256 GiB host guard. These capacity assumptions
are not measured minima or evidence of successful model startup.

The public registry confirmed the existing pinned image has linux/arm64 platform digest
sha256:b1bea6490db94268e68577929ae4b800a662b91a3cd4a1fcba81cfb3946ddcff and
CUDA_VERSION=13.0.2. No image layers or weights were downloaded and no GPU was used.
Rubin does not borrow this image: image, platform_digest and min_vram_mib remain null with
planning_only=true. Framework plans return deployable=false, blockers, command=null and
spec.args=null.

Thirteen new CPU tests cover GB200 card counts, UUID order, reported B200 names, wrong
CPU/GPU/memory, pure plans, Rubin TP2/offload targets, early CLI/Python framework rejection,
completion and help. Clearing only the flag or filling only image fields cannot enable the
framework. Fixtures are explicitly synthetic. Preserve the RTX original-catalog hash constant,
excluding only the new entries, and additionally verify all existing recipes/models against
the complete v1.3.3 catalog hash. Existing protections were not removed, skipped or relaxed.

Of 186 local tests, 184 pass; two existing macOS/ARM64 limitations match the next section.
Ruff lint, formatting of 49 files, Git whitespace and bilingual documentation contracts pass.
Local checks did not run Linux CI, native-client or GPU acceptance; release CI remains required. Loading, full context,
concurrency, speed and sustained stability remain unvalidated. Reviewed both README workflows
and Chinese/English deployment, offline, architecture, development, performance, update,
command and historical validation materials, distinguishing v1.3.4 candidates from historical acceptance. See [GB200 and Rubin](gb200-rubin.md) for methods and future acceptance.

## Bash completion CPU regressions: 2026-11-08

v1.3.3 adds completion bash. Six new regressions
pass on macOS ARM64, Python 3.14 and Bash 3.2.57: command levels, options, fixed choices,
custom catalogs, repeated options, equals syntax, paths with spaces, global arguments and
read-only boundaries, including actual Bash function calls. A Bash PTY smoke test also typed
ser, Tab and --help, confirming completion to server and its command help. Ruff lint/format and diff checks
pass; documentation contracts cover bilingual CLI examples, options, links and Bash syntax.

The full unittest suite has 173 tests: 171 pass and two fail due to local platform constraints:
127.0.0.2 cannot be bound, and an AMD64 server offline-install fixture conflicts with the ARM64
host. The original 167-test source has the same two failures. Existing tests were neither
modified nor skipped. Temporary paths and private state use /private/tmp to avoid macOS
temporary-directory symlink differences in path comparisons. Linux interactive terminals and
GPUs were not validated; hardware support is unchanged.

Manually reviewed both README workflows and Chinese/English command, deployment, offline,
architecture, development, performance, update and validation materials. Completion remains
optional shell setup; installation/migration steps, defaults and historical acceptance limits
remain consistent.

## Hardware and pinned versions

- Server: eight B300 GPUs on AMD64, Ubuntu 24.04, NVIDIA driver 580.126.20.
- Container runtime: Docker 29.2.1, NVIDIA Container Toolkit 1.19.1.
- Model: DeepSeek-V4.1-Flash revision 314113f8a7dadb388215396ba5fbee2c610a04d6.
- vLLM: 0.32.0-ubuntu2404; immutable manifest-list and AMD64/ARM64 child digests
  are recorded in profiles.json.
- BCM client: Linux AMD64, OpenCode 1.19.5; no headnode Docker or Node/npm.

## Project integration tests

| Check | Result |
|---|---|
| BCM-owned SSH tunnel to existing GPU service | Passed |
| BCM grep/glob/read/edit + independent unittest | Passed; tests unchanged |
| Tool execution location | Confirmed BCM hostname |
| Edit/test integration duration | About 9.8 seconds; one smoke task, not a benchmark |
| New manager cold-start on four other local B300 GPUs | Passed; about 364 seconds including first compile |
| BCM tools against the newly created service | Passed |
| Tunnel closed after client exit | Verified by local port check |
| New temporary service stopped | Passed; original service still healthy |
| Online client installation from NPM | Passed with registry SHA512 integrity and version check |
| Fresh online-installed binary, empty private cache, grep + hostname | Passed |
| Client export/checksum/import | Passed; binary checksum preserved |
| Project CLI under Docker network none | Passed through Unix-socket bridge to local inference; external connection blocked |
| Real platform-selected Docker image inspect | Passed on AMD64 |
| GB300 native execution | Not performed; profiles remain experimental |

The network-isolated client test uses a local Unix-socket API bridge. It does not
provide general networking and does not establish a fresh disconnected GB300
server cold start. The image is not run under ARM emulation as a substitute for
hardware validation.

## Independent-host deployment and installation acceptance

On 2026-10-31, deployment was repeated directly on another AMD64 B300 host without an existing project data directory.

| Check | Result |
|---|---|
| Copy complete existing weights; pull pinned platform image | Passed; weights were not downloaded again from the internet |
| CDI preflight | Found zero device definitions; local refresh restored UUID aliases for all eight GPUs |
| Four-GPU cold start and healthy API | Passed; health wait about 361 seconds including first compilation |
| GPU isolation | Only GPUs 0–3 allocated HBM; GPUs 4–7 remained at zero |
| Actual BCM tool calls | glob twice, read twice, edit once, bash twice; hostname confirmed BCM |
| Synthetic code repair and independent tests | Passed without modifying original tests |
| Temporary service cleanup | Container removed and all eight GPUs returned to zero HBM |
| Real image export, SHA256 and import | Passed; archive 9,205,795,328 bytes, export about 212 s, import about 63 s |
| Local image identity after removing original reference | Passed using image ID/content lock without registry access |
| Repeat image/model preparation | Both returned already-present and network=false |
| Wheel build and installation into a separate directory | Passed, including new modules, profiles.json and CLI entry point |

The reused model files lacked this project's model.lock.json, so revision_verified=false was explicitly reported.
No verified-provenance claim was fabricated. Structural shard checks do not replace complete content hashes and provenance validation.

The archive roundtrip used the same Docker 29.2.1 backend and exercised lock fallback with the original reference absent.
The entire host was not physically disconnected from the internet. Fresh OS/driver installation, another storage backend and
GB300 are not established by this result. Installation evidence is centralized in install.log; raw evidence remains internal.

CPU regressions additionally cover local reuse, stale locks, revision conflicts, truncated shards, journal streams/status/timeout/path
handling, pure plans and bilingual CLI/manual/link/Bash-example consistency. New GPUs still require separate profiles and hardware acceptance.

## Reference decode comparison

Earlier same-node sequential streaming probes used prompt lengths of 53 and
8453 tokens, 128 completion tokens, temperature 1 and top_p 0.95:

| Profile | Mean decode tokens/s |
|---|---:|
| Initial TP8 eager / CPU Engram | 5.20 |
| Optimized TP8 | 221.52 |
| Optimized TP4 | 221.72 |

These short capped completions were reasoning tokens. Rates exclude prefill and
do not represent final-answer latency or concurrent throughput. The optimization
comparison combines GPU Engram placement and CUDA Graphs, so their individual
contributions are not established. New uncached approximately 8.5K-token prompts
after warmup had first-token times around 0.44–0.47 seconds.

## CPU-only regression coverage

Tests cover architecture normalization and mismatches, UUID/index duplicate
selection, HBM checks, GB300 TP2 memory policy, side-effect-free plans,
selected-versus-unselected GPU conflicts, image identity, explicit ARM64 image
inspection, weight-index traversal, ELF checks, package tampering, unsafe archive
members, cache privacy, same-user concurrent config isolation, SSH argument
validation and cleanup on exceptions.

CI is configured for Python 3.10/3.12/3.13. Its remote result is only known after
the workflow runs. Local test/lint/build results do not imply remote CI passed.

## Remaining acceptance work

- Native GB300 TP2 and TP4 cold-start, memory, tool and performance tests.
- ARM64 BCM client native test (independent of the server architecture).
- Fully disconnected fresh-system deployment and image roundtrips across Docker/storage-backend versions.
- Sustained two-replica and multi-user concurrency/performance characterization.

## Primary references

- [vLLM model recipe](https://recipes.vllm.ai/deepseek-ai/DeepSeek-V4.1-Flash):
  profile provenance, including GB300-style TP2 offload.
- [NVIDIA CDI](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/cdi-support.html):
  native device selection.
- [Docker platform inspection](https://docs.docker.com/reference/cli/docker/image/inspect/),
  [export](https://docs.docker.com/reference/cli/docker/image/save/) and
  [import](https://docs.docker.com/reference/cli/docker/image/load/).
- [OpenCode configuration](https://opencode.ai/docs/config/).

Raw integration evidence remains in ignored runtime paths with the operator;
it is not a repository artifact.

## Client resume and configurable-model validation

2026-11-01: Real OpenCode 1.19.5, temporary user state, native HTTP session
creation and a pseudo-terminal verified opencode -s resume, disabled mouse
capture, bracketed paste and clean exit. Existing session endpoint/project
lookup also passed. No Slurm/Kubernetes job was submitted, and no additional
model or client release was validated. Assistant guidance covers these tasks;
it does not constitute cluster acceptance.

All three existing vLLM argument lists match their pre-change values.
CPU regressions cover external recipes, revision/environment identity,
per-model locks and client-release reuse. Configurability does not raise
hardware validation levels. Native checks and candidate-version selection
are included in CI.

## 1.0.0 release validation

2026-11-01: 95 unit tests, Ruff lint/format and diff checks passed.
Built wheel/sdist and installed the wheel offline with --no-index --no-deps in
an isolated Python 3.12 environment. Outside the checkout, metadata/CLI reported
1.0.0, all three profiles loaded, and pure planning created no data directory.
Native OpenCode 1.19.5 checks from the installed wheel passed session restore,
disabled mouse capture, bracketed paste and clean exit.
The sdist includes docs, launcher, compatibility script and inventory fixtures.
Existing platform/model validation levels are unchanged. No inference service
was restarted or scheduler job submitted. Publication requires passing commit CI.

## 2026-11-01: 1.1.0 directory installation and complete offline bundles

107 unit/documentation tests, Ruff lint/format and diff checks passed. Coverage includes default dist/, recursive-export exclusion, ordinary source, renamed installation, compressed archives, saved defaults, legacy clients, initial checksums, repeat installation and corruption rejection. Real OpenCode 1.19.5 checks again passed session restore, disabled mouse capture, bracketed paste and clean exit.

The following workflow ran on another idle AMD64 B300 host:

| Step | Result |
|---|---|
| Fresh online server + client installation | Downloaded image, complete model and native client in about 479 seconds; installation did not start GPUs |
| Default export into installation-root dist/ | 519,734,251,520-byte archive in about 1327 seconds, containing ordinary source, all 48 model shards, image and client |
| Portable image archive | 9,205,795,328 bytes, carried inside the bundle |
| Whole-archive SHA256 and extraction | Standard sha256sum passed; extracted into an empty directory with a different name |
| Export exclusions | Actual manifest excluded dist/; regressions cover personal histories, credentials, instances and caches |
| Offline installation after removing original test image references | All file checksums passed; docker image load imported the local archive in about 168 seconds |
| Offline model and client | Complete model reported revision_verified=true; model/client already-present and network=false, with no pull, model or NPM download commands |
| Complete offline installation duration | About 768 seconds including initial per-file SHA256 and image import |
| Four-GPU cold start and status output | Healthy HTTP 200 after about 382 seconds; startup/runtime logs displayed READY and status returned ready=true, listening=true |
| GPU isolation | Only selected GPUs 0–3 allocated memory; GPUs 4–7 stayed at zero |
| Actual BCM tool call | Direct API connection to the restored service; real bash hostname execution returned the BCM hostname |
| Final 1.1.0 runtime recheck | Offline reuse of the same model, image and native client passed; existing ready instance returned HTTP 200 |
| Temporary service cleanup | Test container and temporary CDI file removed; all eight GPUs returned to zero memory usage |

Separately downloaded an exact GitHub commit, installed the client online, exported it, verified the checksum and extracted it into a renamed directory. Client installation under unshare -n with --role client --offline passed, followed by the real native-client contract check. The large bundle came from the directory-installation candidate snapshot; final default-setting and version changes were checked separately with the 1.1.0 runtime. Archive sizes describe the test bundle, not the source-tag download.

Offline installation ran under unshare -n; Docker accessed the host daemon through its local Unix socket. The entire host was not physically disconnected. These results do not cover fresh OS/driver setup, another Docker storage backend, GB300, ARM64 or another model. Raw evidence remains in internal test directories; only summaries are published.

## 2026-11-01: multiple endpoint defaults and overrides

109 tests and Ruff lint/format checks passed. Two local HTTP model servers with different model IDs exercised A → B → A routing, endpoint/model overrides, unchanged installation.json and separate history/state/cache directories. An unavailable model failed with advertised IDs and --model guidance, without fallback to another endpoint. Offline client installation covered optional defaults, preservation when omitted and explicit replacement without downloads.

--check now reports the actual endpoint/model. Real OpenCode 1.19.5 contract checks passed session resume, disabled mouse capture, bracketed paste and clean exit. The multi-service routing test used local HTTP fixtures and a substituted client executor; it is not new acceptance for multiple physical GPU nodes or other models. No GPU service was restarted.

## 2026-11-01: independent configuration and migration documentation

116 tests, Ruff lint/format and documentation contracts passed. config show/set/unset were tested with network, subprocess and installation calls prohibited: read-only viewing, validated updates/removal, preserved metadata, direct file editing, malformed JSON/type errors, bundle verification receipts and offline reinstallation compatibility. Existing multi-endpoint routing tests still pass. Real OpenCode 1.19.5 resume/terminal contract checks passed.

Complete export/transfer/offline-import instructions now live in the offline guide; README identifies source/target roles and links to both routes. This change did not repeat physical GPU migration or restart inference services.

## 2026-11-01: single-node engines and DSpark

Compared the same four B300 GPUs, TP4, model revision, 131072 context and four active sequences using vLLM 0.32.0 and SGLang 0.0.0.dev1+gda64c5cbb. SGLang used a separately pinned development image and EP4; vLLM did not enable EP. These results compare those configurations, not all framework workloads. The existing service on four other GPUs was unchanged.

Identical uncached synthetic logs used 9272 input tokens, 256 output tokens, temperature=1 and top_p=0.95. Single-request groups had two samples; four-concurrency groups had eight. Decode rates exclude prefill. TTFT includes the first reasoning token, not the final answer.

| Configuration | Single TTFT median ms | Single decode tokens/s P50 | Four-concurrency aggregate tokens/s |
|---|---:|---:|---:|
| vLLM baseline | 377.5 | 236.2 | 422.2 |
| vLLM DSpark | 381.8 | 459.9 | 352.0 |
| SGLang baseline | 549.2 | 166.6 | 267.8 |
| SGLang DSpark | 591.6 | 303.5 | 300.6 |

vLLM DSpark decoded about 1.95 times faster for one request, while four-concurrency throughput fell about 16.6%. This supports an optional single-user recipe, not replacing every concurrent service. The vLLM recipe uses five draft tokens, probabilistic drafts, real block rejection sampling, adaptive verification disabled, and graph capture sizes 6/12/24. No synthetic acceptance was used. Counter deltas show 40.97% draft-token acceptance and 2.05 accepted tokens per iteration. The default profile is unchanged.

The ordering also changed with workload: at 1208 input tokens and eight-concurrency, aggregate throughput was 470.1 tokens/s for SGLang baseline and 561.7 for SGLang DSpark, versus 268.8 and 441.9 for the two vLLM configurations. The vLLM baseline included a JIT tail. Preserve these results and repeat with longer steady-state samples before generalizing; the 9K table alone does not dismiss SGLang.

Each configuration had 101 formal-stage requests: 93 performance requests plus warmup, cache seeding and three basic checks. Payloads/token counts matched across configurations, with zero request errors; arithmetic, Bash syntax and tool-format checks passed. Generated Bash was not executed. Most capped output was reasoning, samples were small, and complete quality or complex tool round trips were not validated. SGLang was not added as a project engine.

First-use shapes produced a 13.9-second TTFT spike; the vLLM baseline still showed a 10.75-second short-input/eight-concurrency tail after one shape-preparation pass. Best warmed numbers alone are insufficient. Logs identified inference-time CuTeDSL MXFP8QuantizeSwizzledKernel and Triton _block_scores_kernel JIT. Separate explicit-warmup validation follows. Raw arguments, requests, metrics and model-configuration hashes remain internal.

## 2026-11-01: DSpark recipe and explicit warmup acceptance

Native project commands validated b300-tp4-dspark on four allocated B300 GPUs. Both groups used the same image/model/settings and separate empty compilation caches. Host page caches were not cleared; CPU/RAM/disk were shared. Control waited for API health only; the other group ran start --warmup. All 90 real warmup requests completed in about 104.8 seconds, with completion in runtime logs and warmup.json.

Each group measured 78 streaming requests: exact inputs 1024/8192/32768 tokens, concurrency 1/4/8, twice the concurrency in requests per group, 256 output tokens, temperature=1, top_p=0.95 and ignore_eos=true. Integer token-ID prompts and fresh prefixes were used. This is not full chat-template or quality acceptance. Streaming was measured separately after non-streaming warmup.

| Input tokens | Concurrency | Requests/group | API-only max TTFT seconds | After explicit warmup max TTFT seconds |
|---|---:|---:|---:|---:|
| 1024 | 1 | 2 | 14.405 | 0.191 |
| 1024 | 4 | 8 | 22.948 | 0.584 |
| 1024 | 8 | 16 | 6.816 | 7.785 |
| 8192 | 1 | 2 | 0.885 | 0.386 |
| 8192 | 4 | 8 | 4.327 | 1.173 |
| 8192 | 8 | 16 | 3.320 | 3.276 |
| 32768 | 1 | 2 | 0.968 | 0.959 |
| 32768 | 4 | 8 | 6.163 | 3.375 |
| 32768 | 8 | 16 | 7.717 | 7.627 |

The first single 1024-token request changed from 14.405 to 0.188 seconds. No monitored inference-JIT warnings appeared during post-warmup measurements, but eight-concurrency still had an approximately 7.8-second tail, including queueing beyond four active sequences. Not every latency tail is compilation. Finite shapes and small samples do not establish arbitrary-workload JIT elimination or production SLAs; these results support an optional single-user-oriented configuration.

Cold-cache start commands took about 428.1 seconds for control and 523.1 including explicit warmup. Warmup moves some first-request work before traffic, without eliminating the compilation cost. Stopping/starting the same container restored API health in 167.8 seconds, with 321 host-cache files and the TileLang directory present. The old warmup record correctly became stale/completed=false. This checks the same container, not cache compatibility across recreated containers, engine versions or GPU architectures. All paired payload hashes matched, and all 156 measurement plus 90 warmup requests succeeded. Test containers were removed, the four test GPUs returned to zero allocated memory, and the unchanged production service remained HTTP 200.

131 CPU unit/documentation tests, Ruff lint/format, diff checks and package-content checks passed. CPU coverage includes real TCP TIME_WAIT reuse with active-listener rejection, bounded HTTP warmup, partial failure, cancellation, duplicate locks, wrong deployment metadata and stale restart markers. GB300 and complete DSpark tool round trips remain unvalidated.

The first instance switch exposed a TIME_WAIT false port conflict. After confirming no listener, preflight was fixed with SO_REUSEADDR and a real TCP regression; active listeners remain rejected. All control requests were retained and only the unfinished warmup group resumed. This change affects preflight, not engine arguments or payloads. See the [performance record](performance.md) for the full optimization and SGLang investigation.

## v1.2.0 version marking

This version includes directory installation/offline bundles, configurable endpoints, the optional B300 DSpark recipe and explicit inference warmup. Performance investigation and SGLang findings remain documented. This marking changes version metadata and source-download references without changing the previously validated inference settings. CPU/documentation and package checks are repeated; tag the exact commit only after its CI succeeds. Hardware evidence remains limited to the scenarios above; no additional GPU or disconnected-system acceptance is claimed.

## Program-only updater acceptance

The updater was first validated on main. The actual upgrades below used the original v1.2.0 source archive at b82cfc9. At the user's explicit request, v1.2.0 is retagged to include the updater, tests and bilingual upgrade guide, retaining version 1.2.0. 143 unit/documentation checks pass, including 12 updater regressions for offline/source-tag paths, actual resource inode/content preservation, settings permissions, stale receipts, malformed archives, explicit rollback, replacement failure, missing-launcher interruption recovery and duplicate locks. A real 1.1.0 source tree was upgraded using the public v1.2.0 archive, executed outside the checkout, and rolled back successfully. The retained helper appears in the old tag's ordinary source-file export list.

Actual installed AMD64 server and BCM program directories were then updated from 1.1.0 to 1.2.0 with the verified local source archive, without install or resource preparation. Model/image/client/custom-config file inodes, sizes and modification times were unchanged; all weight contents were not rehashed. Saved defaults were preserved apart from version/bundle receipt metadata. The server container ID/start time and configuration/launch-file hashes matched before/after, health remained HTTP 200, and BCM chat --check succeeded against its saved endpoint. No inference generation, GPU restart, OpenCode version change or production rollback was performed. Old source/metadata backups and detailed infrastructure evidence remain outside Git.

## 2026-11-04: rich-document reading

BCM client on Ubuntu 24.04, Python 3.12.3, OpenCode 1.19.5, existing DeepSeek-V4.1-Flash endpoint. No model/image/GPU service changes. Poppler 24.02.0 and LibreOffice 24.2.7 were installed on the client. Ordinary chat named a directory; no attachment startup flag. The assistant discovered files and called the local document MCP tool. All 12 synthetic files returned their hidden CHECK CODE: PNG, text PDF, scanned PDF, DOCX, XLSX, PPTX, ODS, ODP, DOC, XLS, PPT and RTF. Excel B2 formula =5+7 and cached value 12 were reported; PPT rendering identified the blue rectangle. Direct rendering checks also passed for XLSX/PPTX/ODS/ODP. Expected codes were outside the model project, not supplied in the prompt. PPT relationship ordering was fixed after real LibreOffice output exposed an unqualified numeric id preceding r:id. 154 unit/documentation tests and native session/terminal compatibility passed.

Limits: simple one-page English visual fixtures, not a comprehensive OCR/layout benchmark. Unrequested visual repetition counts in model prose were not accepted as verified facts. No claim for all Chinese scans, complex charts, encrypted documents, macros, animation, large workbooks, ARM64 or arbitrary future OpenCode versions. Supported JPEG/WebP/GIF and ODT paths did not receive the same live-model coverage. Source guides describe optional host dependencies, which portable export does not package.

## v1.3.0 version marking

Explicitly requested release including ordinary-chat rich-document reading, model image capability declarations, client-side PDF/Office tools and bilingual guides. Existing v1.2.0 remains unchanged. The feature commit 8fc8a37 passed 154 tests, native OpenCode compatibility and CI; the release commit updates version metadata and consistent tagged download/update examples. Earlier hardware and document-quality limits remain unchanged.

## 2026-11-08: Bounded four-B200 hardware acceptance

Added b200-tp4 (GPU Engram) and b200-tp4-cpu (CPU Engram) without runtime code changes.
Four allocated healthy B200 GPUs on one NUMA node each reported 183359 MiB.
Environment: AMD64, approximately 2 TiB RAM, driver 580.173.02, Docker 29.6.2,
Toolkit 1.20.1; the pinned vLLM 0.32.0 image includes PyTorch 2.13.0+cu130 and sm_100.
Model revision, image and platform digests remain pinned in profiles.json.
Actually downloaded 48 shards, approximately 475.25 GiB, and checked the revision
lock, configuration, index and shard lengths. Four-GPU BF16 matmul, peer visibility
and 16 MiB NCCL AllReduce passed.

Both native server start commands reached health HTTP 200 with TP4, configured
131072 context, four active sequences, 8192 batched tokens, 0.80 memory budget,
FP8 KV and identical parsers, without DSpark.

| Metric | CPU Engram | GPU Engram |
|---|---:|---:|
| First-instance READY time, seconds | 289.18 | 267.12 |
| Resident model memory, approximately GiB/GPU | 78.53 | 125.74–125.75 |
| Available KV cache at initialization, GiB/GPU | 59.76 | 12.68 |
| Arithmetic, streaming, tool round trip, one red PNG | Passed | Passed |

The model requested add_numbers; deterministic integer addition was executed,
returned as a tool result, and the final answer checked. Vision covered only a
640×480 solid-red PNG, not OCR or complex documents.
Initial API acceptance used 15 requests per profile, including 10 performance
requests: 6680 input tokens, 128 output tokens, temperature=0, thinking disabled,
ignore_eos=true, concurrency 1/4 and two rounds each. CPU/GPU payload hashes matched.
First large inputs showed approximately 11-second TTFT with inference-time JIT.
Initial second-round four-request throughput was 388.91 CPU versus 144.17 GPU
tokens/s; this prompted supplementary sampling rather than a steady-state claim.

Supplementary sampling uses different prefixes and matched payload hashes, six
rounds at concurrency 1/4. Two rounds prepare shapes; four contribute summaries.
Total throughput includes TTFT; per-request decode speed uses first-to-last
content-chunk time. These are different metrics.

Supplementary input length was 6684 tokens per request; all 30 requests per profile returned 128 tokens. All 12 corresponding batch payload hashes matched. The following uses four measured rounds per concurrency, including every outlier:

| Metric | CPU Engram | GPU Engram |
|---|---:|---:|
| Single-request TTFT, median seconds | 0.172 | 0.174 |
| Single-request decode, median tokens/s | 241.984 | 241.589 |
| Four-request total throughput, median tokens/s | 396.379 | 393.317 |
| Four-request batch throughput range, tokens/s | 144.40–398.89 | 391.62–394.18 |

The CPU run also had a four-request latency spike (144.40 tokens/s), so the earlier GPU spike is not evidence of a general offload speed advantage. In this small sample median single-request decode and four-request throughput were similar; it does not establish equal latency tails or general workload performance. Together with the initial API checks, 45 requests per profile completed successfully.

Default KV allocation can keep nvidia-smi total usage similar after CPU offload.
The 256 GiB host and 180000 MiB/GPU guards are not measured minimum requirements;
acceptance used approximately 2 TiB RAM, not a 256 GiB host.
Host page caches were not cleared, CPU/RAM were shared, and NUMA CPU/memory binding
was not tuned. This is bounded API and small-load acceptance, not full 131072-token
input, long-running stability, complex vision/tools or a native OpenCode end-to-end
test on this node. Raw logs, operational scripts and snapshots remain outside
tracked source or in ignored directories.

## v1.3.1 version marking

Explicitly requested version label for merging B200 support commit c802251 into main. Program metadata and download/update examples use 1.3.1. Includes independent GPU/CPU Engram TP4 profiles, seven added regression tests and bilingual deployment guides. B200 hardware acceptance remains bounded by the preceding record; this tag does not expand full-context, long-running or other-platform support.

## 2026-11-08: Live reasoning variants and v1.3.1 retag

Model client.variants exposes default, low, high, xhigh, max and none. The empty default adds no thinking parameters and preserves original behavior. Disable native generic medium/minimal variants unsupported by this model. Runtime code and GPU engine arguments remain unchanged.

Native OpenCode 1.19.5 used an isolated temporary HOME, state and project with a local mock endpoint. Seven sequential requests in one session and backend process checked four numeric effort levels, disabled thinking and restored default. A PTY check verified no initial override, sent the actual Ctrl+T key, and checked the next HTTP request for changed effort. Existing resume and terminal-mode acceptance remains required. Added default-behavior/model-isolation regressions and the native check to CI client-contract. All 164 unit tests, Ruff lint/format checks, Git whitespace validation and both native-client checks passed.

This acceptance invokes no production model, cluster operation or GPU load. It establishes no speedup, reduction in reasoning tokens or preservation of complex-task quality. New or resumed clients load the variants once; subsequent switching is live. Custom complete catalogs need an explicit merge.

The user explicitly requested retagging v1.3.1. Its previous commit was fb3590a52c211472063d0d00b0756fd5074739b4 and annotated tag object was 300e2aba37202788b1f002b7bd0038147d78192c. The replacement points to the CI-passed commit containing this record; consult the remote tag for its exact SHA. Previous v1.3.1 downloads need fresh source or another program update; the unchanged version string alone does not identify source content. Original B200 hardware acceptance limits remain unchanged.

## 2026-11-08: Fix skipped reasoning variants

The user reported missing low/max choices. Reproduction showed an explicit default variant colliding with OpenCode 1.19.5's internal default wrap value. Generated variants merged ahead of it; cycling wrapped back to the middle and made earlier entries unreachable. The previous single-switch check missed full-cycle coverage.

Rename the visible original-strength choice to normal while retaining native unselected behavior. Other request values are unchanged. Strengthen PTY acceptance with nine Ctrl+T presses and mock requests, inspecting frontend-selected names through the public message API. Cover all six visible choices, native default and wrap back to low. Including seven API variant requests, 17 mock-model requests passed. This is no real-GPU or performance claim.

The user's explicit v1.3.1 retag authorization covers this correction. Previous commit: 4be659fa87d2ceee1a605fae5b0f9843f465c06a; previous annotated tag object: 001ba472ea6287755b645ab75bfe616f88f58846. Consult the remote tag and delivery commit for the replacement. Current guides use normal; the preceding default description records the former implementation.

## Experimental RTX 6000D TP8

See [RTX 6000D](rtx6000d.md) for versions and limited hardware smoke coverage. Existing platform validation scope is unchanged.

## v1.3.2 version marking

Explicitly requested release integrating independent RTX 6000D TP8 support (feature commit 29e6ad2). Align program versions, README profile tables, bilingual deployment, client model selection, offline and update examples. Existing models, profiles and defaults remain unchanged. See [RTX 6000D](rtx6000d.md) for eight-GPU, bounded API and native-client tool evidence. Full 32K boundaries, concurrency and sustained stability remain unvalidated; merging into main or tagging does not expand support. Require CPU regressions, Ruff, documentation consistency and CI before creating the annotated tag. Historical version records retain their original labels.

Pre-release checks passed: 167 tests in clean source, Ruff lint and formatting of 46 files, 250 local links/anchors and 126 Bash blocks across 26 Markdown files. The version command reports 1.3.2.

## v1.3.3 version marking

Explicitly requested release adding completion bash for nested commands, options, current recipes,
other fixed choices and local paths. Runtime dependencies remain standard-library-only; completion
does not probe GPUs, connect to models or edit shell startup files. Align versions, README,
recursive help, bilingual command, deployment, offline and update entry points. Preserve historical
v1.3.2 and earlier acceptance records. The version command reports 1.3.3.

See the Bash completion CPU regression section for 171 passing tests out of 173, the two existing
local platform failures, Bash 3.2 completion and documentation checks. The release commit's CI
validates Linux unit tests on Python 3.10/3.12/3.13 and native client contracts before creating
the annotated v1.3.3 tag and verifying its remote target. This release adds no GPU acceptance
and changes no existing recipes, installation defaults or hardware support levels.

## v1.3.4 version marking

Explicitly requested release of the experimental GB200 TP4 candidate and planning-only Rubin
TP2 framework. GB200 uses the pinned ARM64 image and B200 TP4 engine baseline, without hardware
acceptance. Rubin plans CPU Engram offload but leaves image, platform digest and minimum HBM
unresolved. Planning succeeds while deployment, downloads and resource export are refused.
The new deployable/blockers fields describe plan results without changing old instance specs,
default recipes or validated models.

Align versions and bilingual README, command, deployment, offline, update, development,
architecture and acceptance documentation. The version command reports 1.3.4; previous versions,
tags and hardware acceptance limits are preserved. Of 186 local tests, 184 pass with the same
two macOS/ARM64 constraints; all 13 new tests and original-catalog hash protections pass.
Ruff lint, formatting of 49 files, 276 local links/anchors and 140 Bash blocks across 28 Markdown
files pass. Require Linux Python 3.10/3.12/3.13 and native-client CI on the release commit before
creating the annotated v1.3.4 tag and verifying remote main/tag targets. Release marking does
not promote GB200/Rubin hardware support levels.

## Cross-platform offline media preparation (v1.3.5, 2026-11-09)

prepare pulls/saves target-profile images and downloads public models at pinned commits using host Python standard-library HTTP. It runs no target program, probes no GPU and leaves host installation settings unchanged. Profiles share one model per repo/revision/model_directory; conflicts fail before preparation. Target install CPU checks remain unchanged.

196 CPU/documentation tests, Ruff lint/format and patch checks passed. New regressions cover shared models, ARM64 server/native client exports, no target execution, resumed/ignored Range, truncated/corrupt files, unprovenanced local files, unsafe paths and planning-only rejection. An AMD64 Linux/Python 3.12 smoke check downloaded and verified a 1701-byte Git file and 190736-byte LFS image. No full weights or real ARM64 image were downloaded and no GB200 hardware startup was tested. Hardware acceptance is unchanged; this capability ships in v1.3.5.

## v1.3.5 version marking

Explicitly requested release of cross-platform offline media preparation. Update version
metadata and bilingual README, online preparation, command and upgrade examples.
Preserve old tags and platform hardware acceptance limits. prepare obtains target images
and public models on another CPU architecture and shares pinned models across profiles.
Run 196 CPU/documentation tests, Ruff lint/format, patch and wheel-module checks before
release; create the annotated v1.3.5 tag on the exact commit passing CI after push.
No new GPU hardware acceptance was performed.

## v1.3.6 version marking and tag cleanup (2026-11-09)

This version includes the bilingual project introduction and updates version metadata, installation downloads, offline media and upgrade examples.
At the user’s request, retain only v1.3.6 and delete local and remote tags v1.2.0, v1.3.0, v1.3.1, v1.3.2, v1.3.3, v1.3.4 and v1.3.5. Earlier records retain their original version labels as historical acceptance evidence, not downloadable tags; historical source remains accessible by commit.
Release requires CPU/documentation tests, Ruff lint/format and patch checks, followed by an annotated tag on the exact commit passing CI. No client/server redeployment or new GPU hardware acceptance is included.

## v1.3.7 web and video (2026-11-09)

Adds stdlib HTTP(S) text, source metadata and continuation; local sidecar/embedded subtitles, metadata and bounded frame sampling. FFmpeg/ffprobe are optional OS tools with executable version checks. No new base dependencies. Per the final user instruction, no SearXNG, search tool or background network service is integrated or deployed.

Coverage includes local HTTP extraction/redirects/pagination, oversized/incomplete response rejection, local file reads after offline web errors, sidecars without FFmpeg and actual error propagation. BCM passed real duration, two-frame and embedded-subtitle extraction on a 2-second clip. These are tool-layer checks, not model visual-understanding, long-video, arbitrary-site or new GPU acceptance.

Align bilingual entry, offline/update docs and metadata. Require full tests, Ruff and CI on the exact release commit before creating annotated v1.3.7. Delete other tags as requested; retain historical record labels.

## Managed execution CPU validation (2026-11-19, development main)

- Linux AMD64, OpenCode 1.19.5, loopback mock model and isolated configuration/project/history: managed API/TUI follow-ups reached the model before a five-second command finished, about 0.157/0.391 s in individual runs. Each command ran once and completed normally. Synchronous Bash remains after_tool. This is not a live-model latency guarantee.
- check-execution.py controls passed: heartbeat freezes, new native/managed tools are blocked while paused, explicit resume proceeds, stop confirms no live owned group members, and one launch. denied passed: custom tooling cannot bypass native Bash denial.
- Engine unit coverage includes byte/Unicode cursors, stable keys, replay prevention, survival after launcher exit, pause/resume/stop, unrelated-process preservation, descendant cleanup, timeout, overflow, nonzero exits, private paths, cross-session/stale PID refusal, worker loss and failed startup checkpoints/worker copies.
- Native startup/resume, mouse mode and paste contracts passed. CI adds managed API/TUI, controls and denial checks, retaining private fixture artifacts.
- Live-model interpretation, remote scheduler/container cancellation, adoption of running ordinary tools, deliberate process-group escape, disconnected dependency completeness, reboot and automatic completion notifications are not validated. See [steering](client-steering.md) and [usage](execution.md).

All 313 Linux unittest cases passed, along with Ruff lint/format, patch checks and 50 packaged-document checks. Source and wheel include the new execution files. The first full run failed only because combined pause/resume/stop manual entries omitted complete command strings; separate entries fixed the contract, followed by a passing full run.
