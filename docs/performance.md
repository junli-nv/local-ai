# 推理优化与引擎探索记录

本页保存 2026-11-01 的优化思路、参数依据、试验中的问题和后续工作。面向接手开发者；实际操作统一见[部署指南](deployment.zh-CN.md#单用户-dspark-与显式预热)，数字、版本及验收边界统一见[验证记录](validation.md)。SGLang 目前是探索对象，未纳入安装与实例管理。

## 先判断慢在哪一段

将权重加载、启动编译、API 健康、首次请求编译、预填充、解码与排队分开。TTFT 必须说明真实输入 token、是否命中前缀缓存、并发和是否包含首个 reasoning token。解码 token/s 不能代替 TTFT，也不能把 reasoning 首输出当成最终答案。

早期从 TP8/eager/CPU Engram 调整到 GPU Engram 与 CUDA Graph 的组合配置，再比较 TP4。它支持当前 TP4 基线的选择，但多项参数同时变化，不能单独归因于 TP 数或某一种优化。原始测量范围见验证记录；默认 b300-tp4 继续保留。

## RTX 6000D 的适用边界

独立 `rtx6000d-tp8` 使用 CPU Engram、eager、32K、单序列和纯文本；没有启用下文 B300 的 DSpark/CUDA Graph 优化。RTX 实机冒烟、单次延迟与未验收项见 [RTX 6000D](rtx6000d.md)，不能据此推断与 B200/B300 的吞吐差距或性能排名。

## 本次 vLLM DSpark 如何调整

配置落在 [profiles.json](../src/local_ai/profiles.json) 的独立 b300-tp4-dspark，而非修改默认模型参数。模型 revision、镜像、TP4、GPU Engram、FP8 KV、131072 上下文、四个活动序列及 8192 批处理 token 维持基线。

| 调整 | 本次值 | 原因与后续检查 |
|---|---|---|
| 投机解码 | method=dspark，num_speculative_tokens=5 | 提高单请求解码速度；修改草稿长度后重新测接受率、显存及并发吞吐 |
| 草稿与验证 | draft_sample_method=probabilistic，rejection_sample_method=block | 使用真实目标模型验证，不用 synthetic acceptance 冒充性能 |
| 自适应验证 | enable_adaptive_verification=false | 固定本次已测配置；后续单独对照 |
| 图捕获 | mode=0，FULL_DECODE_ONLY，尺寸 6/12/24 | 与本次五 token 草稿和活动序列配置一起验收；不能照抄基线的 1/2/4，也不能当作任意新版本的最优值 |
| 编译缓存 | TILELANG_CACHE_DIR=/root/.cache/tilelang；CUDA_CACHE_PATH=/root/.cache/nvidia | 落入已有的实例 cache 挂载，供后续启动复用；不改变基线实例身份 |

选择 DSpark 的依据是单请求生成改善，同时保留并发吞吐下降的结果。没有降低模型推理预算来冒充运行时加速，也没有证明 TTFT 会同步降低。四组配置对比、接受率和功能检查集中在验证记录。

## 首次编译尖峰如何处理

1. **定位真实编译。** 从运行日志观察到 CuTeDSL MXFP8QuantizeSwizzledKernel 与 Triton _block_scores_kernel 推理期 JIT。服务 /health 成功不等于业务形状都已编译。
2. **检查缓存实际位置。** 镜像中的 TileLang 默认目录为 ~/.tilelang/cache，不在现有 /root/.cache 挂载内。只挂载后者仍可能在容器重建后丢失这部分缓存。因此仅在新配方显式设置缓存目录；缓存复用依赖引擎、架构和参数，不保证完全免编译。
3. **增加显式推理预热。** [warmup.py](../src/local_ai/warmup.py) 使用 /tokenize 取得 token ID，再向 /v1/completions 发指定长度的真实请求。校验 API 返回的输入/输出数量，避免名义 8K 实为 9K。不同请求前缀降低前缀缓存干扰。
4. **覆盖多种形状。** 默认输入 1024/8192/32768、输出 256、并发 1/2/4/8，各两遍；上下文较小时自动缩减。八并发包含四活动序列之外的排队。两遍不是“完全预热”的数学保证；新输入或批次仍可能 JIT。
5. **让状态可核对。** READY 只看 API；WARMING、WARMUP COMPLETE、WARMUP INCOMPLETE 写终端与实例日志。warmup.json 绑定配置摘要与容器 StartedAt；重启后 stale。状态查询不生成请求，预热超时或中断保留容器。
6. **区分迁移与本机缓存。** 离线包不携带实例缓存与完成记录；目标 GPU 安装后重新显式预热，不把来源机器的完成状态当成目标机已编译。

相关实现为 [cli.py](../src/local_ai/cli.py)、[server.py](../src/local_ai/server.py)、[readiness.py](../src/local_ai/readiness.py) 与 [installlog.py](../src/local_ai/installlog.py)。[预热回归](../tests/test_warmup.py)覆盖真实 HTTP 形状、失败、取消、并发锁和重启失效。

## SGLang 探索了什么

比较四组：vLLM 基线、vLLM DSpark、SGLang 基线、SGLang DSpark，使用同一组已分配 GPU、相同权重和相同请求。vLLM 未开启 EP；SGLang 按其配置启用 EP4。这是配置对照，不是严格分离每项框架机制的实验。

本次 SGLang 为 0.0.0.dev1+gda64c5cbb，Torch 为 2.13.0+cu130。固定 AMD64 镜像为 lmsysorg/sglang@sha256:4a5d132a06a77c8331e15845f2e925adc788b00105097ad55409afa3f4fa4860。它是当时的开发镜像，不是未来安装的默认版本。

| SGLang 参数 | 本次值 |
|---|---|
| --tp / --ep-size | 4 / 4 |
| --context-length / --max-running-requests | 131072 / 4 |
| --chunked-prefill-size / --mem-fraction-static | 8192 / 0.8 |
| --kv-cache-dtype | fp8_e4m3 |
| --cuda-graph-max-bs-decode | 4 |
| --reasoning-parser / --tool-call-parser | auto / auto |
| --disable-flashinfer-autotune | 开启此开关 |
| SGLANG_DEFAULT_THINKING | 1 |
| DSpark 组额外参数 | --speculative-algorithm DSPARK，--speculative-dspark-block-size 5 |

实际入口为 python3 -m sglang.launch_server，包含 --trust-remote-code；权重只读挂载，两组使用固定相同镜像。原始启动参数、流式请求、指标和基础功能检查已保存于内部实验目录，公开仓库保留脱敏结果。不能把这张参数表直接视为 local-ai 已支持 SGLang。

探索中观察到较长的 MHC/TileLang 编译与图捕获。两组顺序运行并复用部分磁盘缓存，因此没有拿启动时间作公平的引擎排名；挂载 /root/.cache 也不能证明 ~/.tilelang 被保留。容器停止阶段的 SystemExit: 0、CancelledError 与请求期间错误分开统计。

SGLang 在短输入八并发吞吐上也有优势，数值及 vLLM JIT 干扰已保留在验证记录，值得后续做更长稳态实验；不能只记录不采用它的理由。

本次负载下 vLLM 更适合当前项目，故保留一个生产引擎和一个可选 DSpark 配方。没有测试 Dynamo 路由或分离式 prefill/decode，也没有全面调优 SGLang；不能据此断言 SGLang、Dynamo 或其他模型普遍更慢。

## 后续开发如何复测

- 记录源码提交、镜像摘要、包版本、模型 revision/配置哈希和完整引擎参数。确认 GPU 分配，使用独立实例、端口和缓存，保留原服务。原始基础设施日志不进 Git。
- 引擎对照使用相同请求载荷哈希、实际 token 数、采样参数与输出上限。分别记录冷请求、已准备形状、前缀缓存命中、1/4/8 并发和错误数；包含尖峰，不挑最快值。
- 预热对照另用两套冷缓存：同一 DSpark 配方，一组只等 API，另一组通过原生 start --warmup 后测相同流式请求。再重启同一实例检查磁盘缓存复用，并确认 warmup 状态变 stale。非流式预热不能替代流式测量。
- 比较单请求 TTFT、解码速度、端到端耗时和并发总吞吐；少量样本的最高值或 P95 不作生产 SLA。功能检查进一步扩展到完整回答、真实工具往返和复杂代码任务。
- 若升级 SGLang，重新核实公开参数、图捕获、EP/TP、KV 格式和 DeepSeek 解析器。先做独立适配与离线材料验收，再考虑引擎抽象；不能直接把 vLLM 参数透传给它。
- 若调整 DSpark 草稿长度、图捕获、序列数或推理预算，每次只改变明确因素；保留旧配置及实测回退点。回退按部署指南显式重建为 b300-tp4，不自动停止业务实例。
- 本次还复现了停止 HTTP 服务后 TIME_WAIT 被误报为端口占用：预检增加 SO_REUSEADDR，仍拒绝活跃监听。真实 TCP 回归位于 [test_listen.py](../tests/test_listen.py)，不能为通过测试跳过端口保护。

---

[English version](en/performance.md)
