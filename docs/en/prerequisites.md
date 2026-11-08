# GPU server software prerequisites

BCM clients need no Docker, containerd, CUDA or GPU. This page applies only to GPU servers.

| Component/package | Functional requirement | RTX basic-test environment |
|---|---|---|
| docker-ce | dockerd Server API >=1.49; Docker >=28.1 | 29.9.3 / API 1.56 |
| docker-ce-cli | Matching CLI with image inspect --platform | 29.9.3 |
| containerd.io | Satisfy the chosen docker-ce dependencies; no universal independent minimum | 2.4.2 |
| NVIDIA driver | Compatible with image CUDA; working host nvidia-smi | 580.95.05 |
| NVIDIA Container Toolkit | nvidia-ctk and complete selected-GPU UUID CDI aliases | 1.17.8, manually generated CDI |
| Image CUDA | Pinned image supplies CUDA; full host CUDA Toolkit unnecessary | 13.0.2 |

These versions passed eight-GPU BF16, P2P capability discovery, NCCL, model cold start, limited API smoke tests and a native-client tool round trip. Full context boundaries, sustained load and concurrency remain unvalidated. Existing B200/B300 validation is unchanged.

API 1.49 is required for platform-specific image inspection. Upgrading only the CLI or setting DOCKER_API_VERSION cannot add server features. Docker enables CDI by default since 28.3; explicitly enable and verify it on 28.1/28.2. Toolkit introduced CDI generation in 1.12 and automatic refresh in 1.18. These are feature-introduction versions, not universal validated minima. Follow README for generation; avoid duplicate definitions.

## Checks before installation

On GPU001, inspect the Server section of docker version:

```bash
docker version
docker info --format 'Server={{.ServerVersion}} Driver={{.Driver}} Root={{.DockerRootDir}}'
nvidia-smi
nvidia-ctk --version
nvidia-ctk cdi list
nvidia-smi --query-gpu=index,uuid --format=csv,noheader
```

Require a reachable local daemon, Server API >=1.49, a CDI alias for every selected GPU UUID and verified GPU access inside a container. An active daemon or working host nvidia-smi alone is insufficient.

## Ubuntu repositories

Docker's repository provides docker-ce, docker-ce-cli and containerd.io; Ubuntu's docker.io is a separate package family. Follow Docker's installation guide for conflicting packages.

```bash
apt-cache policy docker-ce docker-ce-cli containerd.io
apt-mark showhold
```

APT prioritizes pin values before versions. NVIDIA Base OS priority 600 can select older packages over Docker's priority 500. To deliberately use official Docker packages, scope an override in /etc/apt/preferences.d/docker-ce:

```text
Package: docker-ce docker-ce-cli docker-ce-rootless-extras containerd.io docker-buildx-plugin docker-compose-plugin
Pin: origin "download.docker.com"
Pin-Priority: 700
```

Keep other NVIDIA package policies, then recheck candidates and simulate:

```bash
apt-cache policy docker-ce docker-ce-cli containerd.io
apt-get -s install docker-ce docker-ce-cli containerd.io
```

Review dependencies, removals and workloads before upgrading. The project does not require the latest version of every package.

References: [Docker installation](https://docs.docker.com/engine/install/ubuntu/), [API](https://docs.docker.com/reference/api/engine/), [Docker CDI](https://docs.docker.com/reference/cli/dockerd/#configure-cdi-devices), [NVIDIA CDI](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/latest/cdi-support.html).

[中文](../prerequisites.md)
