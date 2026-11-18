# 导出、转移与离线安装

只更换 GPU 服务节点、保留原 BCM 时，无须复制会话数据库。v1.4.2 起默认和临时 endpoint 共用本地历史；旧版记录按[恢复步骤](commands.md#更换服务器并保留会话)兼容一次。换 BCM 的私人历史迁移不属于公共离线导出。

在 airgap 环境中，启动聊天时使用 `npm_config_offline=true ./local-ai chat`；尚未保存默认地址时加 `--endpoint http://GPU001:18000/v1`。`install --offline` 只控制安装阶段，不会为后续 OpenCode 启动持久设置 npm 离线模式。该环境变量避免原生依赖初始化等待外部 npm registry；模型 API 仍通过内网访问。不想每次输入前缀时，按下方[持久设置 npm 离线模式](#持久设置-npm-离线模式)配置一次。本地 observer 仅使用原生运行时内置模块；离线标志下的工具、恢复与压缩验收已通过。

v1.4.3 的 observer.mjs 随 src/ 导出；原生依赖运行缓存、诊断和工作流结果不属于公共离线材料。

v1.4.3 的完整导出包含 templates/，不携带个人 AGENTS.md。目标机客户端安装默认离线应用通用模板，可选 --instructions bcm、--instructions-language en；准备机只打包公共客户端时加 --instructions none。用户私有规则仍需另行安全迁移，模板管理区块外的内容保留；详见[持久工作指令配置](../templates/opencode/agent-instructions.md)。

本页统一维护完整迁移流程，与常规在线部署分开。场景一在旧 GPU 节点导出镜像和模型、在旧 BCM 导出客户端，再分别到目标端导入；场景二由联网准备机备齐两端材料。离线导入指校验、解压后执行 install --offline，没有另一个顶层 import 命令。

已有资源、只更新程序时，按[离线程序更新](update.md#离线更新程序)转移脚本与小型源码包即可，不必再次导出整套模型和镜像。

解压目录就是安装目录，本文统一为 /raid/local-ai。local-ai 是启动脚本，src/ 是源码，docs/ 是手册；models/、images/、clients/ 存放模型、镜像归档及锁、公共客户端；dist/ 存放导出包。默认路径随目录移动和改名，本文不设置 LOCAL_AI_DATA_DIR 或 --data-dir。

前置条件：Python 3.10+、Bash、curl、tar、sha256sum；GPU 主机另需兼容驱动、Docker API 1.49+、NVIDIA Container Toolkit/CDI；BCM 另需 Git、rg 和 util-linux script。使用 root 或有 sudo/Docker 权限的账户。示例为 Linux AMD64、四张已分配 B300、b300-tp4、实例 a。新 GPU001 与 bcm-headnode 可经内网 18000 端口通信。介质挂载到 /media/local-ai。模型约 510 GB，另留镜像和 dist/ 完整副本空间。新目标目录须为空。

包内含顶层 local-ai/ 和 bundle.json 校验清单。排除 dist/、实例状态、日志、临时缓存、Git 元数据、个人历史和凭据。Docker 活动数据库及驱动由宿主机管理。

下面两条路线各自完整，选择一条从头执行。gpu-old/bcm-old 是原有来源主机；prep-host 只联网准备，不启动 GPU。新目标沿用 README 的 GPU001/bcm-headnode。源码下载固定 v1.4.3；开发测试使用 main 时另行记录确切提交。

## 进入 airgap 环境前准备 Docker

目标 GPU 节点即使已有 NVIDIA 驱动，也可能没有 Docker。local-ai 的导出包不包含 Docker Engine、containerd 或宿主机系统依赖；须在导入服务端镜像前单独准备并安装。BCM 只运行客户端时不需要 Docker。

Ubuntu 可参考 Docker 官方的[通过软件包安装](https://docs.docker.com/engine/install/ubuntu/#install-from-a-package)：在联网环境按**目标节点的 Ubuntu 版本/代号及 CPU 架构**下载 `.deb`，随介质带入。B300 示例使用 `amd64`，GB300 示例使用 `arm64`，不能按准备机架构选包。准备配套版本的 `docker-ce`、`docker-ce-cli`、`containerd.io`；官方完整安装流程另列 `docker-buildx-plugin` 和 `docker-compose-plugin`。同时备齐目标系统尚缺的依赖包，或提供可访问的内网 APT 镜像；只复制软件源配置不能让断网节点访问外部仓库。

目标 GPU 节点安装后启动 Docker，以运行 local-ai 的账户执行 `docker version` 和 `docker info`，确认能连接守护进程，且 **Server API 至少为 1.49**。版本要求及软件包冲突处理见[软件前提](prerequisites.md)。已有 GPU 驱动不代表 NVIDIA Container Toolkit/CDI 已配置，仍须按[CDI 配置](deployment.zh-CN.md#cdi-配置)核实；缺少的系统包同样提前备齐。官方步骤中的 `docker run hello-world` 会尝试下载本地没有的测试镜像；严格离线时须预先携带该镜像，不能将外网下载失败当作 Docker 安装失败。

## 持久设置 npm 离线模式

`npm_config_offline=true` **仅用于 offline/airgap 环境**，让 OpenCode 初始化依赖时不等待外部 npm 仓库；在线环境不要设置这一行。`PATH` 和 Bash 补全设置在线、离线均可使用。此变量不是 `opencode.json` 的配置字段，`install --offline` 也不会自动持久设置它。

对于所有用户共用 `/raid/local-ai` 的专用 airgap 客户端节点，建议由管理员统一配置 `/etc/profile.d/local-ai.sh`。在**实际运行聊天的节点**设置：本例为 bcm-headnode；若直接在 GPU 节点聊天，则配置该 GPU 节点。管理员创建或编辑此文件，保留已有需要的内容，加入：

```bash
# 仅 offline/airgap 环境设置；在线环境删除此行。
export npm_config_offline=true

# 以下 PATH 与 Bash 补全设置在线、离线均可使用。
export PATH="/raid/local-ai:$PATH"

# /etc/profile.d/ 也可能被其他 shell 读取，仅在交互式 Bash 中加载补全。
if [ -n "${BASH_VERSION:-}" ]; then
    if [[ $- == *i* ]] && command -v local-ai >/dev/null 2>&1; then
        eval "$(local-ai completion bash)"
    fi
fi
```

文件由 root 管理，所有用户可读（通常权限为 0644，无需可执行）；按实际安装目录调整 PATH。此系统级设置作用于该节点所有加载它的用户，npm 离线设置也会影响继承此变量的其他 npm 操作。

Ubuntu 的 `/etc/profile` 通常会加载 `/etc/profile.d/*.sh`，因此重新登录 Bash 后生效。当前已打开的 Bash 终端，以**运行聊天的用户**（本例 alice）执行：

```bash
source /etc/profile.d/local-ai.sh
printenv npm_config_offline
command -v local-ai
```

在 offline/airgap 环境中应分别输出 `true` 和 `/raid/local-ai/local-ai`。之后从任意任务目录直接执行 `local-ai chat`；恢复会话执行 `opencode -s ID`，将 ID 换成退出时显示的实际标识。尚未保存 endpoint 时，仍须在 chat 后加 `--endpoint http://GPU001:18000/v1`。

非登录 Bash 不会自动读取 `/etc/profile`，应从已加载设置的父进程继承环境，或在该终端手动 source 上述文件。交互式非登录 Bash 如需自动加载补全，可在个人 `~/.bashrc` 中按需 source 该文件。

仅为个人配置、没有管理员权限或不希望影响全体用户时，可在聊天用户的 `~/.profile` 中添加 `export npm_config_offline=true`（仍仅限 offline/airgap 环境），再执行 `source ~/.profile`。Bash 登录时优先读取 `~/.bash_profile`、`~/.bash_login`、`~/.profile` 中第一个存在的文件；若前两者存在，须确保它会加载 `~/.profile`。这些设置不自动迁移到其他节点或账号。将节点改回在线用途时，移除相应启动文件中的 npm 离线设置，并在现有终端执行 `unset npm_config_offline`。

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
systemctl status nvidia-cdi-refresh.service nvidia-cdi-refresh.path --no-pager
nvidia-ctk cdi list
```

先判读刷新状态：.service 是一次性任务，inactive (dead) 且最近一次 status=0/SUCCESS 可正常；.path 通常应为 enabled、active (waiting)。status 非零或 Unit not found 时，按 [CDI 配置](../README.md#配置-gpu-的-cdi-设备定义首次部署必查)检查日志、刷新或手动生成，不能只凭状态码判定失败。确认所选 0–3 卡的 UUID 别名完整且无冲突后，再启动：

```bash
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
npm_config_offline=true ./local-ai chat --check
npm_config_offline=true ./local-ai chat
```

成功标志：chat --check 返回 ready=true；聊天中实际执行 hostname，应返回新 BCM 主机名。

## 场景二：从联网环境下载并准备

### 2.1 在任意架构的 prep-host 准备目标资源

准备机 CPU 不必与目标 GPU 主机一致。服务端介质的主要内容是目标平台的 vLLM
镜像、固定 revision 的模型文件，以及源码和校验清单；模型与 Python 源码不区分
AMD64/ARM64，镜像必须按目标 profile 选择。下载和保存镜像不执行镜像。

本节改用 **AMD64 准备机、AMD64 BCM、ARM64 GB300 服务端**，因此目标配方为
gb300-tp4，要求同一 OS 可见四张 GB300/B300，每卡至少 250000 MiB 显存。
该配方已由用户确认实体机验证通过；GB300 TP2 仍未验证。具体[验证范围](validation.md#b200gb300-四卡实机状态确认2026-11-17)独立记录，不套用 B300 性能结论。
其他平台用自己的完整配方替换，不以准备机架构选配方。
准备机需 Python 3.10+、tar、sha256sum、Docker API 1.49+，可访问 GitHub、镜像仓库和公开的
Hugging Face 模型；准备阶段无需 GPU、驱动、CDI、ARM 仿真或 QEMU。

v1.4.3 已包含 prepare。下载固定标签的完整源码；解压目录仍是安装根：

```bash
local_ai_source=/tmp/local-ai-v1.4.3-source.tar.gz
curl -fL --retry 3 https://github.com/junli-nv/local-ai/archive/refs/tags/v1.4.3.tar.gz -o "$local_ai_source"
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
tar -xzf "$local_ai_source" --strip-components=1 -C /raid/local-ai
cd /raid/local-ai
./local-ai --version
./local-ai prepare --help
./local-ai prepare --profile gb300-tp4
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
./local-ai export --profile gb300-tp4
mkdir -p /media/local-ai/both
cp dist/local-ai.tar dist/local-ai.tar.sha256 /media/local-ai/both/
```

导出时显式选择目标 profile。已执行可选客户端步骤时，同一包含 ARM64 服务端资源和 AMD64 客户端；否则仅供服务端使用。目标安装与启动仍检查实际 CPU、GPU 和 CDI。

多个目标平台可在同一准备目录中选择；相同 repo/revision 的完整模型会复用。
prepare 不写本机安装记录，因此 export 也须显式列出配方：

```bash
./local-ai prepare --profile b300-tp4 --profile gb300-tp4
./local-ai export --profile b300-tp4 --profile gb300-tp4 --output dist/local-ai-multi.tar
```

同一 model_directory 对应不同 repo/revision 时应分开准备目录，不能混装。

### 2.3 在新 GPU 主机 GPU001 离线导入并启动

```bash
cd /media/local-ai/both
sha256sum -c local-ai.tar.sha256
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
tar -xf local-ai.tar --strip-components=1 -C /raid/local-ai
cd /raid/local-ai
./local-ai install --role server --profile gb300-tp4 --offline
./local-ai server inventory
systemctl status nvidia-cdi-refresh.service nvidia-cdi-refresh.path --no-pager
nvidia-ctk cdi list
```

先判读刷新状态：.service 是一次性任务，inactive (dead) 且最近一次 status=0/SUCCESS 可正常；.path 通常应为 enabled、active (waiting)。status 非零或 Unit not found 时，按 [CDI 配置](../README.md#配置-gpu-的-cdi-设备定义首次部署必查)检查日志、刷新或手动生成，不能只凭状态码判定失败。确认所选 0–3 卡的 UUID 别名完整且无冲突后，再启动：

```bash
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
npm_config_offline=true ./local-ai chat --check
npm_config_offline=true ./local-ai chat
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
curl -fL --retry 3 https://github.com/junli-nv/local-ai/archive/refs/tags/v1.4.3.tar.gz -o /tmp/local-ai-source.tar.gz
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

当前版本可携带 GB200/Rubin 配方定义与模拟清单；完整资源 export 不能选择
rubin-tp2-framework，因为镜像和显存门槛尚未核实。来源机未准备好的资源不会因导出
而变为可用，验收与候选镜像边界见[GB200 与 Rubin](gb200-rubin.md)。

GPU 启动前若缺少 UUID 别名，先完成[CDI 配置](deployment.zh-CN.md#cdi-配置)。

源端 endpoint 不随包迁移。新 BCM 示例在客户端初次安装时设置初始默认地址；后续用 config set endpoint URL，或编辑 config show 显示的文件，无需安装操作。本次连接用 chat --endpoint URL 选择其他可达内网服务；模型不同再传 --model ID。会话隔离见[多服务使用](../README.md#从同一个-bcm-连接多个服务)。

编译缓存和预热记录随实例状态一并排除。目标机安装、API 启动后按需执行[显式预热](deployment.zh-CN.md#单用户-dspark-与显式预热)；联网准备阶段不运行推理。

包含 benchmark 功能的源码可在离线目标 GPU 上按[本机性能测试](commands.md#本机性能测试)测量已启动实例，
无需联网或额外依赖。benchmark JSON 与其他实例状态一样不随导出迁移，目标机需重新测量。v1.4.3 已包含此命令。

## 可选文档转换依赖

从包含富文档功能的版本导出时，包内携带文档 MCP 工具源码，但不携带宿主机 Poppler/LibreOffice 或可选 FFmpeg。网页和侧挂字幕仅用标准库；视频抽帧需另行准备目标 BCM 的 FFmpeg 系统包。使用 PDF、旧版 Office 或版面渲染前，须在目标 BCM 通过匹配的离线系统软件包准备依赖，见[文档离线要求](documents.md#离线环境)。

## 日志与失败处理

安装/导出看安装根目录的 install.log；启动看 instances/a/server.log。READY 由健康检查确认，容器存在不代表就绪。客户端输出私有会话 Log 路径。离线缺文件或校验失败会停止，不自动联网补下载。解决 CDI、网络、架构或资源错误后再继续。

若服务端已 READY、`chat --check` 返回 ready=true，但 OpenCode 启动一直等待，先用 `printenv npm_config_offline` 确认输出为 `true`，或在启动命令前加 `npm_config_offline=true`。`--check` 只检查模型连接，不能证明原生客户端已正常启动。可在 BCM 的 /raid/local-ai 下执行完整聊天冒烟：

```bash
npm_config_offline=true ./local-ai chat --run 'Reply with exactly LOCAL_AI_OK. Do not use any tools.' --run-timeout 40 --heartbeat 10
```

成功标志：实际返回 `LOCAL_AI_OK` 且退出码为 0。用户反馈该方式在 airgap 环境约 9 秒完成；这是单次聊天验证，不代表所有依赖都已齐备。若仍提示缺少依赖，需在联网环境准备匹配客户端的依赖后重新导出，离线标志不会补齐缺失文件。长期使用按[持久设置 npm 离线模式](#持久设置-npm-离线模式)配置，避免每次手动输入前缀。

详见[部署指南](deployment.zh-CN.md)、[命令手册](commands.md)和[验证记录](validation.md)。

---

[English version](en/offline.md)
