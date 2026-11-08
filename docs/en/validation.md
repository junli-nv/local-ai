# Validation record

[中文（默认）](../validation.md)

Dates: 2026-10-31 through 2026-11-01. Infrastructure hostnames, IPs, GPU UUIDs, credentials and raw
user logs are intentionally omitted from this public record.

The 2026-10-31 integration records below describe the previous client. Tunnel entries are historical; the current client uses API endpoints without built-in forwarding or a separate environment-doctor command. New local HTTP regressions cover direct connections, model checks, retry and no SSH subprocess. They do not constitute new GPU acceptance.

Version labels 1.0.0/1.1.0 below identify historical candidate checks whose tags were withdrawn. The current version is v1.3.1; each acceptance record retains its original date, method and limits. Tagging does not expand support.

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
