# User manual and command reference

[中文（默认）](../commands.md)

## Getting started

Use the [deployment guide](deployment.md) for first installation and this page for command lookup and operations. Run commands from the source checkout.

| Example | Meaning |
|---|---|
| GPU001 | GPU server running the model container |
| bcm-headnode | BCM host running OpenCode and local tools |
| alice; /home/alice/project | BCM user and an existing project directory; replace as needed |
| a; 18000 | Instance name and model API port on GPU001, not hostname or SSH port |

Discover commands without starting a model:

```bash
./local-ai --help
./local-ai server --help
./local-ai server start --help --data-dir /raid/local-ai
./local-ai chat --help
```

Syntax: ./local-ai GROUP COMMAND OPTIONS. profiles and chat have no child command. Every level supports --help. The global --debug option goes before the command group and prints a Python traceback on failure.

## All commands

| Command | Run on | Purpose and result |
|---|---|---|
| profiles | Either host | Profile catalog and validation status as JSON |
| server inventory | GPU001 | Local CPU architecture, GPU models, UUIDs and memory |
| server plan | GPU001 | JSON plan with selected devices, engine args and Docker command; no container creation |
| server start | GPU001 | Validate resources, start the instance and report container, health URL and log |
| server status | GPU001 | Named container state and labels |
| server stop | GPU001 | Stop the named instance; retain weights and host logs |
| image pull | Connected GPU preparation host | Pull the pinned image and record platform identity |
| image export | Docker preparation host | Image archive and companion lock file |
| image import | Offline GPU host | Verify archive and lock, then load the image |
| model download | Connected preparation host | Pinned config, tokenizer, index and all weight shards |
| client install | bcm-headnode | Install a pinned native client online or import local assets |
| client doctor | bcm-headnode | Check client and Python/git/SSH/rg/script availability |
| client export | BCM preparation host | Client/public-cache archive without private history or credentials |
| chat | bcm-headnode | Connect to inference; execute tools locally as the current user |

server runs vLLM through Docker; the plan's command field shows the Docker arguments. chat starts native OpenCode and owns its SSH tunnel. Tools do not execute inside the GPU container.

Engine options are not passed through arbitrarily; maintain model/vLLM presets in profiles.json/profiles.py. Each started instance records spec.json, args.json, docker-command.json and launch.log for inspection.

## Local reuse and installation journal

Preparation checks local artifacts first. A matching pinned/platform image skips registry access.
A complete model configuration, tokenizer, index and all shards skip network downloads. Safetensors
length/offset validation is structural, not a complete SHA256 check; use MODELS.sha256 for offline hash acceptance.
A model.lock.json verifies repository/revision metadata. Without it, revision_verified=false is explicit;
a conflicting revision or truncated shard is rejected instead of silently reused.

image pull --force explicitly contacts the registry. model download --force forces a download from
the pinned revision and may transfer all weights again. Routine repeat execution does not need --force.

Installation/deployment commands append to one journal: DATA_DIR/install.log on GPU001 and
CLIENT_DIR/install.log on BCM. Each operation has an ID and records timestamps, host/version/options,
actual commands, live output, elapsed time, exit status and full exceptions. Long commands report
liveness/output-byte counts every 15 seconds. JSON stays on stdout; progress goes to stderr.
Read-only queries and plan do not create logs.

A missing local image is an expected lookup result and triggers a pull. Docker daemon, permission, or storage inspection errors are reported directly. Failed commands display an error summary on terminal stderr, limited to the last five lines with long lines shortened; complete output remains in the journal. Image pull exceptions also retain Docker's error text.

Put this global option before the command group to choose a fixed journal:

```bash
./local-ai --install-log /raid/local-ai/install.log image pull --profile b300-tp4
```

If both hosts can write the same shared directory, use the same --install-log path for a shared installation journal.
Ongoing model output remains in instances/NAME/server.log; chat history and session logs remain separate.

## Server parameters

| Option | Commands | Meaning and default |
|---|---|---|
| --data-dir | server plan/start/status/stop; image; model download | Data root: LOCAL_AI_DATA_DIR, otherwise /raid/local-ai. status actually looks up the instance by name. |
| --profile | plan/start; image; model download | Hardware/engine preset; required for image, otherwise b300-tp4 |
| --gpus | plan/start | Required comma-separated server indices or full UUIDs; count must match the profile |
| --name | plan/start/status/stop | Default a; lowercase letter followed by lowercase letters, digits or hyphens; at most 32 characters |
| --host | plan/start | IPv4 listen address, default 127.0.0.1; 0.0.0.0 for all IPv4 interfaces or a local IP; no hostnames or IPv6 |
| --port | plan/start | Model API port, default 18000, range 1024–65535 |
| --inventory | plan only | JSON hardware fixture instead of discovery; start does not accept it |
| --output | image export | Required destination archive path |
| --archive; --lock | image import | Required image archive and matching .lock.json |

TP is tensor parallelism: b300-tp4 uses four local B300 GPUs. See [deployment](deployment.md) for GB300 limitations. Data and source directories are separate. Options do not persist between commands; use the same data root for preparation, planning, starting and stopping.

On GPU001:

```bash
./local-ai server plan --profile b300-tp4 --gpus 0,1,2,3 --name a --port 18000 --data-dir /raid/local-ai
./local-ai server start --profile b300-tp4 --gpus 0,1,2,3 --name a --port 18000 --data-dir /raid/local-ai
./local-ai server status --name a
curl --fail http://127.0.0.1:18000/health
```

plan neither reserves GPUs nor checks current process/port occupancy; start checks occupancy. Startup returning is not model readiness. Initial loading/compilation can take minutes. A successful health request (curl exit 0) may have an empty body. Here 127.0.0.1 means GPU001, where curl is run.

The listen address affects engine arguments, instance identity and startup port checks.
Plan does not check local interface ownership. Default loopback instances stay compatible;
changing --host requires explicitly stopping, removing and recreating an existing container.
Wildcard listeners report a loopback health URL; specific IP listeners report that IP.
Managed instances still reserve the API port across interfaces.
Use --endpoint http://GPU001:18000/v1 for direct access, never 0.0.0.0.
API keys/HTTPS are not configured; restrict network access. A specific interface listener
requires --endpoint because --server still forwards to remote loopback.
See [README](../../README.en.md) for the complete procedure.

## Client parameters

client install/doctor/export accept --client-dir, defaulting to clients/ARCH under the private user-state root. The root is ~/.local/state/local-ai, or $XDG_STATE_HOME/local-ai when set. Select native binaries for BCM's architecture independently of the GPU server.

| Option | Command | Meaning and default |
|---|---|---|
| --binary | client install | Import local OpenCode executable; omit for online installation |
| --seed-cache | client install | Optional offline public cache directory |
| --version | client install | Expected download/import version, default 1.19.5 |
| --sha256 | client install | Optional expected checksum from a trusted binary manifest |
| --output | client export | Required archive destination; also creates .sha256 |

See [offline deployment](offline.md) for artifact paths and imports.

## Chat parameters

| Option | Meaning and default |
|---|---|
| --server GPU001 | SSH hostname or alice@GPU001; exactly one of --server and --endpoint is required |
| --endpoint URL | Reachable HTTP(S) model API base including /v1; no SSH tunnel |
| --ssh-user; --ssh-port | SSH user from user@host/OpenSSH settings unless overridden; SSH port defaults to 22 |
| --port | Remote model API port, default 18000 |
| --local-port | Local BCM tunnel port; default 0 automatically selects a free port |
| --project | Existing BCM project directory, default current directory |
| --client-dir | Native client asset directory; match installation location |
| --state-dir | Private history/cache/log root, default described above |
| --model | Served API model ID; default from profiles.json served_name |
| --check | Check connection and model availability; report ready/log path and exit |
| --run 'task' | Run one prompt, stream JSON events, save full logs and exit; omit for interactive use |

On bcm-headnode as alice:

```bash
./local-ai client doctor
./local-ai chat --server GPU001 --check
./local-ai chat --server GPU001 --project /home/alice/project
./local-ai chat --server GPU001 --project /home/alice/project --run 'Run hostname and report its output.'
```

For model/image upgrades, validate a separate data directory and instance while retaining the old source, weights and image locks. Avoid forcing a replacement over production weights as a rollback strategy.

## Operations and troubleshooting

| Symptom / operation | Action |
|---|---|
| Service not ready | On GPU001 check server status and DATA_DIR/instances/a/server.log, then retry /health |
| Image extraction reports missing metadata.db | Follow the [deployment recovery procedure](deployment.md); check runtime storage and workloads before restarting Docker and containerd. File existence immediately after restart is not an acceptance check. |
| BCM cannot connect | Run ssh GPU001 hostname, client doctor and chat --server GPU001 --check; verify API port |
| Client cannot see GPUs | Expected on BCM; inspect inference processes with nvidia-smi on GPU001 |
| GPU or port conflict | Check allocations and workloads; choose free resources without stopping unrelated jobs |
| Change GPUs, port or profile | Inspect and stop the instance, explicitly remove its container, then recreate |
| Exit chat | The session's SSH tunnel closes; inference service remains running |
| Update or roll back | Record Git commit, image digest and model revision; validate a separate instance before switching clients. Switch back to a validated instance/version on failure. |

On GPU001, after confirming a is the instance to replace:

```bash
./local-ai server stop --name a --data-dir /raid/local-ai
# Remove only this stopped container; retain weights and host logs
docker rm local-ai-a
./local-ai server start --profile b300-tp4 --gpus 0,1,2,3 --name a --port 18000 --data-dir /raid/local-ai
```

Exit relevant clients before backing up their private state. Never commit history, credentials or raw logs. Server logs are DATA_DIR/instances/NAME/server.log; installation/preparation logs are DATA_DIR/install.log. Client logs live under private services/ID/logs/session-.../. Plan image, weight and user-state backups separately.

Most management commands return JSON. chat returns the client's exit code; single-prompt runs stream JSON events. Invalid arguments and failures exit nonzero. For a traceback, use ./local-ai --debug GROUP COMMAND OPTIONS.

No automatic load balancing, user quotas, boot startup, cross-host TP or GPU scheduling is provided. Allocate dedicated, available GPU resources before startup. The application does not require a cluster scheduler. See [validation](validation.md) for B300/GB300 evidence and remaining acceptance work.
