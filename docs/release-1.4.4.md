# v1.4.4：通用工作指令与消息响应基线检查

通用 OpenCode 模板增加修改前阅读、控制改动范围、实际验证、授权任务连续执行和结果优先汇报约定。参考 Claude Code 第三方提示词整理，来源、固定提交及改写对应关系见[参考说明](prompt-references.md)。BCM 模板保持原有职责。

- 模板随源码和离线包携带；参考说明位于 docs/，安装及聊天无需联网下载提示词。
- 沿用 v1.4.3 的个人规则自动安装。更新源码后，以实际聊天用户运行 ./local-ai install --role client（BCM 可加 --instructions bcm），更新个人管理区块；退出并恢复 OpenCode 后加载。独立更新器不应用规则。
- 新增 scripts/check-steering.py，在隔离配置和本地模拟模型下测量 API/TUI 补充消息。Linux AMD64/OpenCode 1.19.5 基线显示收件较快，但模型交付均在五秒命令结束之后；尚未实现即时响应、异步执行或停止能力。操作与边界见[消息响应检查](client-steering.md)。
- 记录保留 tar、优先改善外层归档解压时间的低优先级需求，本版未更改包格式或宣称性能提升。

验证范围见[验证记录](validation.md)。按用户要求在通过 CI 的确切提交上创建并推送 v1.4.4 附注标签，保留已有标签，不创建 GitHub Release。

[English](en/release-1.4.4.md)
