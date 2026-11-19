# 长命令托管、插话与暂停/停止

v2.0.0 包含自动 Bash 托管、完成通知、PTY 输入及 SSH/Slurm/容器适配。更新程序后退出并恢复聊天以加载插件，无需重启模型服务；参考客户端仍为 OpenCode 1.19.5。

## 最简单的用法

聊天中直接要求执行长命令；默认交互模式下，普通 Bash 短命令等待约 400 ms，较长命令转为托管任务并返回 job_ ID，随后可以继续提问。也可明确要求“用后台任务执行，完成后告诉我结果”。助手通过 local_ai_task 操作任务。启动成功不代表任务完成。

有按命令匹配的 Bash 权限规则时保留原生解析器，普通 Bash 仍同步；明确使用 local_ai_task 托管。--sync-bash 可手动保留原生 Bash。其他同步工具仍可能阻塞消息，不能保证任何场景都即时响应。[批处理](automation.md)默认使用同步 Bash，便于串联实际结果。

直接在当前项目运行：

```bash
./local-ai client job start --command 'sleep 30; echo done'
./local-ai client job list
./local-ai client job status JOB_ID
./local-ai client job output JOB_ID
./local-ai client job pause JOB_ID
./local-ai client job resume JOB_ID
./local-ai client job stop JOB_ID
./local-ai client job remove JOB_ID
```

pause/stop 的 control_requested 仅表示请求已记录；随后 status 确认 paused 或 terminal=true。停止本机任务先 TERM，唤醒暂停进程，一秒后必要时 KILL，只作用于核验身份的自有进程组。remove 只接受终态，保留防重放键；有意重新执行使用新 request_id。

## 会话、通知与后台生命周期

```bash
./local-ai client job pause-session --session SES_ID --project /home/alice/project
./local-ai client job resume-session --session SES_ID --project /home/alice/project
./local-ai client job stop-session --session SES_ID --project /home/alice/project
```

SES_ID 是 job list 中准确的 ses_ 标识；CLI 创建任务默认 session=cli。pause-session 关闭该会话新工具入口并暂停自有任务；resume-session 放行并恢复因会话暂停的任务。单独暂停的任务需单独恢复。stop-session 保持入口关闭，继续前显式 resume-session。暂停不会撤销已完成写入或已发出的模型请求。

聊天仍运行且空闲时，插件检查完成状态，发送带稳定消息 ID 的通知，模型读取输出后汇报、继续此前已授权工作。通知只代表状态，不增加授权；用户忙于其他消息或会话已暂停时推迟。--no-task-notifications 关闭本次聊天的通知。退出/中断聊天会暂缓通知，不隐式停止后台命令；恢复会话并发送消息后继续检查。没有常驻聊天之外的通知守护进程。

本机 worker 和适配控制器各有代码副本，可跨聊天退出、程序升级继续运行；机器重启不自动恢复或重放。未知/失联状态不能报告完成。orphaned 表示 worker 丢失且进程可能仍在，lost 表示结果不完整；应核验后处理。主动 setsid 的后代不保证被本机进程组控制。没有新增操作系统沙箱。

## PTY 输入与接管已有进程

```bash
./local-ai client job start --interactive --command 'read -r answer; echo "$answer"'
./local-ai client job input JOB_ID --data $'hello\n' --request-id answer-1
./local-ai client job adopt --pid 123456
```

PTY 仅限本机新任务；input 每次 1..16384 UTF-8 字节，换行需显式传入。稳定 request_id 防止重复输入；最多 64 条排队、4096 个输入键。adopt 只接管同用户、独立进程组的组长 PID，拒绝当前调用链；不重新执行命令、不重接 stdout/终端。自然退出为 exited、退出码未知，不能当作成功。不能自动把任意已运行 TUI 改为可输入后台任务。

## SSH、Slurm 与容器

```bash
./local-ai client job start --adapter ssh --host GPU001 --remote-project /raid/work --command 'sleep 30; echo done'
./local-ai client job start --adapter slurm --project /home/alice/project --submit-arg=--mem=128M --command 'hostname'
./local-ai client job start --adapter container --host GPU001 --image MY_PREPARED_IMAGE --command 'echo done'
```

明确 --adapter 才使用远端选项。SSH 需目标可用 Python 3、非交互 SSH；远端目录必须存在且为绝对路径。Slurm 默认本机提交，可 --host 指定提交机；项目及输出文件所在目录须在提交机与计算节点共享。默认一 CPU，内存沿用站点默认值，按需显式传 --submit-arg；不自动申请 GPU。--remote-project 适用于 SSH/Slurm。

容器只使用已存在镜像，--pull=never；默认 NVIDIA_VISIBLE_DEVICES=void，不分配 GPU，不自动挂载项目，工作目录沿用镜像。容器需要目标 Docker 权限。本机无需 Docker，远端容器需 --host。没有远端 PTY。状态、输出及 pause/resume/stop 复用同一 job ID；取消后必须查询调度器/容器的实际状态。容器标签、Slurm 用户与作业名、远端进程身份均校验；后端失联为 unreachable/unknown，不重新提交未知作业。

## 输出、限制与隐私

状态根默认 ~/.local/state/local-ai，execution/ 按用户、项目真实路径、会话隔离，与 endpoint 无关。工具拒绝跨会话/项目控制；当前用户可在 CLI 明确 job ID 管理自己的任务。目录 0700、文件 0600。命令/输入/输出可能含敏感信息，不进入公共离线包或历史迁移包。

output 默认 16384 字节，--limit 范围 1..65536；复用 next_offset 直到终态且 all_output_delivered=true。text 是 UTF-8 预览，跨页字符可能替换；data_base64 能还原原始字节。truncated=true 必须报告缺口。

默认超时 3600 秒（含暂停），最大 604800 秒；每状态根最多 32 个未结束任务。本机/SSH 合并输出超过 64 MiB 停止并标记缺口；容器只保留至多 64 MiB 快照，超量/轮转标记缺口，不因此停止容器。Slurm 日志按需分页。completed/failed/cancelled/timed_out 等状态与 exit_code 一起判断；控制命令退出 0 表示请求处理成功，不代表任务成功。

[完整参数](commands.md#托管命令任务v200) · [测量与验收](client-steering.md) · [English](en/execution.md)
