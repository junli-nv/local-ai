# Deployment guide

[中文（默认）](../deployment.zh-CN.md)

Run inference on the GPU server; run OpenCode and its tools on BCM. Keep source separate from model data and user state.

## 1. Select a profile

| Profile | Server CPU | Local GPUs | Engram | Status |
|---|---|---:|---|---|
| b300-tp4 | AMD64 | 4 | GPU | B300 validated |
| gb300-tp4 | ARM64 | 4 | GPU | Experimental |
| gb300-tp2 | ARM64 | 2 | CPU | Experimental |

Check uname -m and nvidia-smi. Choose the BCM binary independently. GPUs must be visible to one OS; cross-host TP and NVL72 scheduling are not implemented. TP2 offload alone needs about 189 GiB RAM. The 256 GiB MemAvailable guard is conservative, not a measured minimum. Validate GB300 on real hardware.

## 2. Prepare the GPU server

Allocate GPUs first. Install compatible drivers, Docker API 1.49+, NVIDIA Container Toolkit and Python 3.10+. Keep source and /raid/local-ai data separate. The tool does not modify Slurm or stop other jobs.

```bash
git clone https://github.com/junli-nv/local-ai.git
cd local-ai
nvidia-smi
nvidia-ctk cdi list
./local-ai profiles
```

If CDI is missing, regenerate on this host; do not copy device definitions:

```bash
sudo systemctl restart nvidia-cdi-refresh.service
nvidia-ctk cdi list
```

Without a refresh service, follow NVIDIA's manual CDI procedure. Avoid duplicate definitions.

```bash
./local-ai image pull --profile b300-tp4 --data-dir /raid/local-ai
./local-ai model download --profile b300-tp4 --data-dir /raid/local-ai
```

Existing complete weights belong in /raid/local-ai/models/DeepSeek-V4.1-Flash/. Weights are CPU-independent; images are not.

## 3. Start and validate

```bash
./local-ai server plan --profile b300-tp4 --gpus 0,1,2,3 --name a --port 18000
./local-ai server start --profile b300-tp4 --gpus 0,1,2,3 --name a --port 18000
curl --fail http://127.0.0.1:18000/health
curl --fail http://127.0.0.1:18000/v1/models
./local-ai server status --name a
```

Use gb300-tp4 for four local GB300 GPUs or gb300-tp2 with --gpus 0,1 for two. Full UUIDs are accepted. plan does not allocate devices; start checks occupancy. Initial compilation may take minutes. Container running state is not API readiness. Full logs and launch arguments are under instances/a/ in the data directory.

## 4. Install on BCM

Run as the user who will execute tools:

```bash
git clone https://github.com/junli-nv/local-ai.git
cd local-ai
./local-ai client install
./local-ai client doctor
ssh gpu-a hostname
```

Replace gpu-a with the server. Complete SSH authentication and host-key verification first. Normal SSH checks remain enabled; root keys are not distributed. BCM needs Python, Bash, git, ssh, rg and script, but no Docker, CUDA, Node or npm. Installation checks the pinned native binary's NPM integrity.

## 5. Use from BCM

```bash
./local-ai chat --server gpu-a --project /home/alice/project
```

The client owns a loopback SSH tunnel and closes it on exit.

```bash
./local-ai chat --server gpu-a --check
```

Choose identity and API port:

```bash
./local-ai chat --server alice@gpu-a --port 18001 --project /home/alice/project
```

Run a single task:

```bash
./local-ai chat --server gpu-a --project /home/alice/project \
  --run '请用bash执行hostname，并报告实际输出。'
```

Files, git, shell and onward SSH execute on BCM with the current user's permissions. Inference runs in the GPU container. The client does not need a GPU.

## 6. Two instances and multiple users

On an eight-GPU B300 server:

```bash
./local-ai server start --profile b300-tp4 --name a --gpus 0,1,2,3 --port 18000
./local-ai server start --profile b300-tp4 --name b --gpus 4,5,6,7 --port 18001
```

Instances have separate GPUs, HBM, KV, caches, ports and logs; only read-only weights are shared. Select with chat --port. There is no load balancing.

Use separate Linux accounts and private state under ~/.local/state/local-ai/. History follows the logical service, not temporary ports. Connection configurations are independent. Root can access user files. Four active sequences per engine is a scheduling limit; additional requests queue. Measure concurrent throughput separately.

## 7. Stop and reconfigure

```bash
./local-ai server stop --name b
./local-ai server start --profile b300-tp4 --name b --gpus 4,5,6,7 --port 18001
```

To change GPUs, port or profile, inspect and stop the instance, explicitly remove its container, then recreate it. Model files and host logs remain. Automatic boot startup and returning GPUs to Slurm are not implemented.

## 8. Offline use and development

Carry source, matching server image/weights, and BCM-native assets separately. See [offline deployment](offline.md), [architecture](architecture.md), [development](development.md) and [validation](validation.md). Internal SSH may remain available. External MCP, web search and dependency downloads need separate preparation.
