# Prompt references and adaptations for the OpenCode general template

## Sources and verification scope

Reviewed on 2026-11-18. These sources inform local adaptations, not instructions above user requests or project rules. Installation does not download or load these pages.

- [Piebald-AI/claude-code-system-prompts](https://github.com/Piebald-AI/claude-code-system-prompts/tree/be7338dd7770a426141be50d89aa54fb6cfd62de) is the main reference: a third-party Claude Code collection of main-prompt fragments, tool descriptions, subagent and utility prompts. Pinned commit: be7338dd7770a426141be50d89aa54fb6cfd62de. Read the four files listed below. This is not an Anthropic release or proof of a complete prompt used in a real request.
- [asgeirtj/system_prompts_leaks](https://github.com/asgeirtj/system_prompts_leaks) is another located collection. Only its repository description was checked; no individual prompt from it informed template changes.
- [Anthropic's official system-prompt overview](https://platform.claude.com/docs/en/release-notes/system-prompts/overview) covers core web/mobile prompt updates and states they do not apply to the Claude API. It is not the complete Claude Code prompt.
- [Official Claude Code best practices](https://code.claude.com/docs/en/best-practices) supplements the review with concise persistent instructions, verifiable acceptance and the distinction between model instructions and enforced client behavior.

The third-party collection covers different material from that official overview and is more relevant to terminal agents. Breadth does not establish official authenticity, completeness or effectiveness. Files carry different ccVersion values and conditional variables; concatenating the directory does not reconstruct one version's simultaneously enabled default prompt. Principles are paraphrased and independently adapted here, without copying full third-party prompts or leaked source code.

## Reference-to-change mapping

| Reference file, pinned to the commit above | File's ccVersion label | General-template adaptation |
|---|---|---|
| [Task scope](https://github.com/Piebald-AI/claude-code-system-prompts/blob/be7338dd7770a426141be50d89aa54fb6cfd62de/system-prompts/system-prompt-doing-tasks-no-unnecessary-additions.md) | 2.1.161 | Complete the request using existing structures; avoid unrelated changes and hypothetical features, while allowing user-requested expansion |
| [Error-handling scope](https://github.com/Piebald-AI/claude-code-system-prompts/blob/be7338dd7770a426141be50d89aa54fb6cfd62de/system-prompts/system-prompt-doing-tasks-no-unnecessary-error-handling.md) | 2.1.53 | Avoid speculative fallbacks; do not import broad advice to omit compatibility handling or internal checks; preserve validation of actual boundaries |
| [Approved-task continuity](https://github.com/Piebald-AI/claude-code-system-prompts/blob/be7338dd7770a426141be50d89aa54fb6cfd62de/system-prompts/system-prompt-task-approval-continuity.md) | 2.1.173 | Execute decided authorized steps and continue after mid-task questions, respecting pauses and objective changes without expanding permissions |
| [Outcome-first communication](https://github.com/Piebald-AI/claude-code-system-prompts/blob/be7338dd7770a426141be50d89aa54fb6cfd62de/system-prompts/system-prompt-outcome-first-communication-style.md) | 2.1.315 | Give results before supporting evidence and limitations; no mandatory headings, line limits or third-party UI variables |
| [Official best practices: verification and instruction mechanisms](https://code.claude.com/docs/en/best-practices) | Web page reviewed 2026-11-18 | Extend existing local evidence requirements with reading before changes, actual checks, unchanged acceptance criteria and explicit unverified scope; this is local adaptation, not a third-party quotation |

Keep existing language, user-attribution, host/path discovery, BCM exclusions and progress guidance. Do not import Claude identity, exclusive tool names, branding, server variables, permission modes or automatic subagent policies. This does not resume deferred async-task/message-queue work.

## Application and evaluation

Adaptations live directly in the [Chinese general template](../../templates/opencode/AGENTS.general.md) and [English general template](../../templates/opencode/en/AGENTS.general.md). References stay separate to avoid loading the research collection into every chat. Follow [setup](../../templates/opencode/en/agent-instructions.md) and rerun client installation to back up and update the managed block in personal AGENTS.md. Repository edits alone do not change actual personal files. No special model identity or nonexistent tools are required.

File/context checks establish formatting, installation and delivery, not improved task performance. Compare identical models, tasks, resources and acceptance criteria to measure unrelated edits, missing verification and repeated confirmation. No new live-model comparison was performed. References do not turn OpenCode into Claude Code or add unimplemented permissions, hot reload, immediate interruption or background capabilities.

[Setup](../../templates/opencode/en/agent-instructions.md) · [中文](../prompt-references.md)
