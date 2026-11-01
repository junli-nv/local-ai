# local-ai

[中文（默认）](README.md)

Run vLLM on the GPU server and OpenCode on BCM. File, shell, Git and SSH tools execute on BCM as the current user.

Source is delivered from main without stable tags. ./local-ai --version reports the source version; see [validation](docs/en/validation.md) for acceptance scope.

## Example conventions and documentation

| Object | Meaning |
|---|---|
| GPU001 | Eight-card B300 server; main workflow uses GPUs 0–3 |
| bcm-headnode / alice | BCM host and client user |
| /raid/local-ai | Each host's installation root: the extracted directory |
| /home/alice/project | BCM task directory |
| a / 18000 | Main instance and API port |
| http://GPU001:18000/v1 | Model address; substitute a reachable hostname/IP |

Use appropriate sudo/Docker permissions; root may omit sudo. Data defaults follow the launcher directory. These examples set neither LOCAL_AI_DATA_DIR nor --data-dir.

| Document | Purpose |
|---|---|
| This page | First online installation, startup, chat and export |
| [Deployment](docs/en/deployment.md) | CDI, storage recovery, instance replacement and multiple instances/users |
| [Command manual](docs/en/commands.md) | Options, defaults, exit codes, session resume and client versions |
| [Offline deployment](docs/en/offline.md) | Existing-installation migration or online preparation |
| [Architecture](docs/en/architecture.md), [development](docs/en/development.md) | Design, extension and contributor handoff |

## Prerequisites

GPU001: Linux, Python 3.10+, Bash, curl, tar, compatible NVIDIA driver, CDI-capable Docker API 1.49+, and NVIDIA Container Toolkit. Obtain GPU allocation and sufficient resources.

BCM: Linux AMD64/ARM64, Python 3.10+, Bash, curl, tar, Git, rg, util-linux script and access to GPU001:18000. No GPU, CUDA, Docker, Node.js or npm is needed. SSH tool tasks require OpenSSH.

| Profile | Server CPU / image | Local GPUs | Engram | Validation |
|---|---|---|---|---|
| b300-tp4 | AMD64 / linux/amd64 | 4 B300 | GPU | Hardware validated |
| gb300-tp4 | ARM64 / linux/arm64 | 4 GB300/B300 | GPU | Not hardware validated |
| gb300-tp2 | ARM64 / linux/arm64 | 2 GB300/B300 | CPU | Upstream recipe, unvalidated |

BCM architecture is independent. Profiles use GPUs visible to one OS. GB300 TP2 checks at least 256 GiB MemAvailable; B300 acceptance does not cover GB300.

Validated baseline: Ubuntu 24.04, driver 580.126.20, Docker 29.2.1, Toolkit 1.19.1. DeepSeek-V4.1-Flash weights occupy about 510 GB; allow additional images, caches and a complete dist/ copy. Model/revision configuration is covered in [development](docs/en/development.md#model-and-client-compatibility).

## 1. Install and start on GPU001

Download into an empty directory and check Docker, GPUs and CDI:

```bash
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
curl -fL --retry 3 https://github.com/junli-nv/local-ai/archive/refs/heads/main.tar.gz -o /tmp/local-ai-source.tar.gz
tar -xzf /tmp/local-ai-source.tar.gz --strip-components=1 -C /raid/local-ai
cd /raid/local-ai
./local-ai --version
./local-ai profiles
docker version
docker info --format 'Server={{.ServerVersion}} Driver={{.Driver}} Root={{.DockerRootDir}}'
nvidia-smi
nvidia-ctk cdi list
```

Docker must reach its server. CDI must list selected GPUs' nvidia.com/gpu=GPU-... UUID aliases; see [CDI setup](docs/en/deployment.md#cdi-setup) when absent.

Initial inspect No such image is expected. A pull error involving metadata.db requires [storage recovery](docs/en/deployment.md#docker-storage-failures). Docker active does not prove storage health. --data-dir does not move Docker/containerd databases; never share active databases across nodes.

After preflight:

```bash
./local-ai install --role server --profile b300-tp4
./local-ai server plan --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000
./local-ai server start --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000
./local-ai server status --name a
```

install saves the profile and reuses complete assets without starting GPUs. plan produces a plan; start checks live occupancy without terminating other tasks.

start waits up to 600 seconds, showing NOT READY/log paths during loading and compilation. A running container and /health HTTP 200 produce READY in terminal/runtime logs. status checks current readiness: exit 0 when ready, exit 1 with a reason otherwise.

| Evidence | GPU001 location / command |
|---|---|
| Installation/download/export/management | /raid/local-ai/install.log |
| Weights/compilation/warmup/READY | /raid/local-ai/instances/a/server.log |
| Live progress | tail -f /raid/local-ai/instances/a/server.log |
| Current status | ./local-ai server status --name a |

Add --wait-timeout 1200 for longer startup. Timeout exits 1; Ctrl+C returns 130; both retain the container. Check logs/status first. A historical READY, running container or listening port alone is insufficient.

--host 0.0.0.0 listens on all IPv4 interfaces; default is 127.0.0.1. BCM uses the host address, never 0.0.0.0. API keys/HTTPS are not configured; restrict network access. Address changes require [instance replacement](docs/en/deployment.md#replace-an-instance).

## 2. Install and use on BCM

Log in as alice on bcm-headnode and use BCM's own empty directory:

```bash
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
curl -fL --retry 3 https://github.com/junli-nv/local-ai/archive/refs/heads/main.tar.gz -o /tmp/local-ai-source.tar.gz
tar -xzf /tmp/local-ai-source.tar.gz --strip-components=1 -C /raid/local-ai
cd /raid/local-ai
./local-ai install --role client --endpoint http://GPU001:18000/v1
mkdir -p /home/alice/project
```

install saved the endpoint. Subsequent chat commands may omit it. Substitute the actual project directory.

```bash
# API/model check without generation
./local-ai chat --check
# Interactive chat
./local-ai chat --project /home/alice/project
# One task, then exit; hostname should return the BCM hostname
./local-ai chat --project /home/alice/project --run 'Use bash to run hostname and report its actual output.'
```

All three commands use GPU001:18000. chat --endpoint URL overrides one invocation without changing the saved address. Another port is introduced only for a [second instance](docs/en/deployment.md#two-instances-and-multiple-users).

Resume with opencode -s ses_.... The first chat creates ~/.local/bin/opencode and reports PATH/name conflicts. chat --session ID and chat --continue are alternatives. Mouse capture/clipboard bindings are disabled by default; use terminal copying/pasting and keyboard navigation. See [session resume and terminal copying](docs/en/commands.md#resume-and-terminal-clipboard).

Tasks include hardware troubleshooting, scripts, services and Slurm/Kubernetes jobs. SSH queries use current-user permissions, independently of inference profiles. Rules are in [AGENTS.md](AGENTS.md); the no-probing constraint applies only to pure server plan --inventory.

## 3. Export and migrate

From an installed directory:

```bash
cd /raid/local-ai
./local-ai export
ls -lh dist/local-ai.tar dist/local-ai.tar.sha256
```

Export carries prepared source, models, Docker image archives, public clients and recipes. A server-only installation does not include an unprepared BCM client. To prepare both roles online, use install --role both; see [offline deployment](docs/en/offline.md).

Carry both dist/ files, verify, extract into an empty directory and run install --offline. Rename the directory if desired. dist/ itself, old instances, logs, histories and credentials are excluded. Configure local GPUs, ports and endpoints again. Both complete routes are in the [offline guide](docs/en/offline.md).

Program: local-ai, src/, docs/. Public assets: models/, images/, clients/. Docker live storage is host-managed. Private state remains ~/.local/state/local-ai/ or XDG_STATE_HOME/local-ai/.

Development checks and documentation requirements are in the [development guide](docs/en/development.md).
