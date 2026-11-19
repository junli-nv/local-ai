# v2.0.2：任务恢复与输出修复

- 读取日志失败时保留后端已确认的任务终态和退出码。
- Slurm 日志缺失时明确报告，可在日志出现后重试。重新检查 v2.0.1 遗留的错误空缓存。
- 补收终态日志前实时核验后端。后端不可验证时保留终态并返回 backend_unverified。
- 更新器帮助与错误提示使用通用标签格式 vMAJOR.MINOR.PATCH。

[执行指南](execution.md) · [English](en/release-2.0.2.md)
