# 中文部署指南

默认拓扑：**GPU 服务器只运行推理服务；BCM 头节点运行 OpenCode 和工具。**
源码可复制到两端，但模型、镜像和用户会话不放进 GitHub。

## 本文示例环境

| 主机名 | 角色 | 在这台机器上执行什么 |
|---|---|---|
| `GPU001` | GPU 服务节点，示例为 8 卡 B300 | 下载镜像和权重、启动或停止推理服务、检查健康状态 |
| `bcm-headnode` | BCM 头节点 | 以 `alice` 登录，安装客户端，在 `/home/alice/project` 中运行 OpenCode |

将这两个主机名替换为实际环境。示例假设 BCM 可访问 GPU001 的模型 API。
实例 `a`、`b` 是同一 GPU 节点上的服务名字，不是主机名。

完整子命令、参数默认值和排障步骤见[使用手册](commands.md)。

## 1. 先选服务端配置

| 配置 | 服务端 CPU | 同一 OS 可见 GPU 数 | Engram | 验证情况 |
|---|---|---:|---|---|
| b300-tp4 | x86_64 | 4 | GPU 常驻 | B300 参数已实测 |
| gb300-tp4 | aarch64 | 4 | GPU 常驻 | 尚未在 GB300 实机验证 |
| gb300-tp2 | aarch64 | 2 | CPU offload | 依据上游配方，尚未实机验证 |

先在 GPU 服务器执行 uname -m、nvidia-smi 确认实际平台。
GB300 服务端用 ARM64 镜像，不代表 BCM 也要用 ARM64 客户端。
BCM 的客户端架构由 BCM 自己决定。

GB300 若一个 OS 只看到两卡，应考虑 TP2 和足够的主存；不能在四卡配置中
填入别的主机的 GPU。当前不提供跨主机 TP 或整柜 NVL72 调度。
TP2 Engram offload 本身约占 189 GiB 主存，另需加载、运行和系统空间。
该实验配置会检查 MemAvailable 至少 256 GiB，这是保守保护值，不是实测最低需求。
GB300 配置必须完成实机验收，不能直接套用 B300 的速度结论。

## 2. GPU 服务器准备

部署账户须能运行 Docker 并写入所选数据目录；这些权限由管理员预先配置。

示例使用以下参数；换机器部署时，主要调整配置、GPU 和数据目录：

| 参数 | 示例含义 / 如何修改 |
|---|---|
| `--profile b300-tp4` | 使用 B300 四卡推理配置；TP4 表示同一实例跨 4 张本机 GPU。其他平台按上表选择。 |
| `--data-dir /raid/local-ai` | 存放权重、镜像锁文件、缓存和日志；不是 Git 源码目录。可改为容量足够的本地目录。 |
| `--gpus 0,1,2,3` | 使用服务端 `nvidia-smi` 显示的这 4 张卡；也可写完整 GPU UUID。数量须匹配配置。 |
| `--name a` | 自定义实例名，用于区分容器与日志；查询、停止时沿用同一个名字。 |
| `--port 18000` | 模型 HTTP API 端口，默认 18000；第二个实例换成 18001。 |

`server plan/start` 默认配置为 `b300-tp4`，实例名默认 `a`，但必须显式指定 `--gpus`。
数据目录默认取环境变量 `LOCAL_AI_DATA_DIR`，未设置时为 `/raid/local-ai`。
若修改目录，下载、计划和启动时须使用同一个 `--data-dir`，参数不会由前一条命令自动继承。

前提：驱动、Docker、NVIDIA Container Toolkit 已安装且兼容。
Python3 至少 3.10，Docker API 至少 1.49。数据目录示例 /raid/local-ai，源码目录与数据目录分开。
先确认选定 GPU 可用且已取得使用权；本工具不会停止其他作业。

在 GPU 服务器运行：
```bash
git clone https://github.com/junli-nv/local-ai.git
cd local-ai
nvidia-smi
nvidia-ctk cdi list
# 查看配置及验证状态
./local-ai profiles
```

`nvidia-ctk cdi list` 必须列出所选 GPU 的 `nvidia.com/gpu=GPU-...` UUID 别名；显示 0 个设备时不要继续。CDI 缺失时，在目标机器重新生成，不能复制其他机器的设备定义：
```bash
sudo systemctl restart nvidia-cdi-refresh.service
nvidia-ctk cdi list
```
刷新后再次确认 UUID 别名。若没有自动刷新服务，参考 NVIDIA 官方 CDI 手动生成流程；不要创建重复定义。

### 下载前检查 Docker 存储

先在 GPU 节点执行：

```bash
docker version
docker info --format 'Server={{.ServerVersion}} Driver={{.Driver}} Root={{.DockerRootDir}}'
docker ps -a
```

必须能访问 Docker 服务端。`systemctl status docker` 显示 active 只代表进程运行，
不能证明镜像解包和存储正常。首次 `image inspect` 返回 `No such image` 属正常情况，
程序会继续拉取；应根据随后 `docker pull` 的具体错误判断失败原因。

`--data-dir` 只控制项目权重、锁文件和运行数据，不修改 Docker/containerd 的存储路径。
Docker 29 使用 containerd 镜像存储时，两者可能分别使用 `/var/lib/docker` 和
`/var/lib/containerd`；以实际配置为准。不要在服务运行时删除、移动这些目录，
也不要把多节点的 Docker/containerd 数据库放在同一共享目录。

### 故障恢复：镜像解包提示 metadata.db 不存在

若 `image pull` 报以下错误，先停止安装，检查 Docker/containerd 存储：

```text
failed to prepare extraction snapshot
/var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/metadata.db: no such file or directory
```

已验证的一种原因是：服务运行时存储目录被删除，旧进程仍持有已删除的数据库句柄。
Docker 的 active 状态不能排除该问题。仅重启 Docker 不会重启独立的 containerd。
先由管理员核对配置、挂载点和原数据；如有需保留的数据，应先恢复存储，不要用空目录替代。

重启前检查 Docker 容器和 containerd 的所有命名空间、任务：

```bash
docker ps -a
sudo ctr namespaces list
for ns in $(sudo ctr namespaces list -q); do
    sudo ctr --namespace "$ns" tasks list
    sudo ctr --namespace "$ns" containers list
done
```

有运行任务时先安排维护窗口；空列表也不能替代管理员对共享运行时用途的确认。
确认可以中断服务、原存储无需恢复后，在目标 GPU 节点执行；root 可省略 sudo：

```bash
sudo systemctl stop docker.service docker.socket
sudo systemctl restart containerd.service
sudo systemctl start docker.socket docker.service
docker info
```

然后重试原来的 `image pull`，成功后再下载模型。不要反复重启或删除数据库；
仍失败时检查安装日志中的具体错误，以及 `journalctl -u containerd -u docker`。

`metadata.db` 可在首次创建快照时才生成；重启后立即 `ls` 找不到它不代表恢复失败。
只读快照列表也不一定创建该文件。以实际镜像拉取和解包成功作为验收，不要手工
`touch metadata.db`。上述步骤不会恢复已丢失的镜像、容器或卷数据，也不是正常安装必做项。

镜像和模型完整时，下方准备命令会直接复用。安装判断、命令和错误集中记录在 `/raid/local-ai/install.log`；详细规则见[使用手册](commands.md)。

下载固定镜像和完整模型：
```bash
# 下载推理容器镜像
./local-ai image pull --profile b300-tp4 --data-dir /raid/local-ai
# 下载完整模型权重
./local-ai model download --profile b300-tp4 --data-dir /raid/local-ai
```
若已有完整模型，复制到 /raid/local-ai/models/DeepSeek-V4.1-Flash/ 即可。
同一份权重可用于 AMD64/ARM64，但容器镜像不能混用架构。

## 3. 启动与验收

在 GPU 服务器执行：
```bash
# 预览计划，不启动服务
./local-ai server plan --host 0.0.0.0 --profile b300-tp4 --gpus 0,1,2,3 --name a --port 18000 --data-dir /raid/local-ai
# 启动实例，首次加载需等待
./local-ai server start --host 0.0.0.0 --profile b300-tp4 --gpus 0,1,2,3 --name a --port 18000 --data-dir /raid/local-ai
./local-ai server status --name a
curl --fail http://127.0.0.1:18000/v1/models
./local-ai server status --name a
```

在 GPU001 上用 `server status --name a` 查看明确的“已就绪 / 尚未就绪”结果。`server start` 默认等待最多 600 秒，API 就绪时同时在终端和实例 `server.log` 写入 READY 标记；超时或容器退出会明确报错。

GB300 四卡替换为 --profile gb300-tp4。
GB300 两卡替换为 --profile gb300-tp2 --gpus 0,1。
所有示例的 GPU 编号均指所在服务主机；也可传完整 GPU UUID 列表。
启动器将其解析为 UUID，并严格限定容器可见设备。

`profiles` 列出配置及验证状态。`plan` 检查本机硬件并打印计划，不启动容器；`start` 检查实时占用并启动。
`status --name a` 查询实例 a；`stop --name a` 停止该实例。
首次加载/编译可能持续数分钟，容器 running 不能替代 API 验收。
完整日志在数据目录 instances/a/server.log，启动命令和参数也保存在该目录。

正常安装以 start 的“服务已就绪（READY）”及退出码 0 为准，不必额外运行 curl。
未就绪时会显示原因；需要更长冷启动等待，可在 start 中加 --wait-timeout 1200。
超时或 Ctrl+C 不会停止容器，之后用 status 查询，或以相同参数重新 start 继续等待。
详细结果、退出码和日志含义见 [README](../README.md) 的“如何判断服务是否准备好”。

### API 监听地址

server plan/start 接受 --host，默认 127.0.0.1。使用 --host 0.0.0.0 或本机 IPv4 地址后，
BCM 可通过 --endpoint http://GPU001:18000/v1 直连。现有容器改地址须显式重建。
完整命令和访问范围说明见 [README](../README.md) 的“监听地址与已有实例”。

## 4. BCM 安装客户端

在 BCM 以实际执行工具的用户安装：

```bash
git clone https://github.com/junli-nv/local-ai.git
cd local-ai
./local-ai client install
```

需要 Python3、Bash、git、rg 和 script，不需要 BCM 安装 Docker、CUDA、Node.js 或 npm。
在线安装核对固定版本与完整性；离线时导入预先准备的原生程序。
SSH 仅是访问其他节点的可选工具，不是模型连接的前提。

## 5. 从 BCM 开始使用

确认 GPU API 已就绪且 BCM 可以访问。将 GPU001 换为可达 IP 或主机名，端口写在
--endpoint URL 中；--project 指 BCM 已有项目目录，默认当前目录：

```bash
./local-ai chat --endpoint http://GPU001:18000/v1 --project /home/alice/project
./local-ai chat --endpoint http://GPU001:18000/v1 --check
./local-ai chat --endpoint http://GPU001:18001/v1 --project /home/alice/project
./local-ai chat --endpoint http://GPU001:18000/v1 --run '请用 bash 执行 hostname 并报告实际输出。'
```

客户端只连接 HTTP(S) API，不管理网络转发。跨网转发或 nginx/frp 等代理由管理员单独配置，
客户端填写最终可达地址。工具在 BCM 以当前用户权限执行，推理在 GPU 服务器进行。
接口和实例重建步骤见 [README](../README.md)。

## 6. 多人和双实例

在八卡 B300 的 GPU 服务器上：
```bash
./local-ai server start --host 0.0.0.0 --profile b300-tp4 --name a --gpus 0,1,2,3 --port 18000 --data-dir /raid/local-ai
./local-ai server start --host 0.0.0.0 --profile b300-tp4 --name b --gpus 4,5,6,7 --port 18001 --data-dir /raid/local-ai
```

每套拥有独立 GPU、显存、KV、缓存、端口和日志，共享只读模型文件。
用户在 BCM 通过 --endpoint URL 的 18000 或 18001 端口选择实例；当前没有自动负载均衡。

每人使用自己的 Linux 账户。默认私有目录：
```
~/.local/state/local-ai/
  clients/ARCH/
  services/SERVICE_ID/
    cache/
    data/
    state/
    logs/session-.../
```
历史按 API endpoint 保存。每次连接配置独立。
同一 Linux 账户的不同目录不构成用户权限隔离，root 仍能访问用户文件。

每引擎默认四个活动序列，更多请求排队，不是只能有四名用户。
单用户生成速度不能乘以用户数来预测总吞吐；并发性能另测。

## 7. 停止与改配置

在 GPU 服务器：
```bash
./local-ai server stop --name b --data-dir /raid/local-ai
./local-ai server start --host 0.0.0.0 --profile b300-tp4 --name b --gpus 4,5,6,7 --port 18001 --data-dir /raid/local-ai
```

不同配置不会静默覆盖同名实例。需要改 GPU、端口或模板时，先检查、停止并
显式删除对应容器，再重建；模型和实例日志不随容器删除。
本项目不会自动开机启动服务；设备使用权由操作者管理。

## 8. 离线与开发资料

离线时携带三个独立部分：源码、服务端平台匹配的镜像/权重、BCM 平台匹配的
客户端资源。步骤见 [离线文档](offline.md)。
不需要互联网推理，但网页搜索、外部 MCP、在线下载依赖会不可用。
离线推理仍须保持 BCM 到 GPU API 的内网连接。

代码如何划分、为何这么设计：见 [架构](architecture.md)。
如何新增平台、改模型、运行测试和提交代码：见 [开发指南](development.md)。
已验证内容和未验证范围：见 [验证记录](validation.md)。

---

[English version](en/deployment.md)
