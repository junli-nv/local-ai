# v1.4.0 release notes

This release focuses on client task reliability and observability. Existing GPU recipe acceptance remains bounded by prior records.

- Private request diagnostics: actual API usage, first-content latency, request/tool timings and context use; missing cache details remain unknown.
- Context handoffs: retain native compaction/pruning, add objective/constraint/evidence/pending-work preservation requirements and /handoff.
- Task supervision: client tasks / client report, batch deadlines, progress, process-group cleanup and resume argv; no automatic replay of writes.
- Real workflow acceptance: isolated edit-test, diagnose and resume cases check actual files.
- Also releases earlier main-branch work: server benchmark, instruction templates and personal-rule forwarding.
- Reuse native dependency materials by client identity while preserving per-launch connection isolation.

## Validation and limits

OpenCode 1.19.5 remained the NPM latest release when checked; retain the validated client.
CPU regression, native tools/resume/compaction hooks and three small workflows against a real DeepSeek API are distinct checks.
They do not expand GPU recipe acceptance, complex long-context quality, sustained concurrency or real-GPU benchmark claims.
The current service omits per-request cached-token details; reports use null rather than global hit counters.
First content may be reasoning or tool calls. API time cannot be split into network, queue and prefill here.
Model summaries require verification, and resumption requires checking external effects. KV offloading remains low priority.

## Install and upgrade

Source includes Python, observer.mjs, templates, docs and tests, excluding weights, images, native binaries and private history.
Use [README](../../README.en.md) for installation or [program updates](update.md) on each existing host.
New or resumed client sessions load the changes; client features require no GPU-service restart.
Old launches are not backfilled. See [usage](commands.md#task-diagnostics-and-workflow-acceptance-v140).

[中文](../release-1.4.0.md)
