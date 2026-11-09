# 导出、转移与离线安装

本页统一维护完整迁移流程，与常规在线部署分开。场景一在旧 GPU 节点导出镜像和模型、在旧 BCM 导出客户端，再分别到目标端导入；场景二由联网准备机备齐两端材料。离线导入指校验、解压后执行 install --offline，没有另一个顶层 import 命令。

已有资源、只更新程序时，按[离线程序更新](update.md#离线更新程序)转移脚本与小型源码包即可，不必再次导出整套模型和镜像。

解压目录就是安装目录，本文统一为 /raid/local-ai。local-ai 是启动脚本，src/ 是源码，docs/ 是手册；models/、images/、clients/ 存放模型、镜像归档及锁、公共客户端；dist/ 存放导出包。默认路径随目录移动和改名，本文不设置 LOCAL_AI_DATA_DIR 或 --data-dir。

前置条件：Python 3.10+、Bash、curl、tar、sha256sum；GPU 主机另需兼容驱动、Docker API 1.49+、NVIDIA Container Toolkit/CDI；BCM 另需 Git、rg 和 util-linux script。使用 root 或有 sudo/Docker 权限的账户。示例为 Linux AMD64、四张已分配 B300、b300-tp4、实例 a。新 GPU001 与 bcm-headnode 可经内网 18000 端口通信。介质挂载到 /media/local-ai。模型约 510 GB，另留镜像和 dist/ 完整副本空间。新目标目录须为空。

包内含顶层 local-ai/ 和 bundle.json 校验清单。排除 dist/、实例状态、日志、临时缓存、Git 元数据、个人历史和凭据。Docker 活动数据库及驱动由宿主机管理。

下面两条路线各自完整，选择一条从头执行。gpu-old/bcm-old 是原有来源主机；prep-host 只联网准备，不启动 GPU。新目标沿用 README 的 GPU001/bcm-headnode。源码下载固定 v1.3.4；开发测试使用 main 时另行记录确切提交。

## 场景一：从已安装环境导出并迁移

### 1.1 在旧 GPU 主机 gpu-old 导出

起点为已按新版 README 安装的完整目录，包含 local-ai 和 src/；旧版只有数据时先执行文末准备命令。导出期间不更新模型。导出生成或复用本地镜像归档，不重新下载权重。

```bash
cd /raid/local-ai
./local-ai export
mkdir -p /media/local-ai/server
cp dist/local-ai.tar dist/local-ai.tar.sha256 /media/local-ai/server/
```

成功标志：介质 server/ 中已有 local-ai.tar 和校验文件，含程序、镜像和模型。

### 1.2 在旧 BCM 主机 bcm-old 导出

BCM 使用自己的完整安装目录；个人历史不导出。

```bash
cd /raid/local-ai
./local-ai export
mkdir -p /media/local-ai/client
cp dist/local-ai.tar dist/local-ai.tar.sha256 /media/local-ai/client/
```

将介质依次带到 GPU001 和 bcm-headnode，各挂载到 /media/local-ai。

### 1.3 在新 GPU 主机 GPU001 离线导入并启动

安装校验材料并导入本地镜像，不启动 GPU 服务；随后核实本机 CDI 和 GPU 分配再启动。

```bash
cd /media/local-ai/server
sha256sum -c local-ai.tar.sha256
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
tar -xf local-ai.tar --strip-components=1 -C /raid/local-ai
cd /raid/local-ai
./local-ai install --role server --profile b300-tp4 --offline
./local-ai server inventory
nvidia-ctk cdi list
./local-ai server start --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000
./local-ai server status --name a
```

成功标志：installed=true、offline=true，然后 READY、ready=true。

### 1.4 在新 BCM 主机 bcm-headnode 离线导入并连接

```bash
cd /media/local-ai/client
sha256sum -c local-ai.tar.sha256
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
tar -xf local-ai.tar --strip-components=1 -C /raid/local-ai
cd /raid/local-ai
./local-ai install --role client --offline --endpoint http://GPU001:18000/v1
./local-ai chat --check
./local-ai chat
```

成功标志：chat --check 返回 ready=true；聊天中实际执行 hostname，应返回新 BCM 主机名。

## 场景二：从联网环境下载并准备

### 2.1 在任意架构的 prep-host 准备目标资源

准备机 CPU 不必与目标 GPU 主机一致。服务端介质的主要内容是目标平台的 vLLM
镜像、固定 revision 的模型文件，以及源码和校验清单；模型与 Python 源码不区分
AMD64/ARM64，镜像必须按目标 profile 选择。下载和保存镜像不执行镜像。

本节改用 **AMD64 准备机、AMD64 BCM、ARM64 GB200 服务端**，因此目标配方为
gb200-tp4；它仍是未实机验收的候选，要求同一 OS 可见四张卡，见
[GB200 与 Rubin](gb200-rubin.md)。其他平台用自己的完整配方替换，不以准备机架构选配方。
准备机需 Python 3.10+、tar、sha256sum、Docker API 1.49+，可访问 GitHub、镜像仓库和公开的
Hugging Face 模型；准备阶段无需 GPU、驱动、CDI、ARM 仿真或 QEMU。

v1.3.7 已包含 prepare。下载固定标签的完整源码；解压目录仍是安装根：

```bash
local_ai_source=/tmp/local-ai-v1.3.7-source.tar.gz
curl -fL --retry 3 https://github.com/junli-nv/local-ai/archive/refs/tags/v1.3.7.tar.gz -o "$local_ai_source"
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
tar -xzf "$local_ai_source" --strip-components=1 -C /raid/local-ai
cd /raid/local-ai
./local-ai --version
./local-ai prepare --help
./local-ai prepare --profile gb200-tp4
```

成功标志：prepared=true、started=false；models/ 中有完整模型和 revision 锁，
images/ 中有 linux/arm64 镜像归档及内容锁。模型由准备机 Python 标准库通过 HTTP
下载，按文件长度及 Hub 内容标识校验，支持断点续传；不运行目标镜像或推理程序。
完整本地模型和镜像会复用，日志在 install.log。当前下载器面向公开模型，不读取或打包凭据。

如需在同一包内携带本例 AMD64 BCM 的客户端，在这台 AMD64 准备机执行：

```bash
cd /raid/local-ai
./local-ai install --role client --online
```

这一步需访问 NPM，只准备本机架构的 OpenCode，不要求 GPU。仅需服务端介质时省略；
准备机与 BCM 架构不同时，客户端按场景一的 BCM 路线单独准备，不能运行另一架构的客户端。
不要在准备机执行 install --role server/both 来替代跨平台 prepare。

### 2.2 导出到 dist/ 并复制到介质

```bash
cd /raid/local-ai
./local-ai export --profile gb200-tp4
mkdir -p /media/local-ai/both
cp dist/local-ai.tar dist/local-ai.tar.sha256 /media/local-ai/both/
```

导出时显式选择目标 profile。已执行可选客户端步骤时，同一包含 ARM64 服务端资源和 AMD64 客户端；否则仅供服务端使用。目标安装与启动仍检查实际 CPU、GPU 和 CDI。

多个目标平台可在同一准备目录中选择；相同 repo/revision 的完整模型会复用。
prepare 不写本机安装记录，因此 export 也须显式列出配方：

```bash
./local-ai prepare --profile b300-tp4 --profile gb200-tp4
./local-ai export --profile b300-tp4 --profile gb200-tp4 --output dist/local-ai-multi.tar
```

同一 model_directory 对应不同 repo/revision 时应分开准备目录，不能混装。

### 2.3 在新 GPU 主机 GPU001 离线导入并启动

```bash
cd /media/local-ai/both
sha256sum -c local-ai.tar.sha256
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
tar -xf local-ai.tar --strip-components=1 -C /raid/local-ai
cd /raid/local-ai
./local-ai install --role server --profile gb200-tp4 --offline
./local-ai server inventory
nvidia-ctk cdi list
./local-ai server start --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000
./local-ai server status --name a
```

成功标志：installed=true、offline=true、READY 和 ready=true。

### 2.4 在新 BCM 主机 bcm-headnode 离线导入并连接

```bash
cd /media/local-ai/both
sha256sum -c local-ai.tar.sha256
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
tar -xf local-ai.tar --strip-components=1 -C /raid/local-ai
cd /raid/local-ai
./local-ai install --role client --offline --endpoint http://GPU001:18000/v1
./local-ai chat --check
./local-ai chat
```

成功标志：chat --check 返回 ready=true；聊天中实际执行 hostname 验证工具运行位置。

## 更换目录名

同一归档也可解压到其他空目录，默认路径由新位置确定。

```bash
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/ai-prod
tar -xf /media/local-ai/server/local-ai.tar --strip-components=1 -C /raid/ai-prod
cd /raid/ai-prod
./local-ai install --role server --offline
```

## 旧版只有数据、没有程序时

先保存自定义源码修改。从 GitHub 获取完整程序并解压到原数据根目录；源码包不含模型或实例。

```bash
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
curl -fL --retry 3 https://github.com/junli-nv/local-ai/archive/refs/tags/v1.3.7.tar.gz -o /tmp/local-ai-source.tar.gz
tar -xzf /tmp/local-ai-source.tar.gz --strip-components=1 -C /raid/local-ai
cd /raid/local-ai
./local-ai --version
```

旧 GPU 主机复用本地资源并导出，不允许重新下载权重：

```bash
./local-ai install --role server --profile b300-tp4 --offline
./local-ai export
```

旧 BCM 客户端原位于用户目录时，首次导出指定实际程序目录：

```bash
./local-ai export --client-dir /home/alice/.local/state/local-ai/clients/amd64
```

## 导入后的配置与检查

v1.3.4 可携带 GB200/Rubin 配方定义与模拟清单；完整资源 export 不能选择
rubin-tp2-framework，因为镜像和显存门槛尚未核实。来源机未准备好的资源不会因导出
而变为可用，验收与候选镜像边界见[GB200 与 Rubin](gb200-rubin.md)。

GPU 启动前若缺少 UUID 别名，先完成[CDI 配置](deployment.zh-CN.md#cdi-配置)。

源端 endpoint 不随包迁移。新 BCM 示例在客户端初次安装时设置初始默认地址；后续用 config set endpoint URL，或编辑 config show 显示的文件，无需安装操作。本次连接用 chat --endpoint URL 选择其他可达内网服务；模型不同再传 --model ID。会话隔离见[多服务使用](../README.md#从同一个-bcm-连接多个服务)。

编译缓存和预热记录随实例状态一并排除。目标机安装、API 启动后按需执行[显式预热](deployment.zh-CN.md#单用户-dspark-与显式预热)；联网准备阶段不运行推理。

## 可选文档转换依赖

从包含富文档功能的版本导出时，包内携带文档 MCP 工具源码，但不携带宿主机 Poppler/LibreOffice 或可选 FFmpeg。网页和侧挂字幕仅用标准库；视频抽帧需另行准备目标 BCM 的 FFmpeg 系统包。使用 PDF、旧版 Office 或版面渲染前，须在目标 BCM 通过匹配的离线系统软件包准备依赖，见[文档离线要求](documents.md#离线环境)。

## 日志与失败处理

安装/导出看安装根目录的 install.log；启动看 instances/a/server.log。READY 由健康检查确认，容器存在不代表就绪。客户端输出私有会话 Log 路径。离线缺文件或校验失败会停止，不自动联网补下载。解决 CDI、网络、架构或资源错误后再继续。

详见[部署指南](deployment.zh-CN.md)、[命令手册](commands.md)和[验证记录](validation.md)。

---

[English version](en/offline.md)
