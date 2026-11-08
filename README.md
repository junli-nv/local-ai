# local-ai

在 GPU 服务器运行 vLLM，在 BCM 头节点运行 OpenCode。文件、Shell、Git、SSH 等工具由 BCM 上的当前用户执行。

当前版本为 v1.3.1，以下示例下载该标签的完整源码。./local-ai --version 应显示 1.3.1，实际验收范围与未覆盖平台见[验证记录](docs/validation.md)。

## 示例约定与文档入口

| 对象 | 全文统一含义 |
|---|---|
| GPU001 | 八卡 B300 服务节点，主流程使用 0–3 卡 |
| bcm-headnode / alice | BCM 头节点及客户端用户 |
| /raid/local-ai | 两端各自的安装根目录，解压目录就是安装目录 |
| /home/alice/project | BCM 上的任务工作目录 |
| a / 18000 | 主流程的实例名与 API 端口 |
| http://GPU001:18000/v1 | 模型地址，将 GPU001 换成实际主机名或 IP |

普通账户需相应 sudo / Docker 权限；root 可省略 sudo。默认数据目录跟随启动脚本位置。本流程不设置 LOCAL_AI_DATA_DIR 或 --data-dir。

| 文档 | 用途 |
|---|---|
| 本页 | 首次在线安装、启动、聊天、配置及迁移入口 |
| [部署指南](docs/deployment.zh-CN.md) | CDI、存储故障、实例重建、DSpark/预热与双实例 |
| [命令手册](docs/commands.md) | 参数、默认值、退出码、会话恢复与客户端版本 |
| [离线部署](docs/offline.md) | 已安装环境迁移，或联网准备后离线安装 |
| [架构](docs/architecture.md)、[开发指南](docs/development.md) | 模块设计、扩展和接手开发 |

[推理优化与引擎探索记录](docs/performance.md)保存 DSpark 参数依据、首次编译处理、SGLang 探索及后续复测方法，供继续开发参考。

v1.3.1 已包含聊天中按目录读取 PDF、图片、Word、Excel 和 PPT。使用方法、取得此更新及客户端转换依赖见[富文档指南](docs/documents.md)。

## 安装前提

GPU001 需 Linux、Python 3.10+、Bash、curl、tar、兼容 NVIDIA 驱动、支持 CDI 且 API 至少 1.49 的 Docker、NVIDIA Container Toolkit。先取得 GPU 使用权并确认资源充足。

BCM 需 Linux AMD64 或 ARM64、Python 3.10+、Bash、curl、tar、Git、rg 和 util-linux 的 script，且能访问 GPU001:18000；不需要 GPU、CUDA、Docker、Node.js 或 npm。工具任务使用 SSH 时另需 OpenSSH。

| 配置 | 服务端 CPU / 镜像平台 | 本机 GPU | Engram | 验证状态 |
|---|---|---|---|---|
| b300-tp4 | AMD64 / linux/amd64 | 4 张 B300 | GPU | 已实机验证 |
| b300-tp4-dspark | AMD64 / linux/amd64 | 4 张 B300 | GPU | 可选单用户配方，范围见验证记录 |
| b200-tp4-cpu | AMD64 / linux/amd64 | 4 张 B200 | CPU | 四卡 API 冒烟通过，范围见验证记录 |
| b200-tp4 | AMD64 / linux/amd64 | 4 张 B200 | GPU | 四卡 API 冒烟通过，范围见验证记录 |
| gb300-tp4 | ARM64 / linux/arm64 | 4 张 GB300/B300 | GPU | 未实机验证 |
| gb300-tp2 | ARM64 / linux/arm64 | 2 张 GB300/B300 | CPU | 上游配方，未实机验证 |

B200 部署及同条件 CPU/GPU Engram 对照见[部署指南](docs/deployment.zh-CN.md#b200-四卡实验性)。两套配置有独立的有限验收记录，不继承 B300 性能结论。v1.3.1 已包含两套 B200 配方，可用 ./local-ai profiles 核对。

BCM 架构独立选择。配置只使用同一 OS 可见的本地 GPU；GB300 TP2 检查 MemAvailable 至少 256 GiB，不能套用 B300 实测结论。

已验证基线为 Ubuntu 24.04、驱动 580.126.20、Docker 29.2.1、Toolkit 1.19.1。默认 DeepSeek-V4.1-Flash 模型约 510 GB；另留镜像、缓存及 dist/ 完整副本空间。模型 revision、镜像摘要和扩展方式见[开发指南](docs/development.md#模型与客户端兼容性)。

## 1. 在 GPU001 安装并启动

下载到空目录，检查 Docker、GPU 和 CDI：

```bash
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
curl -fL --retry 3 https://github.com/junli-nv/local-ai/archive/refs/tags/v1.3.1.tar.gz -o /tmp/local-ai-source.tar.gz
tar -xzf /tmp/local-ai-source.tar.gz --strip-components=1 -C /raid/local-ai
cd /raid/local-ai
./local-ai --version
./local-ai profiles
docker version
docker info --format 'Server={{.ServerVersion}} Driver={{.Driver}} Root={{.DockerRootDir}}'
nvidia-smi
nvidia-ctk cdi list
```

Docker 客户端必须能连接本机 Docker 守护进程。下面先完成 CDI 检查和配置，再安装模型、启动服务。

### 配置 GPU 的 CDI 设备定义（首次部署必查）

**在 GPU001 执行。** 新机器即使 nvidia-smi 正常，也需要核实 CDI 定义。nvidia-ctk cdi list 必须包含准备使用的每张卡的 nvidia.com/gpu=GPU-... UUID 别名；已有完整别名时无需重复生成。

若列表为空或缺少所选 UUID，系统有自动刷新服务时执行：

```bash
sudo systemctl restart nvidia-cdi-refresh.service
nvidia-ctk cdi list
```

如果提示 Unit nvidia-cdi-refresh.service not found，改用下面的手动生成方式。先确认 /etc/cdi 和 /var/run/cdi 中没有其他有效或冲突的 NVIDIA 定义；不要同时保留重复定义。

```bash
sudo install -d /etc/cdi
sudo nvidia-ctk cdi generate --device-name-strategy uuid --output=/etc/cdi/nvidia.yaml
nvidia-ctk cdi list
```

将列表与本机 GPU UUID 核对：

```bash
nvidia-smi --query-gpu=index,uuid --format=csv,noheader
```

**成功标志：** 准备使用的 0–3 号 GPU 均有对应的 nvidia.com/gpu=GPU-... 别名，且没有冲突错误。只有确认后才继续下方安装。仍缺别名或有重复定义时先停止排查，不能仅因 nvidia-smi 能看到 GPU 就继续启动。手动定义需在驱动、GPU 或 MIG 配置改变后重新生成。

首次 inspect 提示 No such image 可正常继续；随后 pull 若报 metadata.db 不存在，应停止安装，按[Docker 存储故障](docs/deployment.zh-CN.md#docker-存储故障)处理。Docker active 不代表存储正常；--data-dir 不迁移 Docker/containerd 数据库，多节点不能共享其活动数据库。

### 安装资源并启动实例

Docker 和 CDI 检查通过后：

```bash
./local-ai install --role server --profile b300-tp4
./local-ai server plan --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000
./local-ai server start --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000
./local-ai server status --name a
```

这条 server 安装命令保存推理配方，不设置 BCM 客户端的 endpoint；连接地址在第 2 步配置。install 优先复用本地资源，不启动 GPU。plan 生成计划；start 检查实时占用并启动，不会终止其他任务。

start 默认等待 600 秒，加载和编译期间显示 NOT READY 及日志位置。容器运行且 /health 返回 HTTP 200 后，终端和实例日志写入 READY。status 检查当前状态：就绪退出 0，未就绪退出 1，并说明原因。

| 查看内容 | GPU001 上的位置 / 命令 |
|---|---|
| 安装、下载、导出与管理命令 | /raid/local-ai/install.log |
| 权重加载、编译、预热和 READY | /raid/local-ai/instances/a/server.log |
| 实时进展 | tail -f /raid/local-ai/instances/a/server.log |
| 当前状态 | ./local-ai server status --name a |

等待不足可在 start 中加 --wait-timeout 1200。超时退出 1，Ctrl+C 返回 130，均保留容器；先查日志和 status。日志 READY 只代表当时结果，容器 running 或端口监听不代表当前就绪。

--host 0.0.0.0 监听所有 IPv4 网卡，参数默认仍为 127.0.0.1。BCM 使用宿主机地址，不能把 0.0.0.0 填入 endpoint。当前未配置 API key/HTTPS，应限制可信网络访问；已有实例改地址须[显式重建](docs/deployment.zh-CN.md#实例重建)。

偏向单用户生成速度时，可选 b300-tp4-dspark，并显式使用 --warmup 提前触发部分首次编译，操作见[部署指南](docs/deployment.zh-CN.md#单用户-dspark-与显式预热)。READY 只表示 API 健康，WARMUP COMPLETE 表示有限推理预热完成；已有实例更换配方须显式重建。

## 2. 在 BCM 安装并使用

在 bcm-headnode 以 alice 登录，下载到 BCM 自己的空目录：

```bash
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
curl -fL --retry 3 https://github.com/junli-nv/local-ai/archive/refs/tags/v1.3.1.tar.gz -o /tmp/local-ai-source.tar.gz
tar -xzf /tmp/local-ai-source.tar.gz --strip-components=1 -C /raid/local-ai
cd /raid/local-ai
```

**安装客户端，并可选设置默认连接地址：** 在 BCM 执行下面这条命令，将 GPU001 换成实际服务端地址：

```bash
./local-ai install --role client --endpoint http://GPU001:18000/v1
```

本例可选的初始地址在安装成功后写入 **BCM 的 /raid/local-ai/installation.json**。GPU 服务端安装不会设置 BCM 地址；后续通过下节的 config 修改。

默认地址不是安装必填项。如果不想设默认值，改用 ./local-ai install --role client，之后每次 chat 带 --endpoint 即可。已有客户端无需为每个服务重复安装。

已有客户端没有保存地址时，用 config set endpoint URL 配置默认值，或在 chat 中临时指定；修改连接配置无需安装操作。

创建或选择当前用户的工作目录：

```bash
mkdir -p /home/alice/project
```

本例安装时保存了 GPU001:18000，所以下面的 chat 可省略 --endpoint；没有保存默认值时，请在每条 chat 后加 --endpoint URL。

```bash
# 只检查 API 和模型，不生成内容
./local-ai chat --check
# 在 BCM 项目中交互聊天
./local-ai chat --project /home/alice/project
# 执行一次任务后退出；hostname 应返回 BCM 主机名
./local-ai chat --project /home/alice/project --run '请用 bash 执行 hostname 并报告实际输出。'
```

三条命令连接同一个 GPU001:18000 服务，分别演示检查、交互和单次任务。临时覆盖连接用 chat --endpoint URL，不会改写已保存的地址。第二实例的端口见[双实例](docs/deployment.zh-CN.md#双实例与多人使用)。

### 配置默认连接

在 BCM 的 /raid/local-ai 执行。例如保存 GPU001 为默认地址；更换时将 URL 替换成目标地址：

```bash
./local-ai config show
./local-ai config set endpoint http://GPU001:18000/v1
```

config 只修改设置，不安装、不下载，也不连接服务。config show 显示配置文件位置及已配置的 endpoint/model。也可直接编辑现有 /raid/local-ai/installation.json 的 endpoint/model 字段，保留其他字段和合法 JSON；下一次 chat 生效。show 中 null 表示未显式配置默认值。该文件属于本安装目录，目录使用者共享其默认值，修改需要文件写权限。

长期默认模型用 config set model ID 设置。config unset endpoint 清除默认地址，之后 chat 必须带 --endpoint；config unset model 恢复配方默认模型。它们不删除客户端、模型或历史。chat --endpoint/--model 仍只覆盖本次连接。

### 从同一个 BCM 连接多个服务

一套 BCM 客户端可连接多个节点。下面新增 GPU002，它已部署模型服务，API 同样使用 18000；本例两个节点的服务模型 ID 相同：

```bash
# 本次检查 GPU002
./local-ai chat --endpoint http://GPU002:18000/v1 --check
# 本次在 GPU002 上推理，工具仍在 BCM 执行
./local-ai chat --endpoint http://GPU002:18000/v1 --project /home/alice/project
# 不带覆盖参数，仍回到已保存的 GPU001
./local-ai chat --project /home/alice/project
```

chat --endpoint 不改写 installation.json，也不要求重新安装。--check 输出实际 endpoint 和 model，便于确认连到哪台服务。

如果 GPU002 使用不同模型，同时传 --model 服务模型ID。假设它发布的 ID 是 other-model，则本次检查为：

```bash
./local-ai chat --endpoint http://GPU002:18000/v1 --model other-model --check
```

--model 也只对本次生效；省略时仍用安装默认模型，不会自动猜测另一节点的模型。不匹配时错误会列出服务端发布的 ID。不同 endpoint 的历史和缓存分开保存；返回原 endpoint 可继续其原会话。用 chat --session ID 或 --continue 时，也须选择对应 endpoint；原生 opencode -s ID 恢复入口会查找原地址。

退出后可用原生提示的 opencode -s ses_... 恢复。首次 chat 创建 ~/.local/bin/opencode 恢复入口，并提示 PATH 或同名程序冲突；也可用 chat --session ID 或 chat --continue。默认关闭鼠标捕获及内置剪贴板快捷键，使用终端复制粘贴、键盘导航，详见[会话恢复与终端复制](docs/commands.md#恢复会话与终端复制)。

助手可排查硬件、开发脚本、配置服务，以及准备、提交和跟踪 Slurm/Kubernetes 作业。要求通过 SSH 到 GPU001 查询硬件时，使用当前账户权限；推理配方不限制运维查询的硬件型号。规则见 [AGENTS.md](AGENTS.md)，纯计划不探测硬件的约束仅针对 server plan --inventory。

## 更新已有安装

按[程序更新指南](docs/update.md)分别更新 GPU 和 BCM 的实际程序目录，保留资源、配置与运行实例。独立 scripts/update.py 支持指定标签、本地源码包和备份回退，不执行 install 或资源准备。v1.3.1 已包含更新脚本；旧安装没有脚本时，指南给出首次获取方法。

## 导出与离线安装

这是独立的迁移场景：服务端镜像和模型在**源 GPU 节点**导出，在**新 GPU 节点**校验、解压并执行 install --offline。BCM 导出通常只有客户端材料，不能替代 GPU 服务端部署包。

完整命令统一维护在[离线安装指南](docs/offline.md)，按起点选择：

- [从已有安装导出，再到新环境离线导入](docs/offline.md#场景一从已安装环境导出并迁移)。
- [从联网准备机备齐两端资源，再离线安装](docs/offline.md#场景二从联网环境下载并准备)。

两条路线均注明执行主机、转移文件、校验、离线导入和验收，包含 BCM 客户端部署。目标机驱动和 Docker 仍需预装，原实例和个人历史不随包迁移。开发检查见[开发指南](docs/development.md)。

---

[English README](README.en.md)
