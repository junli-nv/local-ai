# Deployment guide

[中文（默认）](../deployment.zh-CN.md)

Run inference on the GPU server; run OpenCode and its tools on BCM. Keep source separate from model data and user state.

## Example environment

| Hostname | Role | Commands run here |
|---|---|---|
| `GPU001` | GPU server; an eight-card B300 in this example | Prepare images/weights, manage inference instances, check health |
| `bcm-headnode` | BCM headnode | Log in as `alice`, install the client, use OpenCode in `/home/alice/project` |

Replace these hostnames with your own. The examples assume BCM can reach the model API on GPU001.
Instance names `a` and `b` identify services on that GPU server, not hostnames.

See the [manual](commands.md) for every command, option default and troubleshooting step.

## 1. Select a profile

| Profile | Server CPU | Local GPUs | Engram | Status |
|---|---|---:|---|---|
| b300-tp4 | AMD64 | 4 | GPU | B300 validated |
| gb300-tp4 | ARM64 | 4 | GPU | Experimental |
| gb300-tp2 | ARM64 | 2 | CPU | Experimental |

Check uname -m and nvidia-smi. Choose the BCM binary independently. GPUs must be visible to one OS; cross-host TP and NVL72 scheduling are not implemented. TP2 offload alone needs about 189 GiB RAM. The 256 GiB MemAvailable guard is conservative, not a measured minimum. Validate GB300 on real hardware.

## 2. Prepare the GPU server

The deployment account needs Docker access and write permission to the data directory, configured by the administrator.

Choose these values before running the example:

| Option | Meaning / what to change |
|---|---|
| `--profile b300-tp4` | B300 four-GPU inference preset. TP4 splits one instance across four local GPUs. |
| `--data-dir /raid/local-ai` | Weights, image locks, cache and logs; separate from the Git checkout. Choose a large local directory. |
| `--gpus 0,1,2,3` | Server GPU indices from nvidia-smi, or full UUIDs. Count must match the profile. |
| `--name a` | Instance name, reused for status/stop and its log directory; not a hostname. |
| `--port 18000` | Model HTTP API port, default 18000. Use 18001 for a second instance. |

Server plan/start default to profile b300-tp4 and name a; --gpus is required.
The data directory uses LOCAL_AI_DATA_DIR if set, otherwise /raid/local-ai.
Use the same --data-dir for preparation, planning and startup: options do not carry over between commands.

Allocate GPUs first. Install compatible drivers, Docker API 1.49+, NVIDIA Container Toolkit and Python 3.10+. Keep source and /raid/local-ai data separate. The tool does not stop other jobs.

```bash
git clone https://github.com/junli-nv/local-ai.git
cd local-ai
nvidia-smi
nvidia-ctk cdi list
# List profiles and validation status
./local-ai profiles
```

nvidia-ctk cdi list must show nvidia.com/gpu=GPU-... aliases for selected devices. Zero devices is not ready. If CDI is missing, regenerate on this host; do not copy device definitions:

```bash
sudo systemctl restart nvidia-cdi-refresh.service
nvidia-ctk cdi list
```

Verify UUID aliases again after refresh. Without a refresh service, follow NVIDIA's manual CDI procedure. Avoid duplicate definitions.

### Check Docker storage before downloading

Run on the GPU node:

```bash
docker version
docker info --format 'Server={{.ServerVersion}} Driver={{.Driver}} Root={{.DockerRootDir}}'
docker ps -a
```

The Docker server must be accessible. An active docker service only confirms a running process,
not working image extraction or storage. A first image inspection reporting `No such image`
is expected and triggers a pull; diagnose the subsequent pull error.

`--data-dir` controls project weights, locks and runtime data, not Docker/containerd storage.
With Docker 29's containerd image store, these services may use `/var/lib/docker` and
`/var/lib/containerd` separately; check the actual configuration. Never delete or move storage
while the services are running, or share runtime databases between nodes.

### Recovery: missing metadata.db during image extraction

Stop installation and inspect runtime storage if image pull reports:

```text
failed to prepare extraction snapshot
/var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/metadata.db: no such file or directory
```

One verified cause is storage deleted while services still hold open database files.
An active Docker service does not rule this out. Restarting Docker alone does not restart
the independent containerd service. First check configuration, mounts and original data.
Restore storage containing data that must be retained instead of replacing it with empty directories.

Inspect Docker containers and every containerd namespace before restarting:

```bash
docker ps -a
sudo ctr namespaces list
for ns in $(sudo ctr namespaces list -q); do
    sudo ctr --namespace "$ns" tasks list
    sudo ctr --namespace "$ns" containers list
done
```

Arrange maintenance for running tasks. Empty lists do not replace administrator confirmation
of other runtime users. Once interruption is acceptable and original storage need not be restored,
run on the target GPU node; root may omit sudo:

```bash
sudo systemctl stop docker.service docker.socket
sudo systemctl restart containerd.service
sudo systemctl start docker.socket docker.service
docker info
```

Retry the original image pull before downloading weights. Do not repeatedly restart services
or delete databases. For continued failures inspect the installation journal's actual error and
`journalctl -u containerd -u docker`.

`metadata.db` may be created only on the first snapshot creation. Its absence immediately after
restart does not prove failure; listing snapshots may not create it either. Successful image pull
and extraction are the acceptance check. Never manually `touch metadata.db`.
This recovery does not restore lost images, containers or volumes and is not a routine installation step.

Complete local images/models are reused. Preparation decisions, commands and errors append to /raid/local-ai/install.log; see the [manual](commands.md).

```bash
# Download the inference container image
./local-ai image pull --profile b300-tp4 --data-dir /raid/local-ai
# Download complete model weights
./local-ai model download --profile b300-tp4 --data-dir /raid/local-ai
```

Existing complete weights belong in /raid/local-ai/models/DeepSeek-V4.1-Flash/. Weights are CPU-independent; images are not.

## 3. Start and validate

```bash
# Preview the plan without starting a service
./local-ai server plan --host 0.0.0.0 --profile b300-tp4 --gpus 0,1,2,3 --name a --port 18000 --data-dir /raid/local-ai
# Start the instance; initial loading takes time
./local-ai server start --host 0.0.0.0 --profile b300-tp4 --gpus 0,1,2,3 --name a --port 18000 --data-dir /raid/local-ai
./local-ai server status --name a
curl --fail http://127.0.0.1:18000/v1/models
./local-ai server status --name a
```

On GPU001, server status --name a prints READY or NOT READY. Server start waits up to 600 seconds by default and records a timestamped READY confirmation in the terminal and instance server.log. Timeout or container exit is explicitly reported.

Use gb300-tp4 for four local GB300 GPUs or gb300-tp2 with --gpus 0,1 for two. Full UUIDs are accepted. plan does not allocate devices; start checks occupancy. Initial compilation may take minutes. Container running state is not API readiness. Full logs and launch arguments are under instances/a/ in the data directory.

Normal acceptance is start reporting READY and exit 0; no extra curl step is required.
NOT READY includes the reason. Use --wait-timeout 1200 for a longer cold start.
Timeout or Ctrl+C retains the container; query status or repeat start with identical arguments.
See [README](../../README.en.md) for explicit results, exit codes and log markers.

### API listen address

Server plan/start accept --host, default 127.0.0.1. Set --host 0.0.0.0 or a local
IPv4 address for BCM access through --endpoint http://GPU001:18000/v1.
An existing container must be explicitly recreated to change its listen address.
See [README](../../README.en.md) for commands and network access requirements.

## 4. Install on BCM

Install as the user who will execute tools:

```bash
git clone https://github.com/junli-nv/local-ai.git
cd local-ai
./local-ai client install
```

BCM needs Python, Bash, git, rg and script, not Docker, CUDA, Node or npm.
Installation checks the pinned binary's integrity. Offline installation imports
prepared native assets. SSH is optional for onward tool tasks, not model access.

## 5. Use from BCM

Wait for the GPU API and verify BCM can reach it. Replace GPU001 with a reachable
IP or hostname. The API port is part of --endpoint; --project selects an existing
BCM directory, defaulting to the current directory.

```bash
./local-ai chat --endpoint http://GPU001:18000/v1 --project /home/alice/project
./local-ai chat --endpoint http://GPU001:18000/v1 --check
./local-ai chat --endpoint http://GPU001:18001/v1 --project /home/alice/project
./local-ai chat --endpoint http://GPU001:18000/v1 --run 'Use bash to run hostname and report its output.'
```

The client connects to HTTP(S) APIs and does not manage network forwarding.
Administrators configure frp/nginx or other forwarding separately and supply its
reachable URL. Tools execute on BCM; inference runs on the GPU server.
See [README](../../README.en.md) for listen addresses and instance recreation.

## 6. Two instances and multiple users

On an eight-GPU B300 server:

```bash
./local-ai server start --host 0.0.0.0 --profile b300-tp4 --name a --gpus 0,1,2,3 --port 18000 --data-dir /raid/local-ai
./local-ai server start --host 0.0.0.0 --profile b300-tp4 --name b --gpus 4,5,6,7 --port 18001 --data-dir /raid/local-ai
```

Instances have separate GPUs, HBM, KV, caches, ports and logs; only read-only weights are shared. Select the port in the --endpoint URL. There is no load balancing.

Use separate Linux accounts and private state under ~/.local/state/local-ai/. History is keyed by API endpoint. Connection configurations are independent. Root can access user files. Four active sequences per engine is a scheduling limit; additional requests queue. Measure concurrent throughput separately.

## 7. Stop and reconfigure

```bash
./local-ai server stop --name b --data-dir /raid/local-ai
./local-ai server start --host 0.0.0.0 --profile b300-tp4 --name b --gpus 4,5,6,7 --port 18001 --data-dir /raid/local-ai
```

To change GPUs, port or profile, inspect and stop the instance, explicitly remove its container, then recreate it. Model files and host logs remain. Automatic boot startup and resource handoff are not implemented.

## 8. Offline use and development

Carry source, matching server image/weights, and BCM-native assets separately. See [offline deployment](offline.md), [architecture](architecture.md), [development](development.md) and [validation](validation.md). Keep the internal BCM-to-API network available. External MCP, web search and dependency downloads need separate preparation.
