# 使用手册与命令参考

全局 `./local-ai --version` 输出项目版本后退出；与 `client install --version` 的客户端版本选择参数不同。

## 从哪里开始

第一次部署先看 [README](../README.md)；本页用于查命令、参数和运行维护。首次先从 GitHub 下载完整程序并解压；解压目录就是安装目录，以下在 /raid/local-ai 执行 ./local-ai。

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
./local-ai server start --help
./local-ai chat --help
```

通用格式为 `./local-ai 命令组 子命令 参数`；install、export、profiles 和 chat 没有下级子命令。
每一级都支持 `--help`。全局 `--debug` 必须放在命令组之前，用于错误时显示 Python 调用栈。

## 全部命令

| 命令 | 执行位置 | 作用与结果 |
|---|---|---|
| `config show` | BCM | 查看默认值及配置文件位置 |
| `config set` | BCM | 仅修改 endpoint/model 默认值，不安装资源 |
| `config unset` | BCM | 清除 endpoint/model 默认值 |
| `install` | 目标主机或准备机 | 就地准备所选角色资源并保存安装设置 |
| `export` | 已安装主机或准备机 | 完整离线包及 SHA256，默认 dist/ |
| `profiles` | 任意一端 | 输出配置目录和验证状态，JSON 格式 |
| `server inventory` | GPU001 | 读取本机 CPU 架构及 GPU 型号、UUID、显存 |
| `server plan` | GPU001 | 输出 GPU 选择、引擎参数及 Docker 启动命令；不创建容器 |
| `server start` | GPU001 | 检查资源、启动并等待 API；成功表示已就绪，返回状态与日志位置 |
| `server status` | GPU001 | 明确显示已就绪或尚未就绪；返回原因、监听状态和日志位置 |
| `server warmup` | GPU001 | 对健康的受管实例显式执行有限推理预热，记录进度 |
| `server stop` | GPU001 | 停止指定实例，保留权重和宿主机日志 |
| `image pull` | 联网 GPU 准备机 | 拉取固定镜像并记录平台身份 |
| `image export` | Docker 准备机 | 导出镜像归档及配套锁文件 |
| `image import` | 离线 GPU 节点 | 校验归档与锁文件后导入镜像 |
| `model download` | 联网准备机 | 下载固定模型配置、分词器、索引和全部权重分片 |
| `client install` | bcm-headnode | 安装所选版本原生客户端，或导入本地程序 |
| `client export` | BCM 准备机 | 打包客户端与公共缓存，不包含个人历史和凭据 |
| `chat` | bcm-headnode | 连接推理服务，在本机以当前用户权限执行工具 |

server 通过 Docker 运行 vLLM；plan 的 JSON 中 `command` 字段就是将使用的 Docker 参数。
chat 连接指定 API 并启动本机 OpenCode；不是登录容器后再执行你的工具命令。

引擎参数不做任意透传；模型和 vLLM 参数在 profiles.json/profiles.py 中维护。启动后实例目录保存 spec.json、args.json、docker-command.json 和 launch.log，便于核对实际配置。

## 统一安装与完整导出

install 在解压目录中准备资源，不另复制源码。首次默认客户端；--role 可选 server、client、both，后续默认取安装记录。--profile 选择服务端配方；安装不启动 GPU 服务。
--offline 只用本地资源，缺文件或校验失败即停止；--online 允许下载。含 bundle.json 的包默认离线，否则默认在线。--client-version 显式选版，默认复用本地版本；--endpoint 保存 API 地址，后续 chat 可省略。
export 一并打包完整程序、模型、镜像归档、客户端和配方。--output 默认 dist/local-ai.tar，旁边生成 .sha256；--profile 可重复，默认取安装记录；--client-dir 可首次携带旧版客户端；--data-dir 可携带旧数据。包内相对顶层 local-ai/，支持换目录名。
导出排除 dist/、旧实例、日志、运行缓存、Git 元数据、个人历史和凭据。源码在 src/，启动文件为 local-ai，手册在 docs/。公共客户端默认 clients/CPU；个人状态仍由 --state-dir 隔离。安装和导出统一写安装根目录的 install.log。

```bash
cd /raid/local-ai
./local-ai install --role server --profile b300-tp4
./local-ai export
./local-ai export --output dist/local-ai.tar.gz
```

外部模型配方：设置 LOCAL_AI_CATALOG，格式及验收见[开发指南](development.md#模型与客户端兼容性)。

安装时 --model 可指定客户端模型 ID；服务端以 --profile 中的模型为准，两者显式冲突时报错。服务启动、模型下载和聊天默认复用安装记录中的配方及模型；命令行参数仍可覆盖。

BCM 使用 install --role client --endpoint http://GPU001:18000/v1，替代上述 server 安装命令；两台机器各自保存设置。兼容的准备机可用 --role both 准备两端资源。client install/export 是只处理客户端的低级命令，不能替代完整 install/export。

初次安装的 install --endpoint 仅在安装成功后将地址写入安装根目录 installation.json 的 endpoint 字段。不传该参数时保留已有地址；首次安装不会自动发现服务端地址。未保存地址时，chat 必须传 --endpoint；chat --endpoint 只覆盖本次连接，不保存。GPU 安装与 BCM 客户端设置分开配置。

## 配置客户端默认值

config show 显示配置文件路径及已配置的 endpoint/model；config set KEY VALUE 修改一项默认值；config unset KEY 清除该项。KEY 只允许 endpoint 或 model。它们不安装、不下载、不请求 API，也不创建 install.log。

在 BCM 的 /raid/local-ai 执行：

```bash
./local-ai config show
./local-ai config set endpoint http://GPU001:18000/v1
./local-ai config set model DeepSeek-V4.1-Flash
```

更换长期默认节点时替换 config set endpoint 的 URL。清除默认值用 config unset endpoint 或 config unset model。清除地址后 chat 必须带 --endpoint；清除模型后回退到配方默认模型。show 中 null 表示未显式配置。

也可直接编辑现有 /raid/local-ai/installation.json 的 endpoint/model 字段，保留其他字段和合法 JSON；下一次命令读取新值。config set 会校验 URL/模型并保留安装元数据。config show 显示绝对路径，数据目录覆盖不改变配置文件位置。该安装目录使用者共享默认值，修改受文件权限控制；个人历史仍各自保留。

## 本地复用与安装日志

准备命令默认先检查本地：镜像的平台及固定摘要匹配，就不访问仓库；模型配置、分词器、
索引和所有分片完整，就不联网下载。模型检查包含 safetensors 长度与偏移检查，不等同于逐文件 SHA256。
带有 model.lock.json 时核对仓库和 revision；缺锁则明确返回 revision_verified=false，不伪造已验证状态；
锁文件版本冲突或权重截断直接报错。离线包首次安装按 bundle.json 中的逐文件 SHA256 验收完整内容。

`image pull --force` 显式联系镜像仓库；`model download --force` 从固定 revision 强制重新下载，
可能重新传输完整权重。普通重复执行不需要加它。

install/export 默认写安装根目录的 install.log；低级 image/model/server 操作写数据目录/install.log，client install 写客户端程序目录/install.log。每次操作有独立 ID，记录时间、主机、版本、参数、
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
| `--data-dir` | server 的 plan/start/status/stop/warmup；image；model download | 运行数据根目录；先取 LOCAL_AI_DATA_DIR，未设置则为程序所在的解压目录。status 实际按实例名查询。 |
| `--profile` | plan/start、image、model download | 硬件与引擎配置。image 必填；plan/start/model 优先取已安装配方，未安装时默认 b300-tp4。 |
| `--gpus` | plan/start | 必填，逗号分隔的本机 GPU 编号或完整 UUID；数量匹配配置 |
| `--name` | plan/start/status/stop/warmup | 实例名，默认 a；须以小写字母开头，仅含小写字母、数字和连字符，最长 32 字符 |
| `--host` | plan/start | IPv4 监听地址，默认 127.0.0.1；0.0.0.0 监听所有 IPv4 网卡，也可指定本机 IP；不接受主机名或 IPv6 |
| `--port` | plan/start | 模型 API 端口，默认 18000，允许 1024–65535 |
| `--wait-timeout` | 仅 start | 等待 API 就绪的秒数，默认 600，须大于 0；超时退出 1，保留容器 |
| `--warmup` | 仅 start | API 就绪后显式执行真实推理预热，默认关闭 |
| `--warmup-timeout` | 仅 start | 预热阶段独立期限，默认 600 秒，须为正数；配合 --warmup |
| `--timeout` | 仅 warmup | 预热总期限，默认 600 秒，须为正数 |
| `--input-tokens` | 仅 warmup | 逗号分隔正整数，精确输入长度；默认取上下文允许的 1024,8192,32768 |
| `--concurrency` | 仅 warmup | 逗号分隔正整数，并发请求数；默认 1,2,4,8，各自不超过两倍 max-num-seqs |
| `--output-tokens` | 仅 warmup | 输出长度，默认 256，须为正整数且输入加输出不超过上下文 |
| `--repeats` | 仅 warmup | 每组输入长度与并发的轮数，默认 2，须为正整数 |
| `--inventory` | 仅 plan | 从 JSON 测试清单生成计划，代替实时硬件发现；start 不接受 |
| `--output` | image export | 必填，导出镜像的归档路径 |
| `--archive`、`--lock` | image import | 均必填，镜像归档及其配套 .lock.json 路径 |

B200 四卡可选 b200-tp4-cpu（CPU Engram）或 b200-tp4（GPU Engram），均为实验性；保护值和操作见[部署指南](deployment.zh-CN.md#b200-四卡实验性)。

TP 表示张量并行：b300-tp4 在同一主机上使用 4 张 B300；GB300 配置及验证限制见[部署指南](deployment.zh-CN.md)。
默认程序和数据都在解压目录（示例 /raid/local-ai）；--data-dir 可覆盖数据位置，不同命令不会继承前一次的参数。下载、计划、启动和停止须使用同一数据根目录。

例如在 GPU001 上预览、启动和查询：

```bash
./local-ai server plan --host 0.0.0.0 --profile b300-tp4 --gpus 0,1,2,3 --name a --port 18000
./local-ai server start --host 0.0.0.0 --profile b300-tp4 --gpus 0,1,2,3 --name a --port 18000
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

server warmup --name a 只处理所选数据根目录中运行且健康的受管实例，使用其保存的 spec.json/args.json，不改变配方。start --warmup 在 API 就绪后执行相同步骤。失败或超时退出 1，中断退出 130，均保留容器。status 将 warmup 与 API 就绪分开报告，不生成请求。日志与有限覆盖范围示例见[DSpark 与预热](deployment.zh-CN.md#单用户-dspark-与显式预热)。

## 客户端参数

client install/export 均接受 `--client-dir`，默认是安装根目录下的 `clients/本机架构/`，存放公共程序。个人状态与程序目录分开。
状态根目录默认 `~/.local/state/local-ai`；设置 XDG_STATE_HOME 时则为 `$XDG_STATE_HOME/local-ai`。

| 参数 | 适用命令 | 含义与默认值 |
|---|---|---|
| `--binary` | client install | 导入本地 OpenCode 程序；省略则在线下载 |
| `--seed-cache` | client install | 导入离线公共缓存目录；可选 |
| `--version` | client install | 显式选择版本；省略时复用安装或识别导入程序；首次在线下载参考版本 1.19.5 |
| `--sha256` | client install | 本地导入程序的预期 SHA256；可选，来自可信材料清单 |
| `--output` | client export | 必填，客户端归档输出路径；同时生成 .sha256 |

离线步骤按[已有安装导出](offline.md#场景一从已安装环境导出并迁移)或[联网准备](offline.md#场景二从联网环境下载并准备)选择；两条路线都包含目标端导入示例。CPU 架构按 BCM 本机选择，与 GPU 服务端独立。

## chat 参数

| 参数 | 含义与默认值 |
|---|---|
| `--endpoint URL` | 本次连接的 HTTP(S) 模型 API 地址，包含端口与 /v1；覆盖可选的安装默认值，不写回设置 |
| `--project` | BCM 上已存在的工作目录，默认当前目录 |
| `--client-dir` | 原生客户端目录，须与安装位置一致 |
| `--state-dir` | 私有历史、缓存和会话日志根目录，默认见上节 |
| `--model` | API 中的服务模型 ID，默认取安装记录，未配置时读取配方的 served_name |
| `--check` | 只检查连接和模型可用性，输出 ready、实际 endpoint、model 与日志位置后退出 |
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

一套 BCM 安装可连接多个 endpoint，见[多服务示例](../README.md#从同一个-bcm-连接多个服务)。模型相同可沿用安装默认模型；目标服务模型不同时，使用 chat --model ID，本次覆盖不改写默认值。不匹配时列出服务发布的 ID，不会静默挑选其他模型或回退到默认节点。恢复参数作用于选定 endpoint 的私有历史。

### 动态思考档位

在 bcm-headnode 的交互聊天输入区按 **Ctrl+T** 循环切换，确认界面显示的档位后再发送消息。作用于下一条用户消息及其模型调用；不会中断或改写正在生成的回答。无须退出会话、编辑配置或重启 GPU 服务。初次升级需退出旧客户端，再按下节方法恢复原会话，聊天历史保留。OpenCode 管理已选档位的记忆；需要回到原有行为时选 `normal`。

| 档位 | DeepSeek-V4.1-Flash 请求行为 |
|---|---|
| `normal` | 不附加思考参数，沿用原有服务端默认行为 |
| `low` | 开启思考，强度 25 |
| `high` | 开启思考，强度 50 |
| `xhigh` | 开启思考，强度 75 |
| `max` | 开启思考，强度 100 |
| `none` | 关闭思考 |

强度是模型提示，不是固定 token 上限或耗时保证；降低强度或关闭思考可能影响复杂任务质量。`normal` 与未选择档位都不强制改变原参数。原生界面的循环顺序由 OpenCode 合并配置后决定，不承诺与表格顺序一致。已禁用该模型不支持的通用 `medium`/`minimal` 档位。

这些档位定义在模型配方的 `client.variants`，不是 GPU profile 的引擎选项；自定义完整 catalog 须自行合并。其他模型不自动继承 DeepSeek 参数。调整在聊天界面完成。原生客户端验收见[验证记录](validation.md)，其他客户端版本需另行检查。

循环中还会经过一个不显示档位名称的原生默认状态，与 normal 同样不附加思考参数。不要在自定义配方中显式声明 default 档位；该名称与 OpenCode 1.19.5 的循环回绕内部值冲突。

### 恢复会话与终端复制

首次运行 chat（包括 --check）会在 `~/.local/bin/opencode` 创建当前用户的恢复入口。
退出提示中的 `opencode -s ses_...` 可直接执行，自动找回原 endpoint、项目目录和私有历史。
若该目录不在 PATH，按提示执行 `export PATH="$HOME/.local/bin:$PATH"`，并按需加入 `~/.profile`。
不会覆盖已有的其他 opencode 程序；有名称冲突时使用下面的显式入口：

```bash
./local-ai chat --endpoint http://GPU001:18000/v1 --project /home/alice/project --session ses_example
./local-ai chat --endpoint http://GPU001:18000/v1 --project /home/alice/project --continue
```

`--session`（`-s`）恢复指定会话，`--continue`（`-c`）继续本项目最近会话，二者互斥。
自动恢复入口只负责 `opencode -s ID`，不是全套原生 CLI 的替代品。
默认关闭 OpenCode 鼠标捕获、选中自动复制和内置复制/剪贴板读取快捷键，让终端处理文本选取与复制粘贴。
代价是界面内鼠标点击和滚轮操作停用；继续使用键盘导航，粘贴使用终端自己的快捷键。
tmux 自身的选取设置仍由用户管理；长对话可用 `/export` 导出。
新开或恢复会话后生效，不必重启推理服务。

### 客户端版本与离线恢复

客户端版本可以通过 `client install --version X.Y.Z` 选择，也可用 `--binary` 导入现有程序。
默认下载版本是验收参考，不是运行时版本白名单；程序不因版本号不同拒绝运行。
会话定位调用公开的 `session list --format json`，不读取 OpenCode 私有数据库表结构。
接口不兼容时明确报告失败的能力；不能保证任意未来版本无需适配。
升级应在独立客户端目录和临时历史中检查恢复参数、JSON 会话列表、鼠标关闭与终端粘贴，
再退出旧客户端、备份原历史并切换。旧版本不一定能读取新版本迁移后的数据库，回退应恢复升级前备份。

下载源不可用时可复用完整本地安装、导入本地程序，或使用 `client export` 的离线包；
包中包含客户端、公共缓存、版本清单及校验值，不含聊天历史或凭据。导入步骤见[离线部署](offline.md)。

## 文档读取自检

正常聊天直接指定文件或目录，不需要附件启动参数。document doctor 只检查转换器路径及 pdf_ready/office_render_ready，不安装软件。document read PATH 返回工具结果 JSON；--mode 可选 auto（默认）、text、render；--start 默认 1，--count 默认 3（允许 1–5），--offset 默认 0。失败退出非零，图片可能包含 base64。依赖安装、格式范围、出处与读取边界见[富文档指南](documents.md)。

## 程序更新

独立 Python 脚本 scripts/update.py 不属于 ./local-ai 子命令。--root、--version、--archive、--sha256、--rollback 的含义、完整示例、备份和退出码统一见[更新指南](update.md)。它不准备镜像、模型或客户端，也不重启推理服务；更换模型/镜像与升级原生 OpenCode 是独立操作。

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
./local-ai server stop --name a
# 仅移除已停止的实例容器；权重和宿主机日志保留
docker rm local-ai-a
./local-ai server start --host 0.0.0.0 --profile b300-tp4 --gpus 0,1,2,3 --name a --port 18000
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
