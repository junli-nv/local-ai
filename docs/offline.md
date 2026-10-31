# 离线部署

分别准备三类材料：项目源码、GPU 服务端镜像与权重、BCM 原生客户端。GB300 服务端通常使用 ARM64 镜像，但 BCM 客户端仍可能是 AMD64；必须分别判断。

目标系统须预装兼容的 GPU 驱动，以及服务端的 Docker、CDI、NVIDIA Container Toolkit。BCM 需要 Python、Bash、git、SSH、rg 和 script。vLLM 镜像不包含宿主机驱动和系统依赖，应按目标发行版及内核准备离线安装包。ELF 架构匹配也不等于完整 ABI 兼容。

## 1. 打包源码

在已审查的提交上执行：

```bash
mkdir -p dist
git archive --format=tar.gz --output=dist/local-ai-source.tar.gz HEAD
cd dist
sha256sum local-ai-source.tar.gz > local-ai-source.tar.gz.sha256
cd ..
```

不要直接打包整个工作目录，其中可能含被忽略的原始日志和个人状态。源码包不包含约 510 GB 的模型权重或原生二进制文件。

## 2. 准备 GPU 镜像和权重

在联网的 Docker 准备机上执行：

```bash
./local-ai image pull --profile b300-tp4 --data-dir /data/local-ai
./local-ai image export --profile b300-tp4 --data-dir /data/local-ai \
  --output /data/export/vllm-amd64.tar
```

GB300 改用 gb300-tp4 或 gb300-tp2，并使用独立的 vllm-arm64.tar。拉取、检查和导出均显式指定平台；AMD64 准备机打包 ARM64 镜像无需执行 ARM64 代码。跨平台镜像操作要求 Docker API 1.49+，已验证基线为 Docker 29。

导出时生成配套 `.lock.json`，记录归档 SHA256 和选定镜像的配置、层指纹。归档与锁文件须一起携带，不允许只凭可变标签回退。

使用与准备机 CPU 相符的配置下载权重：

```bash
./local-ai model download --profile b300-tp4 --data-dir /data/local-ai
rsync -a /data/local-ai/models/ /data/export/models/
cd /data/export
find models -type f -print0 | sort -z | xargs -0 sha256sum > MODELS.sha256
```

权重不依赖 CPU 架构，必须完整复制配置、分词器、索引及全部分片；同一份权重可供两个实例使用。

离线 GPU 节点解压源码、校验并复制权重，必要时重新生成本机 CDI，然后导入和启动：

```bash
cd /media/export
sha256sum -c MODELS.sha256
sudo mkdir -p /raid/local-ai/models
sudo rsync -a models/ /raid/local-ai/models/
cd /path/to/local-ai
./local-ai image import --profile b300-tp4 --data-dir /raid/local-ai \
  --archive /media/export/vllm-amd64.tar \
  --lock /media/export/vllm-amd64.tar.lock.json
./local-ai server start --profile b300-tp4 --gpus 0,1,2,3 --name a
curl --fail http://127.0.0.1:18000/health
```

GB300 使用对应 ARM64 归档和配置。Docker 导入后的镜像身份表示可能不同，但配置、层内容和平台必须一致。CUDA 内核缓存不保证跨机器可用，首次启动可能使用固定镜像在本机编译。

## 3. 准备 BCM 客户端

在与目标 CPU 相同、Linux 环境兼容的联网头节点执行：

```bash
./local-ai client install
./local-ai client doctor
./local-ai client export --output /data/export/client-amd64.tar.gz
```

导出包包含 `client/bin/opencode`、公共 `seed-cache` 和材料清单，不包含历史记录、认证数据库或 SSH 密钥。缓存中的可执行文件也须匹配目标架构。

离线 BCM 上执行：

```bash
cd /media/export
sha256sum -c client-amd64.tar.gz.sha256
mkdir -p client-unpacked
tar -xzf client-amd64.tar.gz -C client-unpacked
cd /path/to/local-ai
./local-ai client install \
  --binary /media/export/client-unpacked/client/bin/opencode \
  --seed-cache /media/export/client-unpacked/client/seed-cache
./local-ai client doctor
./local-ai chat --server gpu-a --check
./local-ai chat --server gpu-a --run 'Use bash to run hostname and report the result.'
```

BCM 不需要 Node、npm 或 Docker。在已校验归档之外单独导入二进制时，使用清单中的校验值指定 `--sha256`。客户端升级或插件变更后，应重新验证无外网运行。

## 4. 验收

断开外网、保留内部 SSH 后，逐项检查：

1. 仅使用本地完整权重和镜像冷启动，确认 API 就绪。
2. 使用新用户启动客户端，不能只验证管理员已预热的环境。
3. 验证搜索、读取、编辑和测试工具，确认 hostname 返回 BCM 主机名。
4. 检查完整私有日志、GPU UUID、显存和遗留隧道。
5. 测试实际输入长度及并发，不能将解码速度直接视为整体性能。

服务端启用 HF/Transformers 离线标志；客户端禁用更新、模型目录获取、默认外部插件和 LSP 下载。显式配置的项目插件、外部 MCP、搜索及 git/pip/npm/apt 下载仍可能需要外网，须预先准备项目依赖和工具。

实际验证范围见[验证记录](validation.md)。客户端网络隔离测试不能证明另一平台的全新 GPU 服务端可以离线冷启动。

---

[English version](en/offline.md)
