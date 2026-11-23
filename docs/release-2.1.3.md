# v2.1.3 后台通知去重与 BCM PDF 手册

后台任务的完整输出已交给助手后，完成通知只弹提示，不再插入消息、唤醒模型生成“已读完、无新指令”之类的重复回复。未读完的结果仍自动触发检查和续做。分页读取记录随任务保存；旧记录从最近 100 条原生会话中的真实工具输出补查，无法确认时保留自动处理。

BCM 模板优先检索 `/cm/shared/docs` 的手册，按版本、组件和 PDF 页码引用；补充 nodeinstaller 的 `/cm/node-installer` 位置。节点安装或启动问题可定向检查关联的 `/cm/images` 镜像，普通检索仍排除整个镜像目录，不全量扫描。

PDF 优先使用 Poppler，缺少文字工具时可使用独立环境中的可选 pypdf。`document setup-pdf` 准备用户私有虚拟环境，`--wheel-dir DIR` 支持本地 wheel 离线安装，不改系统 Python。缺少渲染器时 auto 返回文字及明确警告；pypdf 不提供 OCR，扫描件和图表仍需渲染及支持图片的模型。

在 BCM 更新程序后退出并恢复聊天；模型服务无需重启。以实际聊天用户重新应用 BCM 模板：

```bash
./local-ai install --role client --instructions bcm
```

没有 PDF 文字后端时，可由助手运行 `./local-ai document setup-pdf` 后重试读取；离线机需先准备 wheel。独立文档工具环境不随公共导出或历史迁移携带。保留原有标签。

[执行与通知](execution.md) · [PDF 备用后端](documents.md#v213pdf-文字备用后端) · [验证记录](validation.md) · [English](en/release-2.1.3.md)
