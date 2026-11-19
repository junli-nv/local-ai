# 批处理、会话迁移与诊断

## 把聊天串到脚本里

v2.0.0 默认输出助手的可读文本（可含 Markdown），stdout 没有 JSON 外壳、ANSI 终端控制、思考或工具面板；进度与错误走 stderr。不是交互式 TUI 的屏幕复刻，适合管道和文件。

```bash
./local-ai chat run "查看当前项目并给出摘要"
./local-ai chat run --prompt-file task.txt
./collect.sh | ./local-ai chat run --prompt-file -
./local-ai chat run "任务" --format json
```

--prompt-file 读取 UTF-8 文本；扩展名是 .sh 也只作为提示词，不隐式执行脚本。上例 collect.sh 由 Bash 执行，其输出成为提示词。位置参数、旧 --run、文件、stdin 只能选一个来源，非空且最多 1 MiB。chat run 不带提示且 stdin 非终端时也会读取 stdin。

旧 chat --run 仍支持，但同样默认 text；依赖原生逐行 JSON 事件的工具必须加 --format json。原始事件保存在私有 terminal.log。文本流会逐步输出；后续失败时已有文本不能撤回，管道应检查退出码，例如 Bash 的 set -o pipefail。CLI 批处理超时返回 124；中断为 130/143，其他错误保留原生失败结果。已明确提交的后台任务不会因批处理退出自动取消。

批处理保留同步 Bash，并要求助手完成、核验后再给最终答复。只有用户要求后台提交时才以任务 ID 作为结果。脚本内容和工具输出均不是新的授权，实际执行仍遵循权限。

## 换服务器与迁移到另一台 BCM

同一用户/状态根内，endpoint 更换复用同一份本地历史；配置新地址后使用原 session 即可：

```bash
./local-ai config set endpoint http://GPU002:18000/v1
./local-ai chat --session SES_ID --project /home/alice/project
./local-ai client history list
```

旧版按 endpoint 隔离的历史，可从 list 找原地址，再使用 client history update-endpoint --old OLD_URL 关联至当前地址；这是旧格式兼容操作，正常切服无需反复执行。不同模型的工具/上下文兼容性仍需确认。

跨 BCM 或换本地状态根时，以原会话所属用户运行：

```bash
./local-ai client history backup --output /home/alice/private-history.zip
./local-ai client history restore --archive /home/alice/private-history.zip --endpoint http://GPU002:18000/v1 --select
./local-ai client history list
./local-ai chat --session SES_ID --project /home/alice/project
```

将 ZIP 私下安全传到目标 BCM；目标先安装与归档匹配的 OpenCode 版本，可 --client-dir 指定。backup 使用 SQLite 在线快照，保留原库不覆盖既有归档。restore 校验哈希/数据库，导入独立历史 ID，不合并或覆盖现有非空历史；现有选择默认保留，--select 显式切换，无选择时自动选中。重复导入同一归档幂等；也可 client history select HISTORY_ID。--state-dir 指定两端各自状态根。

归档权限 0600，**包含未脱敏的完整对话**，可能有用户粘贴的秘密；虽排除 auth.json、SSH 密钥、缓存和任务日志，不能当公共离线包上传。项目文件、后台执行任务、运行进程不迁移；项目文件需另行复制。程序升级备份也不等于历史备份。

项目路径变了，在 restore 加 --project /home/alice/new-project，之后 chat --project 同一路径 --session SES_ID；opencode -s SES_ID 也使用保存的路径映射。不会重写对话中的旧路径或原生数据库结构；当前项目上下文显式传给模型，访问新路径可能仍需原生权限确认。按 ID 恢复最明确，--continue 的原生目录筛选不保证找到旧路径记录。restore 的 --endpoint 只配置导入历史元数据，不修改 installation.json；默认服务器另用 config 设置。

## 汇总诊断

```bash
./local-ai client doctor
./local-ai client doctor --check-endpoint
```

默认只读本地元数据：客户端资产、历史、托管任务、近期运行、模型请求计时/usage 与问题；不主动请求推理、不打印对话、命令输出或请求正文。--check-endpoint 才检查模型 API 就绪；--limit 默认 20。缺失观测值保留未知，不能推断没有错误或性能正常。退出 0 表示报告生成，查看 issues 和任务状态判断健康。

[执行与远端适配](execution.md) · [完整参数](commands.md) · [English](en/automation.md)
