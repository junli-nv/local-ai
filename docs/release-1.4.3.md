# v1.4.3：客户端安装自动应用个人工作指令

客户端安装默认将中文通用模板应用到实际运行用户的 OpenCode 全局 AGENTS.md，无需首次手工复制。install --role client/both 与低级 client install 均支持；server 角色不配置个人规则。

- --instructions general（默认）应用通用模板；bcm 应用通用加 BCM；none 保留个人规则原样，不删除已安装区块。
- --instructions-language zh（默认）/en 选择模板语言，不决定回复语言。
- 保留已有内容；改变前创建私有备份，原子替换目标。重复安装只更新 local-ai 管理区块，内容相同时不写入。
- 自定义规则放在管理区块外；符号链接、其他用户文件或损坏标记需修复或显式跳过。sudo/root 只配置运行用户，不推断聊天账户。
- 源码更新与导出不应用个人规则；升级后以实际聊天用户重新运行客户端安装即可应用新版模板，离线同样可用。退出并恢复 OpenCode 原会话后加载规则。

通用模板包含长任务等待与进度汇报约定，不设固定时间、行数或标题，不提供硬性计时保证。安装不启动 GPU，也不改模型、镜像或推理参数；沿用 v1.4.2 的用户本地历史与服务器解耦功能。步骤与备份恢复见[个人规则配置](../templates/opencode/agent-instructions.md)，验证范围见[验证记录](validation.md)。

按用户要求在通过 CI 的确切提交上创建 v1.4.3 附注标签，保留已有标签，不创建 GitHub Release。

[English](en/release-1.4.3.md)
