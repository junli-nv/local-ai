# 使用手册与命令参考

## 从哪里开始

第一次部署先看[部署指南](deployment.zh-CN.md)；本页用于查命令、参数和运行维护。所有命令在源码目录中运行。

| 示例对象 | 含义 |
|---|---|
| `GPU001` | GPU 服务节点，负责容器和模型 |
| `bcm-headnode` | BCM 头节点，负责 OpenCode 和本地工具 |
| `alice`、`/home/alice/project` | BCM 登录用户及已存在的项目目录，按实际环境替换 |
| `a`、`18000` | GPU001 上的实例名和模型 API 端口，与主机名区分，端口用于 API |

先查询帮助，无需启动模型：

```bash
./local-ai --help
./local-ai server --help
./local-ai server start --help --data-dir /raid/local-ai
./local-ai chat --help
```

通用格式为 `./local-ai 命令组 子命令 参数`；profiles 和 chat 没有下级子命令。
每一级都支持 `--help`。全局 `--debug` 必须放在命令组之前，用于错误时显示 Python 调用栈。

## 全部命令

| 命令 | 执行位置 | 作用与结果 |
|---|---|---|
| `profiles` | 任意一端 | 输出配置目录和验证状态，JSON 格式 |
| `server inventory` | GPU001 | 读取本机 CPU 架构及 GPU 型号、UUID、显存 |
| `server plan` | GPU001 | 输出 GPU 选择、引擎参数及 Docker 启动命令；不创建容器 |
| `server start` | GPU001 | 检查资源、启动并等待 API；成功表示已就绪，返回状态与日志位置 |
| `server status` | GPU001 | 明确显示已就绪或尚未就绪；返回原因、监听状态和日志位置 |
| `server stop` | GPU001 | 停止指定实例，保留权重和宿主机日志 |
| `image pull` | 联网 GPU 准备机 | 拉取固定镜像并记录平台身份 |
| `image export` | Docker 准备机 | 导出镜像归档及配套锁文件 |
| `image import` | 离线 GPU 节点 | 校验归档与锁文件后导入镜像 |
| `model download` | 联网准备机 | 下载固定模型配置、分词器、索引和全部权重分片 |
| `client install` | bcm-headnode | 安装固定版本原生客户端，或导入本地程序 |
| `client export` | BCM 准备机 | 打包客户端与公共缓存，不包含个人历史和凭据 |
| `chat` | bcm-headnode | 连接推理服务，在本机以当前用户权限执行工具 |

server 通过 Docker 运行 vLLM；plan 的 JSON 中 `command` 字段就是将使用的 Docker 参数。
chat 连接指定 API 并启动本机 OpenCode；不是登录容器后再执行你的工具命令。

引擎参数不做任意透传；模型和 vLLM 参数在 profiles.json/profiles.py 中维护。启动后实例目录保存 spec.json、args.json、docker-command.json 和 launch.log，便于核对实际配置。

## 本地复用与安装日志

准备命令默认先检查本地：镜像的平台及固定摘要匹配，就不访问仓库；模型配置、分词器、
索引和所有分片完整，就不联网下载。模型检查包含 safetensors 长度与偏移检查，不等同于逐文件 SHA256。
带有 model.lock.json 时核对仓库和 revision；缺锁则明确返回 revision_verified=false，不伪造已验证状态；
锁文件版本冲突或权重截断直接报错。完整性哈希验收使用离线材料的 MODELS.sha256。

`image pull --force` 显式联系镜像仓库；`model download --force` 从固定 revision 强制重新下载，
可能重新传输完整权重。普通重复执行不需要加它。

安装与部署命令追加到一个日志：GPU 端默认 `数据目录/install.log`，
BCM 客户端默认 `客户端目录/install.log`。每次操作有独立 ID，记录时间、主机、版本、参数、
真实命令、实时输出、耗时、退出码、完整异常；长命令每 15 秒报告存活和输出字节数。
标准输出仍保留 JSON，进度提示写到标准错误。只读查询与 plan 不创建日志。

本地镜像不存在属于正常探测结果，随后自动拉取；Docker 服务、权限或存储检查错误直接报告。失败命令的错误摘要显示在终端标准错误，长输出保留末五行并缩短单行；完整输出仍在安装日志中。镜像拉取失败还会在最终异常中保留 Docker 的错误正文。

需要固定日志位置时，将全局参数放在命令组之前：

```bash
./local-ai --install-log /raid/local-ai/install.log image pull --profile b300-tp4
```

两端若可写同一个共享目录，可指定相同 `--install-log` 路径，集中到同一个安装日志。
模型加载后的持续运行日志仍在 instances/实例名/server.log；聊天历史和会话日志独立保留，
不会混进安装记录。

## 服务端参数

| 参数 | 适用命令 | 含义与默认值 |
|---|---|---|
| `--data-dir` | server 的 plan/start/status/stop；image；model download | 运行数据根目录；先取 LOCAL_AI_DATA_DIR，未设置则 /raid/local-ai。status 实际按实例名查询。 |
| `--profile` | plan/start、image、model download | 硬件与引擎配置。image 必填；其余默认 b300-tp4。 |
| `--gpus` | plan/start | 必填，逗号分隔的本机 GPU 编号或完整 UUID；数量匹配配置 |
| `--name` | plan/start/status/stop | 实例名，默认 a；须以小写字母开头，仅含小写字母、数字和连字符，最长 32 字符 |
| `--host` | plan/start | IPv4 监听地址，默认 127.0.0.1；0.0.0.0 监听所有 IPv4 网卡，也可指定本机 IP；不接受主机名或 IPv6 |
| `--port` | plan/start | 模型 API 端口，默认 18000，允许 1024–65535 |
| `--wait-timeout` | 仅 start | 等待 API 就绪的秒数，默认 600，须大于 0；超时退出 1，保留容器 |
| `--inventory` | 仅 plan | 从 JSON 测试清单生成计划，代替实时硬件发现；start 不接受 |
| `--output` | image export | 必填，导出镜像的归档路径 |
| `--archive`、`--lock` | image import | 均必填，镜像归档及其配套 .lock.json 路径 |

TP 表示张量并行：b300-tp4 在同一主机上使用 4 张 B300；GB300 配置及验证限制见[部署指南](deployment.zh-CN.md)。
数据目录与源码目录独立；不同命令不会继承前一次的参数。下载、计划、启动和停止须使用同一数据根目录。

例如在 GPU001 上预览、启动和查询：

```bash
./local-ai server plan --host 0.0.0.0 --profile b300-tp4 --gpus 0,1,2,3 --name a --port 18000 --data-dir /raid/local-ai
./local-ai server start --host 0.0.0.0 --profile b300-tp4 --gpus 0,1,2,3 --name a --port 18000 --data-dir /raid/local-ai
./local-ai server status --name a
```

plan 不预留 GPU，也不检查当前端口/GPU 进程占用；start 才检查实时占用。
start 默认等待 API 就绪，最多 600 秒，成功退出 0 表示检查时已就绪；可用 --wait-timeout 调整。
等待期间直接提示“服务尚未就绪（NOT READY）”，日志持续显示加载、编译和预热。
status 立即检查，已就绪退出 0，尚未就绪或检查失败退出 1；查询只读，不写日志。

监听地址影响引擎参数、实例身份和启动前端口检查；plan 不探测地址是否属于本机。
默认回环实例保持兼容；已有实例更改 --host 须显式停止、移除容器并重建。
绑定 0.0.0.0 时健康地址使用 127.0.0.1；绑定具体 IP 时使用该 IP。
管理中的实例仍保守地独占同一 API 端口，不支持按不同网卡复用端口。
客户端仅连接 --endpoint 指定的 API。需要转发时由管理员配置 nginx/frp 等外部工具。
当前不配置 API key/HTTPS，应限制可信网络访问。完整操作见 [README](../README.md)。

启动开始时直接显示运行日志、tail -f 和 status 查询命令。API 健康成功后，终端和实例
server.log 都会出现带时间戳的“服务已就绪（READY）”。端口开放本身不是就绪条件；
容器停止或 HTTP 503 均为未就绪。首次编译可能耗时数分钟，旧 READY 日志只代表当时状态。

等待超时返回 1，并明确写入 NOT READY 和原因；容器不会停止。容器退出会写入 FAILED；
Ctrl+C 中断等待返回 130，也不会停止容器。中断后用 status 查询，或用相同参数重新执行
start 继续等待并记录 READY；匹配的运行中实例不会重启。
status 的人类可读提示写标准错误，标准输出保留 ready/listening/health/log 等 JSON 字段。
当前状态不从日志推断，以实际容器和 API 检查为准。

## 客户端参数

client install/export 均接受 `--client-dir`，默认是用户状态根目录下的 `clients/本机架构/`。
状态根目录默认 `~/.local/state/local-ai`；设置 XDG_STATE_HOME 时则为 `$XDG_STATE_HOME/local-ai`。

| 参数 | 适用命令 | 含义与默认值 |
|---|---|---|
| `--binary` | client install | 导入本地 OpenCode 程序；省略则在线下载 |
| `--seed-cache` | client install | 导入离线公共缓存目录；可选 |
| `--version` | client install | 下载或校验的 OpenCode 版本，默认 1.19.5 |
| `--sha256` | client install | 本地导入程序的预期 SHA256；可选，来自可信材料清单 |
| `--output` | client export | 必填，客户端归档输出路径；同时生成 .sha256 |

离线归档的路径关系和导入步骤见[离线部署](offline.md)。CPU 架构按 BCM 本机选择，与 GPU 服务端独立。

## chat 参数

| 参数 | 含义与默认值 |
|---|---|
| `--endpoint URL` | 必填，可访问的 HTTP(S) 模型 API 基础地址，包含端口与 /v1 |
| `--project` | BCM 上已存在的工作目录，默认当前目录 |
| `--client-dir` | 原生客户端目录，须与安装位置一致 |
| `--state-dir` | 私有历史、缓存和会话日志根目录，默认见上节 |
| `--model` | API 中的服务模型 ID，默认读取 profiles.json 的 served_name |
| `--check` | 只检查连接和模型可用性，输出 ready 与日志位置后退出 |
| `--run '任务'` | 单次任务，流式输出 JSON 事件并保存完整日志后退出；不加则交互使用 |

在 bcm-headnode 上以 alice 执行：

```bash
# 可选：只检查 API 连接和模型就绪
./local-ai chat --endpoint http://GPU001:18000/v1 --check

# 进入 BCM 本地项目，开始交互会话
./local-ai chat --endpoint http://GPU001:18000/v1 --project /home/alice/project

# 只执行一个任务；工具仍在 bcm-headnode 执行
./local-ai chat --endpoint http://GPU001:18000/v1 --project /home/alice/project --run '请执行 hostname 并报告结果。'
```

升级模型或镜像时，使用独立的数据目录和实例进行验收，保留旧源码、权重和镜像锁。不要在原生产数据目录中强制覆盖权重后再尝试回退。

## 运行维护与排障

| 现象 / 操作 | 检查方法 |
|---|---|
| 镜像解包提示 metadata.db 不存在 | 按[部署指南](deployment.zh-CN.md)检查 Docker/containerd 存储；确认任务影响后恢复服务，不能仅重启 Docker 或根据数据库文件是否立即出现判断恢复。 |
| GPU 服务未就绪 | 在 GPU001 查询 server status，查看提示原因和 instances/a/server.log；必要时增加 start 的 --wait-timeout |
| BCM 无法连接 | 用 chat --endpoint http://GPU001:18000/v1 --check 检查 API；核对服务就绪、DNS、路由、防火墙和代理设置 |
| 客户端看不到 GPU | 工具在 BCM 执行属预期行为；在 GPU001 用 nvidia-smi 检查推理进程 |
| GPU/端口冲突 | 核对分配与现有作业，选空闲设备/端口；不要停止无关任务 |
| 更换 GPU、端口或配置 | 先检查并停止实例，显式移除对应容器，再按新配置重建 |
| 退出聊天 | 本机客户端退出；GPU 推理服务继续运行 |
| 更新或回退 | 固定并记录 Git 提交、镜像摘要和模型 revision；在独立实例验收后再切换客户端。失败时切回已验证实例/版本。 |

停止与重建示例，在 GPU001 执行；先确认实例 a 正是要替换的服务：

```bash
./local-ai server stop --name a --data-dir /raid/local-ai
# 仅移除已停止的实例容器；权重和宿主机日志保留
docker rm local-ai-a
./local-ai server start --host 0.0.0.0 --profile b300-tp4 --gpus 0,1,2,3 --name a --port 18000 --data-dir /raid/local-ai
```

备份用户状态前退出相关客户端；不要将历史、凭据或原始日志提交 Git。
服务端完整日志在 `数据目录/instances/实例名/server.log`，安装与准备过程集中在 `数据目录/install.log`。
客户端完整会话日志在私有 `services/服务ID/logs/session-.../`。镜像、模型权重和用户状态需要分别规划备份。

多数管理命令输出 JSON；chat 的退出码沿用客户端，单次运行输出 JSON 事件。
参数错误或执行失败返回非零退出码。需要调用栈时，使用 `./local-ai --debug 命令组 子命令 ...`。

本项目没有自动负载均衡、用户配额、开机自启、跨主机 TP 或自动 GPU 调度；启动前确认设备可用并取得使用权；项目不依赖集群调度系统。
B300 与 GB300 的实际验收范围见[验证记录](validation.md)，不能用 CPU 测试代替硬件验证。

---

[English version](en/commands.md)
