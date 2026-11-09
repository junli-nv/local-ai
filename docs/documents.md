# 在聊天中读取富文档

在 **BCM 客户端**使用普通聊天，文件必须能被当前账户读取。GPU 节点只接收模型请求；仅把文件放在 GPU 节点上不会让客户端自动看到它。目录可以是当前项目，也可以是你明确指定的其他本地目录。

v1.3.0 已包含本功能。已有安装按[程序更新指南](update.md)选择 --version v1.3.5，无需重新下载模型或镜像。

## 准备与使用

先在 BCM 的安装目录检查转换工具：

```bash
cd /raid/local-ai
./local-ai document doctor
```

DOCX、XLSX、PPTX 和 OpenDocument 的文字提取使用 Python 标准库，无须额外 Python 包。PDF、旧版 Office 和版面查看需要在 BCM 安装系统工具。Ubuntu/Debian 示例：

```bash
sudo apt-get install --no-install-recommends poppler-utils libreoffice-writer libreoffice-calc libreoffice-impress
./local-ai document doctor
./local-ai chat --endpoint http://GPU001:18000/v1 --project /home/alice/project
```

进入会话后直接说：

> 请查看 /home/alice/project/materials 下的 PDF、Word、Excel 和 PPT，总结部署要求，并注明文件、页码、工作表或幻灯片出处。涉及图表时查看页面图片。

不需要附件启动参数。每个新开或通过 local-ai 恢复的会话自动连接 documents_read_document 工具。升级前已打开的客户端须退出后重新进入；GPU 服务无需为客户端文档工具重启。

## 处理方式

| 格式 | 默认读取 | 查看排版、图片和图表 |
|---|---|---|
| PNG、JPEG、WebP、GIF | 图片传给支持图片输入的模型 | 同左；动画和复杂图像效果需另测 |
| PDF | 选定页面的文字与页面图片，包括扫描件 | 工具 render 模式返回页面图片 |
| DOCX/DOCM | 正文、表格文字、页眉页脚；不执行宏 | LibreOffice 转 PDF 后按页渲染 |
| XLSX/XLSM | 工作表名、可见性、单元格地址、原始值、公式与缓存值；不执行宏 | LibreOffice 转 PDF 查看图表与布局 |
| PPTX/PPTM | 按关系表顺序提取幻灯片文字与备注；不执行宏 | LibreOffice 转 PDF 查看幻灯片 |
| DOC、XLS、PPT、RTF | LibreOffice 转 PDF 后读取文字和页面图片 | 同左 |
| ODT、ODS、ODP | 提取正文或表格/页面文字 | LibreOffice 转 PDF 后按页渲染 |
| UTF-8 文本、Markdown、CSV/TSV、JSON、HTML/XML、源代码 | 文字读取；HTML/XML 不加载网页或执行脚本 | 没有浏览器式排版渲染 |

这里以 Codex 常见文档工作流作为体验参照，不声称所有格式、布局和识别效果与 Codex 相同。加密文档、复杂版式、嵌入对象、公式显示与特殊字体可能需要额外处理；音视频和任意二进制不是本功能的支持承诺。

默认一次读取 3 个页面/工作表/幻灯片，工具 start 从 1 开始，count 为 1–5；长文本每次最多 40,000 字符，next_offset 非空时继续读取。正文没有可靠页码时标注正文来源，不编造页数。模型应根据任务继续调用工具，不能把初次返回的部分内容当作全文。输入文件上限 100 MiB，单张返回图片上限 8 MiB。

Excel 文字读取不重新计算公式，缓存可能过期，日期可能显示为原始序列值。需要数值计算时另行校验；版面转换也可能重算或调整 Office 文件的显示。原文件不被写入。扫描件文字依靠视觉识别，关键参数、编号和表格应核对原页。

## 自检与排障

聊天中由模型调用工具；下面命令仅用于开发/排障，不是正常使用的必做步骤：

```bash
./local-ai document read /home/alice/project/materials/manual.pdf --mode text --start 1 --count 2
```

document read 返回工具结果 JSON；auto/render 可能包含 base64 图片，正常聊天不需要手工处理它。--offset 为当前选定范围内的字符偏移。失败时命令返回非零；聊天工具以 isError=true 报告实际错误，不伪造读取成功。

doctor 显示 pdf_ready 和 office_render_ready。缺少依赖时按错误提示在 **客户端**补齐；不需要重新下载模型。模型配方须正确声明 modalities.input 包含 image；仅文字模型可用 text 模式读取可提取的文字，不能识别扫描件或图表。

会话开始时打印的 Log 路径保存工具调用与错误；文件内容只作为参考资料，不成为执行命令的授权。

## 离线环境

local-ai export 会携带源码中的文档工具，但不会携带宿主机的 Poppler/LibreOffice。目标 BCM 必须通过适配其发行版和架构的系统软件源、离线仓库或管理员预置安装这些依赖，并运行 document doctor 确认。不能把另一台主机的 /usr/bin 程序直接复制当作完整离线安装。

[English version](en/documents.md)
