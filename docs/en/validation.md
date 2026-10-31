# Validation record

[中文（默认）](../validation.md)

Date: 2026-10-31. Infrastructure hostnames, IPs, GPU UUIDs, credentials and raw
user logs are intentionally omitted from this public record.

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
- Fresh offline server deployment on another host and real large image-export
  roundtrip across Docker/storage-backend versions.
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
