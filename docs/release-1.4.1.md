# v1.4.1 发布说明

本版完善离线部署说明，并同步用户确认的四卡实机验证状态。

- 两条离线客户端流程均加入 npm 离线启动变量，区分模型 API 就绪与完整聊天成功，并给出 `LOCAL_AI_OK` 冒烟命令。
- 专用 airgap 客户端节点可通过 `/etc/profile.d/local-ai.sh` 设置 PATH、交互式 Bash 补全和 npm 离线环境；个人可使用 `~/.profile`。`npm_config_offline=true` 仅用于 offline/airgap 环境，安装程序不自动持久设置。
- 提醒进入离线环境前按目标 Ubuntu 版本与 CPU 架构准备 Docker `.deb` 及系统依赖；离线准备示例以 B300/GB300 为主。
- `b200-tp4-cpu`、`b200-tp4` 和 `gb300-tp4` 已获用户确认实体机验证；`gb300-tp2` 保留且继续标注未验证。保留已有测试方法和覆盖范围，不新增性能或长期稳定性承诺。
- 程序版本、当前安装和升级示例统一为 1.4.1；包含此前 main 上的文档勘误，不移动 v1.4.0 标签。

推理参数、模型、容器镜像和客户端运行逻辑保持不变。GB300 TP4 的新增状态依据用户确认，本次未重新执行远端实机测试。此前客户端功能见 [v1.4.0 说明](release-1.4.0.md)，验证方法与限制见[验证记录](validation.md)。

获取程序见 [README](../README.md)，已有安装分别按[程序更新](update.md)更新两端；离线部署按[离线指南](offline.md)。

[English](en/release-1.4.1.md)
