# Inference optimization and engine exploration

This records the 2026-11-01 reasoning, parameter choices, failed approaches and follow-up work for developers. Operational commands belong in [deployment](deployment.md#single-user-dspark-and-explicit-warmup); measurements, versions and acceptance limits belong in [validation](validation.md). SGLang remains an experiment, outside installation and instance management.

## Identify the slow phase

The v1.3.4 GB200 TP4 candidate and Rubin TP2 framework have no performance results.
Rubin's 288GB/GPU informs capacity assessment; TP2 with CPU Engram offload is not a validated
speed optimization. Measure CPU/NVLink-C2C, NUMA, KV and kernel costs separately; see the
[dedicated guide](gb200-rubin.md) for candidates and blockers.

Separate weight loading, startup compilation, API health, first-request compilation, prefill, decoding and queueing. TTFT needs actual input tokens, prefix-cache state, concurrency and whether the first reasoning token counts. Decode tokens/s does not replace TTFT, and reasoning output is not the final answer.

Earlier work changed TP8/eager/CPU Engram into a combined GPU Engram/CUDA Graph configuration before comparing TP4. It supports the current TP4 baseline, but simultaneous changes prevent attributing improvements to TP count or one optimization alone. See validation for scope. Default b300-tp4 remains unchanged.

## RTX 6000D scope

Independent `rtx6000d-tp8` uses CPU Engram, eager, 32K, one sequence and text input. It does not enable the B300 DSpark/CUDA graph optimizations below. See [RTX 6000D](rtx6000d.md) for smoke tests, single-request latency and unvalidated work; these do not establish throughput differences or a performance ranking against B200/B300.

## What changed for vLLM DSpark

The separate b300-tp4-dspark recipe lives in [profiles.json](../../src/local_ai/profiles.json). It retains the model revision, image, TP4, GPU Engram, FP8 KV, 131072 context, four active sequences and 8192 batched tokens.

| Change | Tested value | Reason and next check |
|---|---|---|
| Speculation | method=dspark; num_speculative_tokens=5 | Improve single-request decoding; retest acceptance, memory and concurrency when changing draft length |
| Draft and verification | draft_sample_method=probabilistic; rejection_sample_method=block | Real target-model verification, without synthetic acceptance |
| Adaptive verification | enable_adaptive_verification=false | Keep this tested configuration fixed; compare alternatives independently |
| Graph capture | mode=0; FULL_DECODE_ONLY; sizes 6/12/24 | Validate together with five draft tokens and active-sequence settings; do not copy baseline 1/2/4 or assume future-version optimality |
| Compilation cache | TILELANG_CACHE_DIR=/root/.cache/tilelang; CUDA_CACHE_PATH=/root/.cache/nvidia | Use the existing per-instance cache mount for later starts without changing baseline identity |

The choice preserves both single-request improvement and concurrent-throughput regression. Reasoning budgets were not reduced to claim runtime acceleration; lower TTFT is not established. The four-configuration comparison, acceptance counters and basic checks live in validation.

## Addressing first-use compilation spikes

1. **Find actual compilation.** Runtime logs identified inference-time CuTeDSL MXFP8QuantizeSwizzledKernel and Triton _block_scores_kernel JIT. Healthy /health does not establish compilation coverage for business requests.
2. **Inspect actual cache paths.** This image defaults TileLang to ~/.tilelang/cache, outside the existing /root/.cache mount. Mounting the latter alone can lose that cache on recreation. The new recipe explicitly relocates it. Reuse depends on engine, architecture and settings and does not guarantee zero compilation.
3. **Add explicit inference warmup.** [warmup.py](../../src/local_ai/warmup.py) gets token IDs through /tokenize and sends exact-length requests to /v1/completions. Returned usage must match requested input/output lengths, avoiding nominal 8K prompts that are actually 9K. Fresh prefixes reduce prefix-cache interference.
4. **Cover multiple shapes.** Defaults use input lengths 1024/8192/32768, output 256, concurrency 1/2/4/8 and two passes, reduced when context requires. Eight requests include queueing beyond four active sequences. Two passes are not a guarantee against every later length or batch JIT.
5. **Expose distinct states.** READY means API health; WARMING, WARMUP COMPLETE and WARMUP INCOMPLETE appear in terminal/runtime logs. warmup.json binds to the spec fingerprint and container StartedAt; restart makes it stale. Status generates no requests; failure/cancellation retains the container.
6. **Separate migration from local caches.** Exports exclude instance caches and completion markers. Warm again on the destination GPU instead of inheriting source-machine completion claims.

Implementation spans [cli.py](../../src/local_ai/cli.py), [server.py](../../src/local_ai/server.py), [readiness.py](../../src/local_ai/readiness.py) and [installlog.py](../../src/local_ai/installlog.py). [Warmup regressions](../../tests/test_warmup.py) cover real HTTP shapes, failures, cancellation, duplicate locks and restart invalidation.

## What the SGLang exploration covered

Four configurations used the same allocated GPUs, weights and requests: vLLM baseline, vLLM DSpark, SGLang baseline and SGLang DSpark. SGLang enabled EP4; vLLM did not enable EP. This compares configurations without isolating every framework mechanism.

SGLang was 0.0.0.dev1+gda64c5cbb with Torch 2.13.0+cu130. The fixed AMD64 image was lmsysorg/sglang@sha256:4a5d132a06a77c8331e15845f2e925adc788b00105097ad55409afa3f4fa4860, a development image from that experiment, not a future installation default.

| SGLang parameter | Tested value |
|---|---|
| --tp / --ep-size | 4 / 4 |
| --context-length / --max-running-requests | 131072 / 4 |
| --chunked-prefill-size / --mem-fraction-static | 8192 / 0.8 |
| --kv-cache-dtype | fp8_e4m3 |
| --cuda-graph-max-bs-decode | 4 |
| --reasoning-parser / --tool-call-parser | auto / auto |
| --disable-flashinfer-autotune | Flag enabled |
| SGLANG_DEFAULT_THINKING | 1 |
| Additional DSpark flags | --speculative-algorithm DSPARK; --speculative-dspark-block-size 5 |

The entry point was python3 -m sglang.launch_server with --trust-remote-code, read-only weights and the same fixed image for both variants. Actual launch arguments, streaming requests, metrics and basic checks remain in the internal experiment directory; only sanitized summaries are public. This table does not establish local-ai SGLang support.

Long MHC/TileLang compilation and graph capture were observed. The variants ran sequentially with some shared disk caches, so startup durations were not used as a fair engine ranking. A /root/.cache mount does not establish persistence of ~/.tilelang. Shutdown SystemExit: 0 and CancelledError logs were distinguished from request-time errors.

SGLang showed competitive short-input/eight-concurrency throughput; those results and the vLLM JIT confound are preserved in validation. This remains a useful follow-up direction, not a failed-engine verdict.

vLLM better fit this measured workload, so the project retains one production engine plus an optional DSpark recipe. Dynamo routing/disaggregated prefill-decode and comprehensive SGLang tuning were not tested. No universal ranking across SGLang, Dynamo or other models follows.

## How to continue the investigation

- Record source commit, image digest, package versions, model revision/config hashes and complete engine arguments. Allocate GPUs and separate instances, ports and caches while preserving production. Keep raw infrastructure logs out of Git.
- Match payload hashes, actual token counts, sampling settings and output caps across engines. Record cold requests, prepared shapes, prefix-cache hits, 1/4/8 concurrency and errors, including spikes instead of selecting fastest results.
- For warmup A/B, use separate cold caches with the same DSpark recipe: API readiness only versus native start --warmup, then identical streaming requests. Restart the same instance to measure disk-cache reuse and verify stale warmup state. Non-streaming warmup does not replace streaming measurement.
- Compare TTFT, decoding, end-to-end latency and concurrent throughput. Small-sample maxima/P95 are not production SLAs. Extend checks to full answers, actual tool round trips and complex code tasks.
- For new SGLang versions, recheck flags, graphs, EP/TP, KV format and DeepSeek parsers. Validate an independent adapter and offline artifacts before adding an engine abstraction; do not pass vLLM arguments through unchanged.
- Change draft length, graphs, sequence count or reasoning budget as explicit independent factors. Retain the old configuration and measured rollback point. Follow deployment instructions to rebuild as b300-tp4; never implicitly stop production.
- This work also reproduced TIME_WAIT being mistaken for a live port conflict after HTTP shutdown. Preflight now uses SO_REUSEADDR while still rejecting active listeners. The real TCP regression is in [test_listen.py](../../tests/test_listen.py); do not bypass port protection to pass tests.

[中文（默认）](../performance.md)
