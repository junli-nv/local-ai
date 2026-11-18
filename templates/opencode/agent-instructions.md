# 在客户端配置持久工作指令

本目录提供可维护的参考模板，供减少新对话中的重复纠正；提示词不能保证模型始终遵守。
这不是仓库根目录的开发者 AGENTS.md，也不是自动安装的全局策略。

## 文件与执行位置

- [通用模板](AGENTS.general.md)：回复语言、用户原话与来源、任务推进、证据、有限检索、项目位置与聊天工作目录；模板语言不决定回复语言。
- [BCM 模板](AGENTS.bcm.md)：/cm 组件定位及 /cm/images 排除；按本集群情况修改。
- [英文模板和说明](en/agent-instructions.md)：相同配置流程，任选一种语言组合，不要重复加载两套。

在运行 OpenCode 的客户端 bcm-headnode，以实际聊天用户执行。示例安装根是 /raid/local-ai，
项目是 /home/alice/project；替换为本机真实路径。无需在 GPU001 上配置。
默认个人文件为 ~/.config/opencode/AGENTS.md；root 对应 /root/.config/opencode/AGENTS.md。
启动 local-ai 前设置 XDG_CONFIG_HOME 时，改用 $XDG_CONFIG_HOME/opencode/AGENTS.md。
使用 sudo 切换用户或改变 HOME 会改变个人文件归属，必须按实际运行用户核对。

v1.4.0 会先解析上述个人路径，再为 OpenCode 设置隔离的会话配置目录。
存在的个人文件通过生成配置的 instructions 列表显式加载，排在内置 operations.md 后面；
不导入用户的其他模型、插件或连接配置，不自动修改个人规则。项目 AGENTS.md 仍由原生客户端加载。
这些指令是组合关系，应人工消除冲突，不把文件顺序当成可靠的冲突解决机制。
v1.3.7 发布源码没有这段显式加载逻辑；使用 v1.4.0 或更新版本，开发分支另行核对提交。

## 首次配置与合并

在 bcm-headnode 的安装根目录，用 Bash 执行。普通客户端只组合通用模板；BCM 场景使用下面两份。
如果文件已存在，脚本只备份并生成候选，不覆盖现有内容；人工比较、合并到 AGENTS.md。

```bash
cd /raid/local-ai
set -e
rules_dir="${XDG_CONFIG_HOME:-$HOME/.config}/opencode"
mkdir -p "$rules_dir"
candidate="$(mktemp "$rules_dir/AGENTS.candidate.XXXXXX")"
cat templates/opencode/AGENTS.general.md templates/opencode/AGENTS.bcm.md > "$candidate"
chmod 600 "$candidate"
if [ -e "$rules_dir/AGENTS.md" ]; then
  cp -p "$rules_dir/AGENTS.md" "$rules_dir/AGENTS.md.bak-$(date +%Y%m%d-%H%M%S)"
  diff -u "$rules_dir/AGENTS.md" "$candidate" || test "$?" -eq 1
  printf '保留已有规则；请人工合并候选文件：%s\n' "$candidate"
else
  mv -i "$candidate" "$rules_dir/AGENTS.md"
fi
```

不要把个人规则直接写入安装目录的 templates/：源码更新会替换它们。
本机主机名、项目目录及特殊约定保留在个人文件或对应项目 AGENTS.md，勿提交凭据或内部日志。

## 核对实际加载

结束旧聊天后重新启动。先以同一用户、同一环境运行以下命令；模型服务和客户端须已安装可达：

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

安装、更新和导出只携带模板，不自动应用；先比较新旧模板，再手工合并个人文件并备份。
完整离线包包含 templates/，但不包含 ~/.config/opencode 下的个人文件；迁移用户规则须自行安全传输。
旧更新器可能忽略 templates/，从包含此功能的同一源码包取得新版 scripts/update.py 后再执行程序更新。
不要通过替换 XDG_CONFIG_HOME 为全局目录来绕过会话隔离，也不要编辑每次生成的会话配置作为长期设置。

[返回 README](../../README.md) · [English](en/agent-instructions.md)
