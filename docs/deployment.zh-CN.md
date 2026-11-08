# 部署与运行维护

首次在线安装按 [README](../README.md) 顺序完成；本页只展开部署分支和故障处理，不重复软件下载、客户端安装和聊天主流程。离线准备与迁移见[离线部署](offline.md)，参数和默认值见[命令手册](commands.md)。

沿用 README：GPU001、bcm-headnode、alice、安装根 /raid/local-ai、实例 a、端口 18000。以下 local-ai 命令在 GPU001 的 /raid/local-ai 执行；标明 BCM 的命令才在 BCM 执行。本页不设置数据目录覆盖。

已有安装只更新程序时，使用[更新指南](update.md)，保留运行实例和资源，无需准备镜像/模型；改变推理配方仍按下文显式重建实例。

## CDI 配置

首次部署的检查、刷新/手动生成命令及 UUID 验收标准，统一放在 [README：配置 GPU 的 CDI 设备定义](../README.md#配置-gpu-的-cdi-设备定义首次部署必查)，排在模型安装和服务启动之前。请在目标 GPU 主机按该步骤执行，不能复制其他机器的定义。

若别名缺失或重复，检查 /etc/cdi 和 /var/run/cdi，解决定义冲突后再继续。驱动、GPU 或 MIG 配置变化后重新生成手动定义；已有完整别名无需重复生成。

## Docker 存储故障

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

### metadata.db 不存在

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

然后回到 README 重试安装；原命令是 image pull 时先单独重试镜像拉取。不要反复重启或删除数据库；
仍失败时检查安装日志中的具体错误，以及 `journalctl -u containerd -u docker`。

`metadata.db` 可在首次创建快照时才生成；重启后立即 `ls` 找不到它不代表恢复失败。
只读快照列表也不一定创建该文件。以实际镜像拉取和解包成功作为验收，不要手工
`touch metadata.db`。上述步骤不会恢复已丢失的镜像、容器或卷数据，也不是正常安装必做项。

## 监听与网络

server plan/start 的 --host 默认为 127.0.0.1。README 显式使用 --host 0.0.0.0，BCM 通过 http://GPU001:18000/v1 访问；也可绑定本机具体 IPv4 地址。0.0.0.0 不是客户端地址，不接受主机名或 IPv6 作为 --host。

绑定 0.0.0.0 时健康探测使用 127.0.0.1；具体 IP 则探测该 IP。配置防火墙和路由，使 BCM 可达 API；现有实例修改监听地址需重建。当前未配置 API key/HTTPS，应限制可信客户端访问。

跨网络转发由管理员单独配置 nginx、frp 等，endpoint 填最终可达地址。模型连接不要求 SSH；日常工具仍可用 SSH 运维其他节点。若代理环境影响内网访问，将 GPU001 或实际 IP 加入 NO_PROXY/no_proxy。

同一 BCM 客户端也可通过 chat --endpoint URL 选择其他 GPU 主机的服务，与下文同一主机双实例是不同场景。可选默认地址、模型选择与会话隔离见[多节点使用](../README.md#从同一个-bcm-连接多个服务)。

## 实例重建

修改 GPU、端口、监听地址或配方时，先确认实例 a 正是要替换的服务，记录新旧参数。停止后显式删除对应容器，再用新参数启动；仅 restart 原容器不会更改参数。

以下以重建相同参数的实例 a 为例，实际变更时同时调整 plan/start：

```bash
cd /raid/local-ai
./local-ai server status --name a
./local-ai server stop --name a
docker rm local-ai-a
./local-ai server plan --profile b300-tp4 --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000
./local-ai server start --profile b300-tp4 --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000
```

权重与宿主机实例日志保留。程序不会静默覆盖配置不同的同名容器。尚未就绪时的查询、超时和日志含义见 [README](../README.md#1-在-gpu001-安装并启动)；完整退出码见命令手册。

启动预检允许已停止 HTTP 服务的 TCP TIME_WAIT 连接复用，但仍拒绝实际监听进程占用的端口。其他程序占用时应更换端口或由操作者明确处理。

## B200 四卡（实验性）

`b200-tp4-cpu` 将 Engram 表放到主机内存；`b200-tp4` 保留 GPU Engram。
两者要求 AMD64、四张 B200、每卡至少 180000 MiB HBM；CPU 配方另检查
MemAvailable 至少 256 GiB。这些值是保守配置保护值，不是实测最低需求。
模型 revision、AMD64 镜像摘要及其他引擎参数沿用 B300 基线：
131072 上下文、四个活动序列、8192 批处理 token、0.80 显存预算，不启用 DSpark。
两套配方已在验证记录所列环境通过四卡 API 冒烟；完整上下文边界与长期负载未验收。
已发布的 v1.3.0 源码包不含新增配方；先取得包含本变更的源码并检查 ./local-ai profiles。
CPU 卸载释放的模型显存会被 vLLM 用作 KV cache，nvidia-smi 总占用不一定下降。
API READY 也不表示所有形状已预热；首次请求仍可能出现 JIT 延迟。

在 GPU001 执行，先按 README 核对 Docker、所选 GPU 的 CDI UUID 和空闲状态。
以下使用通用编号 0–3；部署时按本机拓扑选择已分配的健康 GPU，优先同一 NUMA 节点，
编号不是配方的一部分。CPU 内存位置还需单独核对，不能仅靠选卡保证 NUMA 局部性。

```bash
cd /raid/local-ai
./local-ai install --role server --profile b200-tp4-cpu
./local-ai server plan --profile b200-tp4-cpu --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000
./local-ai server start --profile b200-tp4-cpu --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000
./local-ai server status --name a
```

比较 GPU Engram 时保持同样的设备、上下文、并发和请求，显式重建实例并改选
`b200-tp4`，不要同时在这四张卡上启动两套服务。分别测量首 token 延迟、
生成速度、显存与主存；CPU 配方的容量优势不等于性能已经验证。
外部 LOCAL_AI_CATALOG 或 config/catalog.json 完整替代内置配方，需要手动合并新配置。

## 单用户 DSpark 与显式预热

默认 b300-tp4 保留原参数；可选 b300-tp4-dspark 偏向单用户生成速度，并发吞吐可能下降。DSpark 通过草稿和目标模型校验的投机解码提高生成阶段速度，不保证 TTFT 下降。两者使用相同镜像和权重，无需另下模型。测量方法和适用范围见[验证记录](validation.md)。GB300 未验证，不直接套用此配方。

以下在 GPU001 的 /raid/local-ai 执行，要求所选 GPU 和端口空闲。已有实例 a 时，先按[实例重建](#实例重建)确认并停止、移除对应容器，再更换配方。

```bash
./local-ai server plan --profile b300-tp4-dspark --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000
./local-ai server start --profile b300-tp4-dspark --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000 --wait-timeout 1200 --warmup --warmup-timeout 600
./local-ai server status --name a
```

--wait-timeout 只控制 API 启动等待；API 健康后 --warmup 才发送真实生成请求，另受 --warmup-timeout 控制。普通 start 默认不生成请求。READY 表示 API 可用，WARMUP COMPLETE 才表示本次显式预热完成。

已有运行中且健康的实例也可单独预热，无需重新安装或重启，原配方同样适用：

```bash
./local-ai server warmup --name a
./local-ai server status --name a
```

预热会占用 GPU 并与业务请求竞争，建议在正式接入前执行。默认覆盖上下文允许的 1024、8192、32768 个输入 token，256 个输出 token，并发 1、2、4、8，每组两遍；本配方共 90 个请求。超过四个活动序列的请求会排队。每个请求使用不同前缀，避免把前缀缓存命中当作编译完成。有限请求不能保证所有后续长度、批次都不再触发 JIT。

可根据实际负载调整范围，例如：

```bash
./local-ai server warmup --name a --input-tokens 1024,8192 --concurrency 1,4 --output-tokens 256 --repeats 2 --timeout 600
```

install.log 和 instances/a/server.log 显示 WARMING、进度及 WARMUP COMPLETE，失败显示 WARMUP INCOMPLETE。instances/a/warmup.json 保存输入范围、耗时和完成数量；status 只读取记录，不触发生成。只有记录匹配当前配置与容器启动时间时才显示 completed=true；重启后为 stale，需重新显式预热。超时或失败退出 1，Ctrl+C 返回 130，均保留容器；API 仍可能健康，应分别查看 ready 与 warmup 字段。

DSpark 配方将 TileLang 与 CUDA 编译缓存放到持久化的 instances/a/cache 下，便于同一实例后续启动复用。不同引擎版本、GPU 架构或参数可能需要重新编译；这不能消除权重加载及所有首次编译。导出不携带实例缓存，迁移后在目标 GPU 重新预热。

若设置了 LOCAL_AI_CATALOG 或安装目录 config/catalog.json，外部目录是完整替代，不自动追加新内置配方；先按[开发指南](development.md#模型与客户端兼容性)合并配置并验收。

## 双实例与多人使用

只有本节引入第二个服务：八卡 B300 上 a 使用 0–3 卡和 18000，b 使用 4–7 卡和 18001。先确认另外四卡和端口可用，再在 GPU001 执行：

```bash
cd /raid/local-ai
./local-ai server start --profile b300-tp4 --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000
./local-ai server start --profile b300-tp4 --host 0.0.0.0 --gpus 4,5,6,7 --name b --port 18001
```

两套服务只共享只读模型；GPU、显存、KV、端口、缓存和日志独立。BCM 临时选择第二实例：

```bash
cd /raid/local-ai
./local-ai chat --endpoint http://GPU001:18001/v1 --check
./local-ai chat --endpoint http://GPU001:18001/v1 --project /home/alice/project
```

未带 --endpoint 的 chat 仍用安装时保存的 18000 地址。若要保存新的默认地址，用 config set endpoint URL；无需安装操作。不同 endpoint 分别保存历史，切换端口不会自动迁移会话。

每人使用自己的 Linux 账户和私有状态，默认 ~/.local/state/local-ai/。共享程序不等于共享历史；同一账户下的不同目录不是权限隔离，管理员仍可访问用户文件。备份状态前退出客户端。

每引擎四个活动序列是调度上限，不是四个用户上限；更多请求排队。当前不提供自动负载均衡、配额、开机自启或跨主机 TP；并发性能须单独测量。平台验收以[验证记录](validation.md)为准。

---

[English version](en/deployment.md)
