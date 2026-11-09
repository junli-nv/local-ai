# GB200 四卡候选与 Rubin 单节点框架

离线介质可在其他 CPU 架构的准备机上使用 prepare --profile gb200-tp4 准备；模型共用固定 revision，镜像按 ARM64 选择。完整步骤见[联网准备](offline.md#场景二从联网环境下载并准备)。这不扩大 GB200 的实机验收范围。

v1.3.4 包含 GB200 四卡候选和 Rubin 两卡框架。当前没有这两类硬件，以下只代表
配置、纯计划和拒绝条件可由 CPU 测试检查，不代表模型能启动或性能已验收。
GPU001 指未来的目标 GPU 主机；BCM 客户端继续通过 API endpoint 连接，架构独立选择。
本功能仅处理一个 OS 可见的 GPU，不管理整柜或跨节点张量并行。

## GB200 四卡实验配方

`gb200-tp4` 要求 ARM64、恰好四张本地 GB200/B200、每卡至少 180000 MiB。
该显存值是暂定保护值，沿用 B200 容量级别，不是实测最低要求。GPU 名称包含 B200
是为了兼容实际设备报告；同时检查 CPU 架构、卡数、UUID 唯一性和每卡显存。

沿用当前固定 DeepSeek-V4.1-Flash revision 和 B200 TP4 引擎基线：GPU Engram、131072
上下文、四个活动序列、FP8 KV 与原 CUDA Graph 配置；没有新增 DSpark。ARM64 镜像使用
现有多架构固定清单，独立平台摘要为
`sha256:b1bea6490db94268e68577929ae4b800a662b91a3cd4a1fcba81cfb3946ddcff`。
2026-11-09 从公开镜像仓库核对到 Linux ARM64 和 CUDA 13.0.2；这不证明镜像内所有
DeepSeek 内核都能在 GB200 工作，也不证明目标驱动、内存、完整上下文或并发可用。

在开发机的当前源码目录执行，无需 GPU、Docker、模型或联网：

```bash
./local-ai server plan --profile gb200-tp4 --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000 --inventory tests/fixtures/gb200-tp4.json --data-dir /tmp/local-ai-gb200-plan
```

成功退出 0，输出 `deployable=true` 和 ARM64 Docker 命令；不创建数据目录。
这里 deployable 只表示配方材料已填写，可生成启动命令；不表示硬件验收或资源已分配。
测试清单明确为 synthetic，GPU 名称、编号、UUID、PCI 和显存都是示例，不能当作实测。
本次仅增加四卡配方，没有 GB200 TP2。

## Rubin 仅规划框架

`rubin-tp2-framework` 按单 OS ARM64、两张 Rubin/VR200 和 CPU Engram 卸载建立候选。
官方规格为每卡 288GB HBM4，两卡标称合计 576GB；这不等于模型可用显存。当前权重约
510GB，磁盘权重大小也不等于运行时显存占用；按 0.80 预算粗算只有约 460.8GB，
还要留 KV cache、通信和内核工作区，因此优先采用 Engram 卸载思路。CPU Engram 约
189 GiB 来自现有 GB300 TP2 配方估算；主存暂定保护值为 256 GiB MemAvailable，
仍需加载和 OS 余量，不能据此承诺两卡启动或完整上下文。标称 GB 与设备报告 MiB
不能直接混作实际可用容量。
Vera Rubin NVL72 是系统形态；实际可见卡数仍以 OS 为准，不把机柜名称解释成可用 72 卡。
镜像、平台摘要和最低显存均为 null，`planning_only=true`，没有可执行的引擎参数。

```bash
./local-ai server plan --profile rubin-tp2-framework --host 0.0.0.0 --gpus 0,1 --name a --port 18000 --inventory tests/fixtures/rubin-tp2.json --data-dir /tmp/local-ai-rubin-plan
```

成功生成框架计划时退出 0，返回 `deployable=false`、`blockers`、`command=null` 和
`spec.args=null`；仍检查 CPU 架构、卡数、重复 UUID 和 GPU 名称，但不检查未知的显存
容量门槛或引擎兼容性。该模拟清单中的显存值也不是要求或实测值。

选择此框架执行 install 的 server/both 角色、server start、image pull/export/import、
model download 或完整 export 时，退出 1 并说明 not deployable；在日志、GPU/Docker
探测、下载或资源写入之前拒绝。Python 操作入口也有同样约束。单独清除 planning_only
仍会被缺失字段拒绝；单独填入镜像也不能解除框架标记。普通源码/客户端导出仍可携带
框架定义，只是不能选择它作为已准备好的服务端资源。

## 获得硬件后的验收顺序

先取得设备与端口分配，在 GPU001 的独立目录准备当前源码，保留既有服务和配置。
GB200 可从下面的只读查询开始；Rubin 同样先核对真实环境，不先解除部署限制：

```bash
cd /raid/local-ai
./local-ai server inventory
nvidia-smi
nvidia-smi topo -m
nvidia-ctk cdi list
```

1. 保存脱敏 CPU/OS、GPU 名称与计算能力、驱动、显存、主存和 NUMA 拓扑；确认所选 GPU 在
   同一 OS 可见（GB200 四卡、Rubin 两卡），所选 CDI UUID 完整且设备与端口空闲。
2. 在独立容器中验收 CUDA、BF16 和所选卡数的 NCCL；记录完整镜像和平台摘要，以及 CUDA、
   PyTorch、vLLM、FlashInfer、Triton、DeepGEMM/CUTLASS、NCCL 版本。
3. GB200 按真实容量检查上述候选，先验证启动与有限输入，再逐步验证上下文、并发和
   图捕获。Rubin 在完整外部 catalog 中建立独立模型/硬件配方，核实镜像和显存门槛、
   模型内核与客户端能力后再显式解除 planning_only，不能直接借用 GB300 镜像摘要。
4. 验收模型加载、健康、中文流式、思考字段、工具调用与结果往返，并在 BCM 实际执行
   hostname、文件编辑和回读。API READY 不能代替这些检查。
5. 记录失败、未覆盖范围和回退方法，再逐项提高验证等级；性能、完整上下文、并发、
   DSpark 和长期稳定性分别验收。本次 CPU 检查不承诺这些能力。

Rubin 上游构建目前有 CUDA 13.4、专用 Triton 和 NCCL 的适配要求；同模型旧依赖组合也
有 DeepGEMM/CUTLASS 断言报告，必须核对修复提交与实际镜像，不能凭平台名称判断兼容。
参考：[vLLM 构建说明](https://github.com/vllm-project/vllm/blob/main/docs/getting_started/installation/gpu.cuda.inc.md)、
[DeepGEMM 问题记录](https://github.com/deepseek-ai/DeepGEMM/issues/461)、
[Rubin 参考托盘](https://docs.nvidia.com/dgx/dgxvr-user-guide/hardware.html)。
288GB HBM4 的来源为 [NVIDIA Vera Rubin NVL72 官方规格](https://www.nvidia.com/en-us/data-center/vera-rubin-nvl72/)。

外部配方是完整替代，更新现有安装后如看不到新候选，按[开发指南](development.md#模型与客户端兼容性)
合并配置。离线包材料范围与真实 GPU 验收仍按[离线指南](offline.md)和[验证记录](validation.md)。

---

[English version](en/gb200-rubin.md)
