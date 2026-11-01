# 开发与扩展流程

## 开发规则的适用范围

本页约定用于修改 local-ai 仓库；普通系统与硬件运维任务不需要先走开发流程。
项目指令在根目录 [AGENTS.md](../AGENTS.md)。只有 `server plan --inventory FILE`
这一纯计划功能不得额外探测硬件、启动子进程或写文件；不限制用户要求的本机或 SSH 硬件查询。
客户端的通用运维指引由 [operations.py](../src/local_ai/operations.py) 提供，
每次 `chat` 启动时写入私有会话目录并通过客户端配置加载。

## 项目配置文件

`pyproject.toml` 是 Python 项目的构建和开发配置，日常运行源码中的 `./local-ai` 无需修改它。

| 配置节 | 本项目的用途 |
|---|---|
| `build-system` | 使用 setuptools>=68 构建安装包 |
| `project` | 包名 cluster-local-ai、版本 0.1.0、Python>=3.10；运行时第三方依赖为空 |
| `project.scripts` | 安装后的 local-ai 命令调用 local_ai.cli:main |
| `tool.setuptools` | 从 src 查找模块，并将 profiles.json 包含到安装包 |
| `project.optional-dependencies` | dev 组包含 Ruff 0.14.2，仅开发时安装 |
| `tool.ruff` | Python 3.10 兼容目标、100 字符行宽和静态检查规则 |

仓库根目录的 Bash 脚本 `local-ai` 将 src 加入 PYTHONPATH 后运行同一入口。
模型、GPU 及 vLLM 参数由 profiles.json/profiles.py 管理；使用者查[命令手册](commands.md)。

## 准备环境与执行检查

运行时代码仅使用 Python 标准库。可选开发工具安装在项目虚拟环境，不写入系统 Python：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/python -m unittest discover -s tests -v
.venv/bin/ruff check src tests
.venv/bin/ruff format --check src tests
git diff --check
```

`pip install -e '.[dev]'` 以可编辑方式安装当前项目及 dev 工具；代码改动无需重复安装。
`unittest -s tests` 从 tests 目录发现测试，`-v` 显示测试名；`ruff check` 检查规则，
`ruff format --check` 只检查格式不改文件；`git diff --check` 检查补丁空白错误。

CPU CI 检查策略与失败边界，无法证明 CUDA 内核兼容性、硬件最低内存、互联拓扑或吞吐。

## 接手开发与提交约定

1. 先读 README 的拓扑和使用手册，再读架构及验证记录；真实环境信息和原始日志保留在忽略目录，不能带进提交。
2. 命令入口集中在 cli.py；新增命令须提供逐级 --help、参数含义、默认值、执行位置，并同步中英文手册。
3. GPU/CPU/镜像平台与客户端架构独立；新增型号优先添加 profiles.json 配置和测试清单，不写真实主机名或 GPU UUID 到逻辑中。
4. 引擎参数只从 profiles.py 生成；固定模型 revision、镜像清单与平台摘要，不能用可变标签代替版本身份。
5. plan 在使用给定硬件清单时不得运行子进程或写文件；启动前再检查真实占用、CDI 和平台。
6. 安装诊断经 installlog.py 集中记录，JSON 标准输出与进度标准错误分离；不能把预期的缺失探测误标为安装失败。
7. 本地复用必须验证完整性并区分版本已核实/未核实；不得伪造版本锁。离线导入同时保留归档校验和内容身份检查。
8. 修改后运行本页的 unittest、Ruff 和 diff 检查；测试失败先修复，不能通过删改既有验收用例来“通过”。
9. 新平台和 GPU 测试写明来源、分配设备、版本、方法、结果、限制；CPU 测试不能提高硬件验证等级。
10. 发布前审查暂存文件，记录提交、依赖版本和验收结果；确认临时容器、客户端进程和资源已清理，再推送并查看 CI。

新增 GPU 的标准流程见下一节。B200 或后续型号拿到硬件后再新增并验收，不能修改已验证配置来冒充新型号支持。

## 没有 GPU 时也能开发

复制已有[硬件清单样本](../tests/fixtures/b300-tp4.json)编写脱敏测试数据，先验证参数生成与拒绝条件。
以下命令不探测真实 GPU，不启动容器，也不创建数据目录：

```bash
./local-ai server plan --host 0.0.0.0 --profile b300-tp4 --gpus 0,1,2,3 --inventory tests/fixtures/b300-tp4.json --data-dir /tmp/local-ai-plan
```

配置入口：[profiles.json](../src/local_ai/profiles.json)；引擎参数：[profiles.py](../src/local_ai/profiles.py)；
策略边界测试：[test_policy.py](../tests/test_policy.py)；安装、缓存和文档约定测试：[test_installation.py](../tests/test_installation.py)。

## 新增硬件配置

1. 核对上游模型配方，以及目标 OS 实际可见的 GPU 数、显存、CPU 架构、互联和主存。
2. 确认镜像清单提供目标平台，记录固定的清单摘要及平台子摘要。
3. 在 `src/local_ai/profiles.json` 添加架构、平台、本地 TP 数、Engram 位置、
   GPU 类型、保守显存保护值和验证级别。
4. 引擎参数统一在 `profiles.py` 生成；不在 BCM 客户端加入 GPU 分支，也不从服务端推断客户端架构。
5. 测试有效与无效选择、编号/UUID 重复、缺失设备、CPU/镜像不匹配和内存不足。
6. 使用 `server plan --inventory FIXTURE.json` 检查计划。
   只有 plan 接受测试清单，start 必须发现真实硬件。
7. 在已分配硬件上准备固定镜像和权重，启动后等待 API，测试流式输出和原生工具往返，
   再从 BCM 执行真实的编辑、测试和 hostname 任务；检查内存及日志，最后停止实例。
8. 将版本、方法、结果及限制写入 [验证记录](validation.md)。
   不能仅凭单元测试把配置标记为实机验证通过。

同一 OS 只有两张 GPU 的 GB300 需要 TP2 配置和足够主存。
跨 OS 的张量并行属于新的编排能力，不能只修改配置 JSON 来实现。

## 新增或升级模型

同时修改固定仓库/revision、分词器/解析器、模型目录和客户端能力声明。
验证流式结束、思考内容传输、工具调用/结果往返，以及真实文件编辑和测试。
不能把已有服务模型名静默指向另一个 revision。
思考预算或量化变更要与运行时优化分别记录。

## 客户端与离线资源

原生程序按 BCM 的架构选择，与服务端平台独立。
在线安装固定 NPM 版本，并在提取、执行允许的二进制前校验 SHA256/SHA512。
导入程序需检查 ELF 架构、可选 SHA256 和请求的版本。
CPU 架构一致不等于完整 ABI 兼容，还需检查发行版、共享库和 CPU 指令支持。

资源包只包含程序、允许的公共缓存和清单，不包含历史、认证文件或 SSH 密钥。
模型权重与 CPU 架构无关；镜像、原生程序及缓存中的可执行文件与架构有关，
不能混用 AMD64 与 ARM64 缓存。

## 测试与评审原则

- 计划生成应确定、无子进程和文件写入。
- 测试拒绝状态及退出清理，不只检查正常命令。
- 导入镜像后核对配置/层身份，不能只核对 tag。
- 验证两个会话的历史稳定、端点连接配置独立。
- 用 hostname 验证工具在 BCM 执行，不能只看模型回复成功。
- 原始日志及实际基础设施标识保存在被忽略的运行目录，只提交脱敏汇总。
- CI 不得启动 GPU 工作或修改集群状态、固件、网络。
- 重构与发布时保留现有生产服务状态。

推送前检查暂存文件，排除权重、二进制、缓存、凭据和私有路径，并执行全部检查。
源码、测试、文档与 CI 一并提交；新增平台尽量保持变更集中，
具备验收证据后才提高其验证级别。

---

[English version](en/development.md)

## 模型与客户端兼容性

默认 DeepSeek 配方不是模型白名单。profiles.json 的 models 保存仓库、revision、
model_directory、served_name、镜像、engine_options、environment 和 client 能力；
default_model 选择默认客户端模型，硬件 profile 的 model 字段选择服务端配方。
profile 的 engine_options 覆盖模型的同名选项；对象/数组编码为 JSON，true 发出独立开关，
false/null 省略。监听、端口、模型路径和 TP 参数仍由管理命令控制。
DeepSeek 解析器、Engram 和推理格式只属于其配方，不自动用于其他模型。

复制内置 profiles.json 到自己的文件，添加模型与 profile，再设置：

```bash
export LOCAL_AI_CATALOG=/home/alice/local-ai-profiles.json
./local-ai profiles
```

每个新模型/revision 使用独立 model_directory。锁位于该目录内的 model.lock.json；
旧版根级锁仅在仓库与目录匹配时复用。客户端可用 chat --model 选择其他
OpenAI-compatible 模型，在 client 中声明 reasoning、tool_call、interleaved 和 limit。
未登记模型不自动套用 DeepSeek 的上下文或推理格式。新增配方不继承原配方的实机验证等级。

当前下载器面向 Hugging Face snapshot，权重校验面向带索引的分片 safetensors，
服务端使用 vLLM；其他权重格式或引擎须增加适配。配置可生成不等于模型工具调用或硬件已验收。

客户端不设运行时版本白名单。省略 client install --version 时复用已安装版本，
导入本地程序时识别其版本，仅首次在线下载使用参考版本；也可显式指定版本。
在线源失效时使用现有安装、本地程序或离线包。升级候选放在独立 --client-dir，运行：

```bash
PYTHONPATH=src .venv/bin/python scripts/check-client.py --client-dir /home/alice/client-candidate
```

脚本用临时状态、原生会话 HTTP API 和伪终端检查恢复、公开 JSON 元数据、
鼠标关闭和终端粘贴模式，不调用 GPU 或模型生成。CI 自动检查参考版本；
手动工作流的 client_version 可测试候选版本。外层终端真实复制、模型工具往返和
历史迁移仍需验证。切换前退出客户端并备份历史；跨数据库迁移回退时恢复原备份。
