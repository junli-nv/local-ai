# 部署与运行维护

首次在线安装按 [README](../README.md) 顺序完成；本页只展开部署分支和故障处理，不重复软件下载、客户端安装和聊天主流程。离线准备与迁移见[离线部署](offline.md)，参数和默认值见[命令手册](commands.md)。

沿用 README：GPU001、bcm-headnode、alice、安装根 /raid/local-ai、实例 a、端口 18000。以下 local-ai 命令在 GPU001 的 /raid/local-ai 执行；标明 BCM 的命令才在 BCM 执行。本页不设置数据目录覆盖。

## CDI 配置

nvidia-ctk cdi list 必须列出所选 GPU 的 nvidia.com/gpu=GPU-... UUID 别名。定义应在目标机器生成，不复制其他机器的定义。

系统有自动刷新服务时：

```bash
sudo systemctl restart nvidia-cdi-refresh.service
nvidia-ctk cdi list
```

若没有自动刷新服务，管理员先检查 /etc/cdi 和 /var/run/cdi，确认没有其他有效 NVIDIA 定义或冲突后，生成本机 UUID 定义：

```bash
sudo install -d /etc/cdi
sudo nvidia-ctk cdi generate --device-name-strategy uuid --output=/etc/cdi/nvidia.yaml
nvidia-ctk cdi list
```

手动定义在驱动、GPU 或 MIG 配置改变后需重新生成。不要同时保留重复定义；若所选 UUID 仍缺失，停止启动并排查。镜像平台和 BCM 架构分别选择，GB300 验证限制见 README。

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

未带 --endpoint 的 chat 仍用安装时保存的 18000 地址。若要保存新的默认地址，重新执行 install --role client --endpoint URL。不同 endpoint 分别保存历史，切换端口不会自动迁移会话。

每人使用自己的 Linux 账户和私有状态，默认 ~/.local/state/local-ai/。共享程序不等于共享历史；同一账户下的不同目录不是权限隔离，管理员仍可访问用户文件。备份状态前退出客户端。

每引擎四个活动序列是调度上限，不是四个用户上限；更多请求排队。当前不提供自动负载均衡、配额、开机自启或跨主机 TP；并发性能须单独测量。平台验收以[验证记录](validation.md)为准。

---

[English version](en/deployment.md)
