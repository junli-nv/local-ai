# 长命令托管、插话与暂停/停止

这是 v1.4.4 标签之后开发主线的新能力，原 v1.4.4 下载包不包含。更新客户端程序后退出并恢复聊天，新启动的 OpenCode 会加载 local_ai_task；不需要重启模型服务器。保留已验收 OpenCode 1.19.5。

## 最简单的用法

在聊天里说：“把这条长命令作为后台任务执行，告诉我任务 ID，然后继续回答我的问题。”助手应使用 local_ai_task start，立即返回 job_ 开头的 ID。任务执行中可以继续提问，也可说“暂停当前会话的任务”“恢复”“停止当前会话的任务”。权限仍由原生客户端和账户控制；模型是否正确选择工具与理解要求需实际确认。

也可以在 BCM 上直接使用终端，不依赖模型：

```bash
cd /home/alice/project
/raid/local-ai/local-ai client job start --command 'sleep 30; echo done'
/raid/local-ai/local-ai client job list
```

把以下 JOB_ID 换成返回的 job_ 标识：

```bash
/raid/local-ai/local-ai client job status JOB_ID
/raid/local-ai/local-ai client job pause JOB_ID
/raid/local-ai/local-ai client job resume JOB_ID
/raid/local-ai/local-ai client job stop JOB_ID
/raid/local-ai/local-ai client job output JOB_ID
```

start 表示已提交，不能当作完成。pause/stop 返回 control_requested 也不是已经暂停/退出；随后查看 status，分别确认 paused 或 terminal=true。停止先发送 TERM，并唤醒暂停进程以便退出，一秒后仍未退出则 KILL；只对核实身份的自有进程组操作。

会话级控制需要准确的 OpenCode ses_ 标识和原项目路径；两者可从 job list 返回值查到。CLI 自己创建的任务默认 session=cli：

```bash
/raid/local-ai/local-ai client job pause-session --session SES_ID --project /home/alice/project
/raid/local-ai/local-ai client job resume-session --session SES_ID --project /home/alice/project
/raid/local-ai/local-ai client job stop-session --session SES_ID --project /home/alice/project
```

pause-session 关闭该会话的新工具入口，并请求暂停其托管任务；resume-session 显式放行，只恢复因会话暂停的任务，单独暂停的任务需单独恢复。stop-session 停止该会话自有任务且保持入口关闭，继续工作前必须显式 resume-session。暂停不撤销已经完成的写入，也不会撤回已发出的模型请求。已进入执行中的普通原生工具不能追溯托管。

## 后台与恢复的边界

- 任务是本机非交互命令，stdin 为空，无 PTY。可脱离终端和 OpenCode 生命周期；重新打开聊天后用 list/status/output 接续查看。程序升级时每个任务使用自己的 worker 副本。
- 不把已运行的普通 Bash 或 TUI 自动移入后台；普通同步 Bash 仍可能让新消息等到命令返回。即时插话能力适用于长命令走 local_ai_task、主会话没有被其他同步工具阻塞的路径。
- 没有自动唤醒模型或定时发送完成通知。助手返回任务 ID 后保持可对话，用户或后续工具调用查询结果；不要用紧密轮询占住会话。
- 只管理当前用户、本机自有进程组及继承该组的子进程。不保证终止主动 setsid/守护化的后代、远端 SSH 已提交作业、Slurm 或容器内部作业；这些需要专门的执行适配和取消接口。
- 机器重启、worker 异常退出不自动重放。orphaned 表示 worker 丢失且命令可能仍运行，应检查或请求身份核验后的 stop；lost 表示已无存活组成员但最终结果/输出不完整，不能报成功。
- 多个任务指向不明时应先明确目标。自然语言指令由模型选择工具；要求直接控制时使用 CLI。这里没有加入操作系统沙箱。

## 状态、输出和隐私

状态和日志位于当前用户私有状态根的 execution/，默认 ~/.local/state/local-ai/execution；不以 endpoint 分目录，按项目真实路径与会话标识绑定，目录 0700。工具拒绝跨会话/项目管理；当前用户可通过 CLI 明确 job ID 管理自己的任务。不是跨用户或跨 BCM 同步。

start 必须使用稳定 request_id；同一会话/项目重复提交同一操作返回原任务，参数不同则拒绝。CLI 默认每次生成新键，重试需要显式 --request-id。终态任务可 remove，删除日志和 worker，但保留防重放键；有意重新执行必须用新键。

output 的 offset/next_offset 按字节计，默认每页 16384、范围 1..65536。继续传回 next_offset，直到终态且 all_output_delivered=true。text 是便于阅读的 UTF-8 预览，跨页字符可能被替换；data_base64 可精确还原原始字节。truncated=true 必须说明缺口，不能将剩余输出当作完整结果。

默认每任务超时 3600 秒，含暂停时间，最大 604800 秒；每个状态根最多 32 个未结束任务，每任务最多保留 64 MiB 合并 stdout/stderr，超限停止并标记 output_limit/truncated，不能报成功。终态还包括 completed、failed、cancelled、timed_out、lost；业务退出码在 exit_code 中。诊断 tasks/report 仍只是运行记录，与 client job 分开。

命令、参数与输出可能包含敏感信息，仅留在用户私有目录；公共离线导出不包含这些记录。执行仍请求原生 Bash 权限，外部目录仍请求 external_directory 权限；Bash 明确拒绝时不会借新工具执行。

[完整参数与退出码](commands.md#托管命令任务开发主线) · [测量与复现](client-steering.md) · [English](en/execution.md)
