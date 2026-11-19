# v2.0.3：交互会话的退出恢复提示

按 Ctrl-C 退出 local-ai 交互聊天后，复制屏幕上的 local-ai chat --session 命令可恢复原会话。命令携带原项目和历史路径，保留临时指定的模型或 endpoint；一般会话继续使用当前保存的默认连接。

已用 OpenCode 1.19.5 验证 Ctrl-C、带空格的项目路径及复制命令后的恢复。已有客户端进程在下次重新启动后加载新提示。

[命令手册](commands.md#恢复会话与终端复制) · [English](en/release-2.0.3.md)
