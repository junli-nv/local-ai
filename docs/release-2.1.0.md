# v2.1.0：从客户端查看推理负载

在 BCM 上运行 `./local-ai client metrics`，即可从已配置的 vLLM 服务读取运行请求数、排队请求数和 KV 缓存池使用率。用 `--interval 2 --count 5` 连续采样，结束后可查看排队和首 token 耗时、缓存抢占与前缀 token 命中率。输出附有指标说明，默认英文，可加 `--lang zh` 切换为中文。

BCM 到 HGX260 的五次采样已验证。客户端通过现有 HTTP 指标接口读取数据，更新时无需重启推理服务。

[命令手册](commands.md#从客户端查看推理压力) · [验证记录](validation.md#v210-客户端指标采样) · [English](en/release-2.1.0.md)
