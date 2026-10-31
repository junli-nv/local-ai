# 验证记录

日期：2026-10-31。公开记录不包含基础设施主机名、IP、GPU UUID、凭据及用户原始日志。

## 硬件与固定版本

- 服务端：AMD64，8 张 B300，Ubuntu 24.04，NVIDIA 驱动 580.126.20。
- 容器：Docker 29.2.1，NVIDIA Container Toolkit 1.19.1。
- 模型：DeepSeek-V4.1-Flash，修订 314113f8a7dadb388215396ba5fbee2c610a04d6。
- vLLM：0.32.0-ubuntu2404；固定清单及 AMD64/ARM64 子镜像摘要见 profiles.json。
- BCM 客户端：Linux AMD64，OpenCode 1.19.5；头节点无需 Docker、Node 或 npm。

## 项目集成验证

| 检查项 | 结果 |
|---|---|
| BCM 管理的 SSH 隧道连接已有 GPU 服务 | 通过 |
| BCM 搜索、通配、读取、编辑与独立 unittest | 通过，未修改测试内容 |
| 工具执行位置 | 确认为 BCM 主机 |
| 编辑与测试集成耗时 | 约 9.8 秒；仅单次冒烟任务，不是性能基准 |
| 使用另外 4 张本机 B300 冷启动新服务 | 通过；含首次编译约 364 秒 |
| BCM 工具访问新服务 | 通过 |
| 客户端退出后关闭隧道 | 已通过本地端口检查确认 |
| 停止临时新服务 | 通过，原服务仍健康 |
| 从 NPM 在线安装客户端 | 通过，校验注册表 SHA512 完整性及版本 |
| 新安装二进制、空私有缓存运行 grep 和 hostname | 通过 |
| 客户端导出、校验、导入 | 通过，二进制校验值一致 |
| 项目 CLI 在 Docker 无网络模式运行 | 通过 Unix 套接字桥访问本地推理，外部连接被阻止 |
| 实际按平台检查 Docker 镜像 | AMD64 上通过 |
| GB300 原生运行 | 尚未进行，相关配置仍为实验性 |

客户端网络隔离测试使用本地 Unix 套接字 API 桥，不提供通用联网能力，也不能证明断网 GB300 服务端能够全新冷启动。没有使用 ARM 模拟执行代替硬件验证。

## 解码速度参考对比

此前同一节点顺序执行流式请求：提示词长度分别为 53 和 8453 token，输出上限 128 token，temperature=1，top_p=0.95。

| 配置 | 平均解码 token/s |
|---|---:|
| 初始 TP8，eager，CPU Engram | 5.20 |
| 优化后 TP8 | 221.52 |
| 优化后 TP4 | 221.72 |

这些短输出均为推理 token。速度不含预填充，不能代表最终答案延迟或并发吞吐量。优化同时调整了 GPU Engram 放置与 CUDA Graphs，不能据此分离各项贡献。预热后，新输入、未命中缓存的约 8.5K-token 请求，首 token 时间约 0.44–0.47 秒。

## CPU 回归检查范围

覆盖架构标准化与不匹配、UUID/索引重复选择、显存检查、GB300 TP2 内存策略、无副作用规划、选中及未选中 GPU 的占用冲突、镜像身份、显式 ARM64 镜像检查、权重索引路径穿越、ELF 检查、包篡改、不安全归档成员、缓存隐私、同一用户并发配置隔离、SSH 参数校验及异常退出清理。

CI 配置覆盖 Python 3.10、3.12、3.13。远程结果须以工作流实际运行结果为准，本地测试、静态检查和构建成功不等于远程 CI 已通过。

## 尚需完成的验收

- GB300 原生 TP2、TP4 冷启动、内存、工具与性能验证。
- ARM64 BCM 客户端原生验证，与服务端架构分别检查。
- 另一台全新主机上的离线服务端部署，以及跨 Docker 版本、存储后端的大镜像导出导入往返验证。
- 两个副本长期运行与多用户并发、性能评估。

## 原始参考资料

- [vLLM 模型部署方案](https://recipes.vllm.ai/deepseek-ai/DeepSeek-V4.1-Flash)：配置来源，包含 GB300 TP2 卸载方案。
- [NVIDIA CDI](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/cdi-support.html)：原生设备选择。
- Docker [镜像平台检查](https://docs.docker.com/reference/cli/docker/image/inspect/)、[导出](https://docs.docker.com/reference/cli/docker/image/save/)与[导入](https://docs.docker.com/reference/cli/docker/image/load/)。
- [OpenCode 配置](https://opencode.ai/docs/config/)。

集成验证原始证据由操作人员保存在被忽略的运行目录中，不属于公开仓库材料。

---

[English version](en/validation.md)
