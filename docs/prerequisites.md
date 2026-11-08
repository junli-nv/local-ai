# GPU 服务端软件前提

BCM 客户端不需要 Docker、containerd、CUDA 或 GPU；本页只针对 GPU 服务端。

| 组件/包 | 功能要求 | 本次 RTX 基础测试环境 |
|---|---|---|
| docker-ce | dockerd Server API >=1.49；Docker >=28.1 | 29.9.3 / API 1.56 |
| docker-ce-cli | 配套客户端，支持 image inspect --platform | 29.9.3 |
| containerd.io | 满足所选 docker-ce 包的依赖，不规定统一最低版本 | 2.4.2 |
| NVIDIA 驱动 | 兼容镜像 CUDA，宿主机 nvidia-smi 正常 | 580.95.05 |
| NVIDIA Container Toolkit | nvidia-ctk 可生成 CDI，所选 GPU UUID 别名完整 | 1.17.8，手动生成 |
| 镜像 CUDA | 固定镜像提供，宿主机无需完整 CUDA Toolkit | 13.0.2 |

本次版本通过八卡 BF16、P2P 能力查询、NCCL、模型冷启动、有限 API 冒烟和原生客户端工具往返；完整上下文边界、长期负载及并发未验收。既有 B200/B300 验收不变。

API 1.49 要求来自 image inspect 的平台参数。仅升级 CLI 或设置 DOCKER_API_VERSION 不会增加服务端能力。Docker 28.3 起默认启用 CDI；28.1/28.2 需显式启用并验证。Toolkit 1.12 起可生成 CDI，1.18 起提供自动刷新；这是功能引入版本，不是全平台验收下限。生成步骤见 README，避免重复定义。

## 安装前检查

在 GPU001 执行，检查 docker version 的 Server 部分：

```bash
docker version
docker info --format 'Server={{.ServerVersion}} Driver={{.Driver}} Root={{.DockerRootDir}}'
nvidia-smi
nvidia-ctk --version
nvidia-ctk cdi list
nvidia-smi --query-gpu=index,uuid --format=csv,noheader
```

成功标准：可连接本机守护进程，Server API >=1.49，每个选中 GPU UUID 都有 CDI 条目，且容器实测可访问 GPU。docker active 或宿主机 nvidia-smi 正常不能替代容器验证。

## Ubuntu 软件源

官方源提供 docker-ce、docker-ce-cli、containerd.io；Ubuntu 的 docker.io 是另一种打包方式。按官方安装说明处理冲突包，不混装。

```bash
apt-cache policy docker-ce docker-ce-cli containerd.io
apt-mark showhold
```

APT 先比较 pin 优先级。NVIDIA Base OS 旧包优先级 600 会压过 Docker 官方新包的 500。确需官方包时，可只为这些包增加 /etc/apt/preferences.d/docker-ce：

```text
Package: docker-ce docker-ce-cli docker-ce-rootless-extras containerd.io docker-buildx-plugin docker-compose-plugin
Pin: origin "download.docker.com"
Pin-Priority: 700
```

保留其他 NVIDIA 包的规则，然后重新检查候选版本并模拟：

```bash
apt-cache policy docker-ce docker-ce-cli containerd.io
apt-get -s install docker-ce docker-ce-cli containerd.io
```

核对依赖、删除列表和运行任务后再升级；不要求所有包都装最新版。

参考：[Docker 安装](https://docs.docker.com/engine/install/ubuntu/)、[API](https://docs.docker.com/reference/api/engine/)、[Docker CDI](https://docs.docker.com/reference/cli/dockerd/#configure-cdi-devices)、[NVIDIA CDI](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/cdi-support.html)。

[English](en/prerequisites.md)
