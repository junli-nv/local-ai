# v2.1.0: Check inference load from the client

Run `./local-ai client metrics` on BCM to see running requests, queued requests and KV cache usage for the configured vLLM service. Use `--interval 2 --count 5` to sample repeatedly and summarize queue time, time to first token, cache preemptions and the prefix token hit rate. The output explains the metrics and defaults to English. Use `--lang zh` for Chinese.

Five scrapes from BCM to HGX260 were verified. The client reads the existing HTTP metrics endpoint, so the inference service needs no restart for this update.

[Command reference](commands.md#check-inference-load-from-the-client) · [Validation](validation.md#v210-client-metrics-sampling) · [中文](../release-2.1.0.md)
