# 在客户端配置持久工作指令

本目录提供可维护的参考模板，供减少新对话中的重复纠正；提示词不能保证模型始终遵守。
这是个人 OpenCode 规则，不是仓库根目录的开发者 AGENTS.md。v1.4.3 起客户端安装默认应用通用模板。

## 文件与执行位置

- [通用模板](AGENTS.general.md)：回复语言、用户原话与来源、任务推进、长任务等待与进度汇报、证据、有限检索、项目位置与聊天工作目录；模板语言不决定回复语言。
- [BCM 模板](AGENTS.bcm.md)：/cm 组件定位及 /cm/images 排除；按本集群情况修改。
- [英文模板和说明](en/agent-instructions.md)：相同配置流程，任选一种语言组合，不要重复加载两套。

在运行 OpenCode 的客户端 bcm-headnode，以实际聊天用户执行。示例安装根是 /raid/local-ai，
项目是 /home/alice/project；替换为本机真实路径。无需在 GPU001 上配置。
默认个人文件为 ~/.config/opencode/AGENTS.md；root 对应 /root/.config/opencode/AGENTS.md。
启动 local-ai 前设置 XDG_CONFIG_HOME 时，改用 $XDG_CONFIG_HOME/opencode/AGENTS.md。
使用 sudo 切换用户或改变 HOME 会改变个人文件归属，必须按实际运行用户核对。

v1.4.0 会先解析上述个人路径，再为 OpenCode 设置隔离的会话配置目录。
存在的个人文件通过生成配置的 instructions 列表显式加载，排在内置 operations.md 后面；
不导入用户的其他模型、插件或连接配置，聊天启动本身不修改个人规则。项目 AGENTS.md 仍由原生客户端加载。
这些指令是组合关系，应人工消除冲突，不把文件顺序当成可靠的冲突解决机制。
v1.3.7 发布源码没有这段显式加载逻辑；使用 v1.4.0 或更新版本，开发分支另行核对提交。

## 安装时自动应用

在实际聊天用户的客户端执行，不要为了安装个人规则而切换到 root；sudo/root 安装只配置该运行用户，不推断其他用户或修改全体用户配置。安装程序默认使用中文通用模板，模板语言不决定回复语言。

```bash
cd /raid/local-ai
./local-ai install --role client --endpoint http://GPU001:18000/v1
# BCM 场景：通用模板加 BCM 模板
./local-ai install --role client --instructions bcm
# 需要英文规则时
./local-ai install --role client --instructions bcm --instructions-language en
# 只准备客户端，不创建或修改个人规则
./local-ai install --role client --instructions none
```

install --role client/both 和低级 client install 都支持这两个参数；server 角色不配置个人规则。离线安装行为相同，无需另行下载模板；在线准备机只想打包程序时使用 --instructions none。重复运行不必重新下载已验证的客户端，也不启动 GPU 服务。

安装后 JSON 的 client.instructions（低级命令为 instructions）返回 path、status（created/updated/unchanged/skipped）、template、language，修改已有文件时还有 backup；跳过时仅返回 status。进度和备份位置写 stderr 及 install.log。

- 文件不存在时创建；已有文件在末尾添加一个 local-ai 管理区块，保留原内容。
- 重复安装只替换 `<!-- local-ai:instructions:begin -->` 到 `<!-- local-ai:instructions:end -->` 之间的区块；内容相同时不写入、不重复备份。
- 每次改变已有文件前，先保存同目录 AGENTS.md.bak-随机后缀，备份权限 0600；再原子替换目标，文件不放宽到其他用户可读写。
- 自定义规则放在管理区块外；区块内修改会在下次安装时被模板替换。以前手工复制的模板不会自动删除，首次应用时按需人工消除重复或冲突。
- --instructions none 既不修改也不移除现有管理区块。若长期自行维护规则，每次安装显式传入该参数。
- 目标为符号链接、其他用户文件、标记损坏或写入失败时安装报错，不宣称配置完成；可修复后重试，或用 --instructions none 保留自管规则。

需要恢复时，先备份当前文件，再将 JSON/安装日志所示的 backup 复制回 path；退出并重新启动 OpenCode。个人主机名、目录和凭据不应写入 templates/，它会随源码更新而替换。

## 核对实际加载

安装应用规则或手工修改实际个人 AGENTS.md 后，退出并重新启动 OpenCode，让新会话重新读取规则，再以同一用户、同一环境运行以下命令；模型服务和客户端须已安装可达：

```bash
cd /raid/local-ai
./local-ai chat --project /home/alice/project --check
```

输出 ready=true 只表示连接检查成功。将返回的 log_directory 填入下面占位符：

```bash
python3 - /absolute/log_directory <<'PYTHON'
import json
import sys
from pathlib import Path

cfg = json.loads((Path(sys.argv[1]) / 'opencode.json').read_text())
for name in cfg['instructions']:
    print(name)
PYTHON
```

应同时出现私有会话中的 operations.md 和当前用户个人 AGENTS.md；不存在个人文件时只有前者。
配置中列出路径证明已传给客户端，不能代替检查最终模型请求。
可运行 `PYTHONPATH=src python3 scripts/check-instructions.py --client-dir /raid/local-ai/clients/amd64`，
将客户端目录替换为实际架构位置。脚本使用临时个人/项目标记和本机模拟 API，检查实际模型请求中的
个人规则、项目规则与内置指引；不连接 GPU，不改个人文件。该检查也纳入原生客户端 CI。
可在个人文件临时加入独特验证标记，在新会话要求按该规则回复，或通过本地模拟 API 检查实际请求；
删除标记后再次新开会话。不得把一次回答当作所有规则永久有效的证明。
另用临时目录中可检查的测试脚本验证查找范围，查看真实工具参数，不能只相信模型说“已排除”。
不要拿整个 /cm/images 当测试数据；若规则未加载，先核对用户、环境、源码提交和生成配置。

实际任务应选择小型工作目录，不要把 /cm、/ 或包含全部计算节点镜像的目录作为 --project。
实测将小型镜像样本置于项目根目录内时，OpenCode 内部线程也会自行读取项目文件；
这类客户端行为不能靠模型提示词限制。测试镜像排除时，把样本放在项目目录外，
仅为该临时样本配置必要的外部目录权限，避免把非交互权限拒绝误报为用户拒绝。
不能把提示词当成文件访问的强制隔离；要强制限制访问，需另外设计账户权限或执行层控制。

## 后续维护与分发

通用模板的长任务约定要求合理分段等待、按重要变化与等待情况汇报、合并重复信息，并将大量输出优先写入日志；不规定固定汇报间隔、行数或强制标题。这是模型行为要求，不是定时器或后台通知机制，阻塞调用期间可能无法发送消息。只更新源码不会改动个人规则；再次运行客户端安装可应用新模板，再退出并重新启动 OpenCode。

客户端安装默认应用模板；独立 scripts/update.py 与 export 只更新/携带程序模板，不修改个人规则。升级后在实际聊天用户下重新运行客户端安装即可应用新模板；安装时自动备份已有文件。
完整离线包包含 templates/，但不包含 ~/.config/opencode 下的个人文件；迁移用户规则须自行安全传输。
旧更新器可能忽略 templates/，从包含此功能的同一源码包取得新版 scripts/update.py 后再执行程序更新。
不要通过替换 XDG_CONFIG_HOME 为全局目录来绕过会话隔离，也不要编辑每次生成的会话配置作为长期设置。

[返回 README](../../README.md) · [English](en/agent-instructions.md)
