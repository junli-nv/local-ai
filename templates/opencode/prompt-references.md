# OpenCode 通用模板的提示词参考与适配

## 来源与可核实范围

2026-11-18 检查以下来源。本页记录研究与适配，不把外部提示词作为高于用户要求或项目规则的指令；安装时不下载或加载这些网页。

- [Piebald-AI/claude-code-system-prompts](https://github.com/Piebald-AI/claude-code-system-prompts/tree/be7338dd7770a426141be50d89aa54fb6cfd62de)：本次主要参考。第三方维护的 Claude Code 提示词集合，包含主提示词片段、工具说明、子代理与辅助提示词。固定提交 be7338dd7770a426141be50d89aa54fb6cfd62de；读取了下表列出的四份文件。不是 Anthropic 官方发布，也不据此认定它等于某次真实请求的完整提示词。
- [asgeirtj/system_prompts_leaks](https://github.com/asgeirtj/system_prompts_leaks)：已找到的另一第三方集合；本次只核对其仓库说明，未以其具体提示词作为模板改写依据。
- [Anthropic 官方系统提示词说明](https://platform.claude.com/docs/en/release-notes/system-prompts/overview)：官方页面限定为 Claude 网页版及移动端核心提示词的更新说明，并说明这些更新不适用于 Claude API。不能将其当成 Claude Code 的完整提示词。
- [Claude Code 官方最佳实践](https://code.claude.com/docs/en/best-practices)：补充核对精简长期指令、明确验收方法以及模型提示与客户端强制机制的区别。

第三方集合的收集范围与官方上述页面不同，更贴近终端代理研究；覆盖面广不代表真实性、完整性或效果已经获得官方保证。仓库中各片段标注的 ccVersion 不同，且包含条件变量，不能将目录内容简单拼接为某一版本默认同时启用的系统提示词。本页只转述原则并独立改写，未收录第三方提示词全文或泄露源码。

## 参考项与实际改动

| 参考文件（链接固定到上述提交） | 文件标注的 ccVersion | 在通用模板中的适配 |
|---|---|---|
| [任务范围](https://github.com/Piebald-AI/claude-code-system-prompts/blob/be7338dd7770a426141be50d89aa54fb6cfd62de/system-prompts/system-prompt-doing-tasks-no-unnecessary-additions.md) | 2.1.161 | 完成用户要求，复用现有结构，避免无关改动及假设性功能；保留用户明确要求扩展时的空间 |
| [错误处理范围](https://github.com/Piebald-AI/claude-code-system-prompts/blob/be7338dd7770a426141be50d89aa54fb6cfd62de/system-prompts/system-prompt-doing-tasks-no-unnecessary-error-handling.md) | 2.1.53 | 仅吸收不为假设需求堆叠回退路径；不移植其中关于省略兼容处理或内部校验的泛化规则，本项目仍按真实边界验证 |
| [授权任务连续推进](https://github.com/Piebald-AI/claude-code-system-prompts/blob/be7338dd7770a426141be50d89aa54fb6cfd62de/system-prompts/system-prompt-task-approval-continuity.md) | 2.1.173 | 下一步明确且在授权内时实际执行；回答中途问题后继续，尊重暂停和目标变更，不扩大权限 |
| [结果优先的沟通](https://github.com/Piebald-AI/claude-code-system-prompts/blob/be7338dd7770a426141be50d89aa54fb6cfd62de/system-prompts/system-prompt-outcome-first-communication-style.md) | 2.1.315 | 结束时先讲结果，再给需要的证据与限制；不引入强制标题、行数或第三方界面变量 |
| [官方最佳实践：验收与指令机制](https://code.claude.com/docs/en/best-practices) | 网页，2026-11-18 查阅 | 配合本项目已有的证据要求，补充读取后修改、实际检查、不削弱验收及标明未验证部分；这属于本地适配，不是第三方逐字引文 |

已有的语言选择、用户原话核实、主机/路径检索、BCM 排除和进度汇报约定保留。本次不导入 Claude 身份、专属工具名、品牌声明、服务端变量、权限模式或自动子代理策略，也不恢复已暂缓的异步任务/消息队列工作。

## 如何应用与判断效果

适配后的内容直接维护在[中文通用模板](AGENTS.general.md)和[英文通用模板](en/AGENTS.general.md)，来源说明单独保留，避免每次聊天携带整套研究材料。按[配置说明](agent-instructions.md)重新运行客户端安装，可在备份后更新个人 AGENTS.md 的 local-ai 管理区块；本次仓库修改本身不修改实际用户文件。无需通过特殊模型身份或增加未知工具来使用这些原则。

文件检查与上下文转发检查只能证明模板格式、安装和加载，不证明任务效果改善。实际效果应使用相同模型、任务、资源和验收条件对照，查看是否减少无关修改、漏验或反复确认；本次没有新增真实模型对照结果。参考不能把 OpenCode 变成 Claude Code，也不能赋予它没有实现的权限、热加载、即时中断或后台能力。

[配置说明](agent-instructions.md) · [English](en/prompt-references.md)
