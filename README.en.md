# local-ai

[中文（默认）](README.md)

Run vLLM on the GPU server and OpenCode on BCM. File, shell, Git and SSH tools execute on BCM as the current user.

The current version is v1.3.3. Examples download complete source from this tag; ./local-ai --version should report 1.3.3. See [validation](docs/en/validation.md) for acceptance scope and unvalidated platforms.

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
| This page | First online installation, startup, chat, configuration and migration links |
| [Deployment](docs/en/deployment.md) | CDI, storage recovery, instance replacement, DSpark/warmup and multiple instances |
| [Command manual](docs/en/commands.md) | Options, defaults, exit codes, session resume and client versions |
| [Offline deployment](docs/en/offline.md) | Existing-installation migration or online preparation |
| [Architecture](docs/en/architecture.md), [development](docs/en/development.md) | Design, extension and contributor handoff |

The [optimization and engine exploration record](docs/en/performance.md) preserves DSpark parameter choices, first-use compilation work, SGLang experiments and future comparison methods.

v1.3.2 includes rich-document reading during ordinary chat. Read PDF, images, Word, Excel and PowerPoint by naming their directory during chat. Upgrade steps and optional client-side converters: [document guide](docs/en/documents.md).

## Prerequisites

See [server software prerequisites](docs/en/prerequisites.md) for Docker CE, containerd, driver and CDI requirements and checks.

GPU001: Linux, Python 3.10+, Bash, curl, tar, compatible NVIDIA driver, CDI-capable Docker API 1.49+, and NVIDIA Container Toolkit. Obtain GPU allocation and sufficient resources.

BCM: Linux AMD64/ARM64, Python 3.10+, Bash, curl, tar, Git, rg, util-linux script and access to GPU001:18000. No GPU, CUDA, Docker, Node.js or npm is needed. SSH tool tasks require OpenSSH.

| Profile | Server CPU / image | Local GPUs | Engram | Validation |
|---|---|---|---|---|
| b300-tp4 | AMD64 / linux/amd64 | 4 B300 | GPU | Hardware validated |
| b300-tp4-dspark | AMD64 / linux/amd64 | 4 B300 | GPU | Optional single-user recipe; see validation |
| b200-tp4-cpu | AMD64 / linux/amd64 | 4 B200 | CPU | Four-GPU API smoke passed; see validation |
| b200-tp4 | AMD64 / linux/amd64 | 4 B200 | GPU | Four-GPU API smoke passed; see validation |
| rtx6000d-tp8 | AMD64 / linux/amd64 | 8 RTX 6000D | CPU | Experimental: eight-GPU API smoke and native-client tool round trip passed |
| gb300-tp4 | ARM64 / linux/arm64 | 4 GB300/B300 | GPU | Not hardware validated |
| gb300-tp2 | ARM64 / linux/arm64 | 2 GB300/B300 | CPU | Upstream recipe, unvalidated |

See [B200 deployment](docs/en/deployment.md#b200-four-gpu-experimental) for CPU/GPU Engram comparison. Both have separate bounded acceptance and do not inherit B300 performance results. v1.3.2 includes both B200 recipes; confirm them with ./local-ai profiles.

Starting with v1.3.2, the independent `rtx6000d-tp8` profile requires at least 85000 MiB per GPU and 256 GiB available host RAM. It uses a separately pinned SM120 image, 32K context, one sequence and text input, without DSpark or CUDA graphs. See [RTX 6000D deployment](docs/en/rtx6000d.md) for installation, eight-GPU startup and BCM commands. Explicitly select served model `DeepSeek-V4.1-Flash-SM120` on the client. Full 32K boundaries, concurrency and sustained stability remain unvalidated. The main workflow below continues to use four B300 GPUs; follow the dedicated guide for RTX 6000D.

BCM architecture is independent. Profiles use GPUs visible to one OS. GB300 TP2 checks at least 256 GiB MemAvailable; B300 acceptance does not cover GB300.

Validated baseline: Ubuntu 24.04, driver 580.126.20, Docker 29.2.1, Toolkit 1.19.1. DeepSeek-V4.1-Flash weights occupy about 510 GB; allow additional images, caches and a complete dist/ copy. Model/revision configuration is covered in [development](docs/en/development.md#model-and-client-compatibility).

## 1. Install and start on GPU001

Download into an empty directory and check Docker, GPUs and CDI:

```bash
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
curl -fL --retry 3 https://github.com/junli-nv/local-ai/archive/refs/tags/v1.3.3.tar.gz -o /tmp/local-ai-source.tar.gz
tar -xzf /tmp/local-ai-source.tar.gz --strip-components=1 -C /raid/local-ai
cd /raid/local-ai
./local-ai --version
./local-ai profiles
docker version
docker info --format 'Server={{.ServerVersion}} Driver={{.Driver}} Root={{.DockerRootDir}}'
nvidia-smi
nvidia-ctk cdi list
```

The Docker client must connect to the local daemon. Complete CDI setup below before installing model assets or starting the service.

### Configure GPU CDI definitions before first deployment

**Run on GPU001.** Working nvidia-smi output is not sufficient: verify CDI definitions too. nvidia-ctk cdi list must include a nvidia.com/gpu=GPU-... UUID alias for every selected GPU. Skip regeneration when those aliases already exist.

If the list is empty or selected UUIDs are absent, use the automatic refresh service when available:

```bash
sudo systemctl restart nvidia-cdi-refresh.service
nvidia-ctk cdi list
```

If it reports Unit nvidia-cdi-refresh.service not found, generate definitions manually below. First check /etc/cdi and /var/run/cdi for other valid or conflicting NVIDIA definitions; do not retain duplicates.

```bash
sudo install -d /etc/cdi
sudo nvidia-ctk cdi generate --device-name-strategy uuid --output=/etc/cdi/nvidia.yaml
nvidia-ctk cdi list
```

Compare aliases against local GPU UUIDs:

```bash
nvidia-smi --query-gpu=index,uuid --format=csv,noheader
```

**Success:** selected GPUs 0–3 each have a matching nvidia.com/gpu=GPU-... alias, without conflicts. Only then continue installation below. Missing aliases or conflicting definitions must be resolved first; visible GPUs in nvidia-smi alone do not permit startup. Regenerate manual definitions after driver, GPU or MIG changes.

Initial inspect No such image is expected. A pull error involving metadata.db requires [storage recovery](docs/en/deployment.md#docker-storage-failures). Docker active does not prove storage health. --data-dir does not move Docker/containerd databases; never share active databases across nodes.

### Install resources and start the instance

After Docker and CDI preflight succeeds:

```bash
./local-ai install --role server --profile b300-tp4
./local-ai server plan --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000
./local-ai server start --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000
./local-ai server status --name a
```

This server install command saves the inference profile, not the BCM endpoint; configure the client address in step 2. install reuses complete assets without starting GPUs. plan produces a plan; start checks live occupancy without terminating other tasks.

start waits up to 600 seconds, showing NOT READY/log paths during loading and compilation. A running container and /health HTTP 200 produce READY in terminal/runtime logs. status checks current readiness: exit 0 when ready, exit 1 with a reason otherwise.

| Evidence | GPU001 location / command |
|---|---|
| Installation/download/export/management | /raid/local-ai/install.log |
| Weights/compilation/warmup/READY | /raid/local-ai/instances/a/server.log |
| Live progress | tail -f /raid/local-ai/instances/a/server.log |
| Current status | ./local-ai server status --name a |

Add --wait-timeout 1200 for longer startup. Timeout exits 1; Ctrl+C returns 130; both retain the container. Check logs/status first. A historical READY, running container or listening port alone is insufficient.

--host 0.0.0.0 listens on all IPv4 interfaces; default is 127.0.0.1. BCM uses the host address, never 0.0.0.0. API keys/HTTPS are not configured; restrict network access. Address changes require [instance replacement](docs/en/deployment.md#replace-an-instance).

For single-user generation, optional b300-tp4-dspark and explicit --warmup are described in [deployment](docs/en/deployment.md#single-user-dspark-and-explicit-warmup). READY confirms API health; WARMUP COMPLETE confirms the bounded inference suite. Existing instances require explicit replacement to change recipes.

## 2. Install and use on BCM

Log in as alice on bcm-headnode and use BCM's own empty directory:

```bash
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
curl -fL --retry 3 https://github.com/junli-nv/local-ai/archive/refs/tags/v1.3.3.tar.gz -o /tmp/local-ai-source.tar.gz
tar -xzf /tmp/local-ai-source.tar.gz --strip-components=1 -C /raid/local-ai
cd /raid/local-ai
```

**Install the client, optionally saving a default address:** run this on BCM, substituting the actual server address:

```bash
./local-ai install --role client --endpoint http://GPU001:18000/v1
```

This optional initial default is saved in **BCM's /raid/local-ai/installation.json** after installation succeeds. GPU server installation does not configure the BCM address. Later changes use config, as shown below.

The default address is optional. To omit it, use ./local-ai install --role client and pass --endpoint to every chat invocation. One BCM client installation can connect to many services.

For an existing client without a saved address, use config set endpoint URL or specify chat --endpoint URL. Changing connection settings does not require installation.

Create or select the actual user's project directory:

```bash
mkdir -p /home/alice/project
```

This example saved GPU001:18000, so the following chat commands may omit --endpoint. Without a saved default, add --endpoint URL to each chat command.

```bash
# API/model check without generation
./local-ai chat --check
# Interactive chat
./local-ai chat --project /home/alice/project
# One task, then exit; hostname should return the BCM hostname
./local-ai chat --project /home/alice/project --run 'Use bash to run hostname and report its actual output.'
```

All three commands use GPU001:18000. chat --endpoint URL overrides one invocation without changing the saved address. Another port is introduced only for a [second instance](docs/en/deployment.md#two-instances-and-multiple-users).

### Enable Tab completion (optional)

v1.3.3 adds Bash Tab completion. In a Bash terminal on GPU001 or BCM, from the program directory, run:

```bash
eval "$(./local-ai completion bash)"
```

Complete subcommands, options, fixed choices such as recipes, and local paths without extra
dependencies. This enables the current terminal; see [command completion](docs/en/commands.md#bash-command-completion)
for examples and login persistence.

### Switch reasoning during a session

With DeepSeek-V4.1-Flash, press **Ctrl+T** at the chat prompt to cycle reasoning variants and check the displayed variant. `normal` preserves the original server behavior, `low` suits simpler tasks, and `none` disables thinking. See [dynamic reasoning variants](docs/en/commands.md#dynamic-reasoning-variants) for other levels and limits. Changes affect the next message without leaving the session or restarting the GPU service. Clients opened before upgrading must exit and resume once to load the new variants. OpenCode may remember a selection; choose `normal` explicitly to restore the original behavior.

### Configure the default connection

Run on BCM from /raid/local-ai. For example, save GPU001 as the default (substitute another URL to change it):

```bash
./local-ai config show
./local-ai config set endpoint http://GPU001:18000/v1
```

config only updates settings: it does not install, download or connect. config show reports the settings file and configured endpoint/model. You may directly edit endpoint/model in the existing /raid/local-ai/installation.json; preserve other fields and valid JSON. Changes apply to the next chat invocation. Null in show means no explicit default. The file belongs to this installation and is shared by users of that directory; edit permission is required.

Use config set model ID for a persistent model default. config unset endpoint requires explicit --endpoint on subsequent chat commands; config unset model restores the catalog fallback. These do not remove resources or histories. chat --endpoint/--model remain invocation-only overrides.

### Connect to multiple services from one BCM

One client installation can connect to many nodes. GPU002 below is another deployed model server, also on port 18000. Both nodes advertise the same model ID in this example:

```bash
# Check GPU002 for this invocation
./local-ai chat --endpoint http://GPU002:18000/v1 --check
# GPU002 runs inference; tools still execute on BCM
./local-ai chat --endpoint http://GPU002:18000/v1 --project /home/alice/project
# Without an override, return to the saved GPU001 default
./local-ai chat --project /home/alice/project
```

chat --endpoint neither rewrites installation.json nor requires reinstallation. --check reports the actual endpoint and model.

For a different model on GPU002, also pass --model with its advertised ID. If that ID is other-model:

```bash
./local-ai chat --endpoint http://GPU002:18000/v1 --model other-model --check
```

--model is also invocation-only. Omitting it uses the installed model default, without guessing another node's model; mismatch errors list advertised IDs. Histories/caches are separate per endpoint. Return to the original endpoint to continue its history. chat --session ID/--continue must select that endpoint too; the native opencode -s ID launcher locates the original address.

Resume with opencode -s ses_.... The first chat creates ~/.local/bin/opencode and reports PATH/name conflicts. chat --session ID and chat --continue are alternatives. Mouse capture/clipboard bindings are disabled by default; use terminal copying/pasting and keyboard navigation. See [session resume and terminal copying](docs/en/commands.md#resume-and-terminal-clipboard).

Tasks include hardware troubleshooting, scripts, services and Slurm/Kubernetes jobs. SSH queries use current-user permissions, independently of inference profiles. Rules are in [AGENTS.md](AGENTS.md); the no-probing constraint applies only to pure server plan --inventory.

## Update an existing installation

Use the [program update guide](docs/en/update.md) to update GPU and BCM installations separately while retaining resources, configuration and running instances. The standalone scripts/update.py supports explicit tags, local source archives and backup rollback, without install or resource preparation. v1.3.2 includes the updater; the guide also covers bootstrapping installations that lack it.

## Export and offline installation

This is a separate migration scenario. Export server images/models on the **source GPU host**, then verify/extract and run install --offline on the **new GPU host**. A BCM export normally carries client assets and cannot replace the GPU server bundle.

Complete commands are maintained only in the [offline guide](docs/en/offline.md). Choose a route:

- [Export an existing installation and import it elsewhere](docs/en/offline.md#scenario-1-export-an-installed-environment).
- [Prepare both roles online, then install offline](docs/en/offline.md#scenario-2-download-on-an-online-preparation-host).

Both routes specify execution hosts, files to transfer, checksums, offline import and acceptance, including BCM client deployment. Drivers/Docker remain target prerequisites; host-local instances and private histories are not carried. Development checks are in the [development guide](docs/en/development.md).
