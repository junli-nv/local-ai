# 中文部署指南

默认拓扑：**GPU 服务器只运行推理服务；BCM 头节点运行 OpenCode 和工具。**
源码可复制到两端，但模型、镜像和用户会话不放进 GitHub。

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

前提：驱动、Docker、NVIDIA Container Toolkit 已安装且兼容。
Python3 至少 3.10，Docker API 至少 1.49。数据目录示例 /raid/local-ai，源码目录与数据目录分开。
先由管理员/调度器分配 GPU；本工具不会修改 Slurm 或停止其他作业。

在 GPU 服务器运行：
```bash
git clone https://github.com/junli-nv/local-ai.git
cd local-ai
nvidia-smi
nvidia-ctk cdi list
./local-ai profiles
```

CDI 缺失时，在目标机器重新生成，不能复制其他机器的设备定义：
```bash
sudo systemctl restart nvidia-cdi-refresh.service
nvidia-ctk cdi list
```
若没有自动刷新服务，参考 NVIDIA 官方 CDI 手动生成流程；不要创建重复定义。

下载固定镜像和完整模型：
```bash
./local-ai image pull --profile b300-tp4 --data-dir /raid/local-ai
./local-ai model download --profile b300-tp4 --data-dir /raid/local-ai
```
若已有完整模型，复制到 /raid/local-ai/models/DeepSeek-V4.1-Flash/ 即可。
同一份权重可用于 AMD64/ARM64，但容器镜像不能混用架构。

## 3. 启动与验收

在 GPU 服务器执行：
```bash
./local-ai server plan --profile b300-tp4 --gpus 0,1,2,3 --name a --port 18000
./local-ai server start --profile b300-tp4 --gpus 0,1,2,3 --name a --port 18000
curl --fail http://127.0.0.1:18000/health
curl --fail http://127.0.0.1:18000/v1/models
./local-ai server status --name a
```

GB300 四卡替换为 --profile gb300-tp4。
GB300 两卡替换为 --profile gb300-tp2 --gpus 0,1。
所有示例的 GPU 编号均指所在服务主机；也可传完整 GPU UUID 列表。
启动器将其解析为 UUID，并严格限定容器可见设备。

plan 不分配 GPU；start 才检查实时占用并启动。
首次加载/编译可能持续数分钟，容器 running 不能替代 API 验收。
完整日志在数据目录 instances/a/server.log，启动命令和参数也保存在该目录。

## 4. BCM 安装客户端

在 BCM 头节点，以实际操作用户执行：
```bash
git clone https://github.com/junli-nv/local-ai.git
cd local-ai
./local-ai client install
./local-ai client doctor
ssh gpu-a hostname
```

把 gpu-a 换为 GPU 服务器名。先完成正常 SSH 登录、主机密钥确认和密钥/agent
认证。程序不关闭主机密钥检查，不修改 SSH 配置，也不分发 root 密钥。

客户端只装在当前用户的私有目录，不需要 BCM 安装 Docker、CUDA、Node.js
或 npm。在线安装会下载固定版本原生程序并核对 NPM 完整性。
BCM 需要 Python3、Bash、git、ssh、rg 和 script；离线时提前准备这些工具。

## 5. 从 BCM 开始使用

```bash
./local-ai chat --server gpu-a --project /home/alice/project
```

程序自动建立本机 loopback SSH 隧道，确认 API 后启动本地 OpenCode，
退出时关闭隧道。无需另外手工运行 ssh -L。

检查连接但不调用模型：
```bash
./local-ai chat --server gpu-a --check
```
指定登录身份、服务端口：
```bash
./local-ai chat --server alice@gpu-a --port 18001 --project /home/alice/project
```
非交互单次任务：
```bash
./local-ai chat --server gpu-a --project /home/alice/project \
  --run '请用bash执行hostname，并报告实际输出。'
```

此时 hostname、文件编辑、git 和 SSH 都发生在 BCM，推理发生在 GPU 容器。
如需访问其他节点，使用 BCM 当前用户已有的 SSH 权限。
客户端看不到本地 GPU 属于正常现象，不代表模型在 CPU 上运行。

## 6. 多人和双实例

在八卡 B300 的 GPU 服务器上：
```bash
./local-ai server start --profile b300-tp4 --name a --gpus 0,1,2,3 --port 18000
./local-ai server start --profile b300-tp4 --name b --gpus 4,5,6,7 --port 18001
```

每套拥有独立 GPU、显存、KV、缓存、端口和日志，共享只读模型文件。
用户在 BCM 选择 chat --port 18000 或 18001；当前没有自动负载均衡。

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
历史按逻辑服务保存，不随临时隧道端口变化。每次连接配置独立。
同一 Linux 账户的不同目录不构成用户权限隔离，root 仍能访问用户文件。

每引擎默认四个活动序列，更多请求排队，不是只能有四名用户。
单用户生成速度不能乘以用户数来预测总吞吐；并发性能另测。

## 7. 停止与改配置

在 GPU 服务器：
```bash
./local-ai server stop --name b
./local-ai server start --profile b300-tp4 --name b --gpus 4,5,6,7 --port 18001
```

不同配置不会静默覆盖同名实例。需要改 GPU、端口或模板时，先检查、停止并
显式删除对应容器，再重建；模型和实例日志不随容器删除。
本项目不会自动开机启动服务，也不会自动把空闲 GPU 交回 Slurm。

## 8. 离线与开发资料

离线时携带三个独立部分：源码、服务端平台匹配的镜像/权重、BCM 平台匹配的
客户端资源。步骤见 [离线文档](offline.md)。
不需要互联网推理，但网页搜索、外部 MCP、在线下载依赖会不可用。
内部 SSH 网络可以保留。

代码如何划分、为何这么设计：见 [架构](architecture.md)。
如何新增平台、改模型、运行测试和提交代码：见 [开发指南](development.md)。
已验证内容和未验证范围：见 [验证记录](validation.md)。

---

[English version](en/deployment.md)
