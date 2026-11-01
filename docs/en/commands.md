# User manual and command reference

[中文（默认）](../commands.md)

## Getting started

Use the [deployment guide](deployment.md) for first installation and this page for command lookup and operations. Run commands from the source checkout.

| Example | Meaning |
|---|---|
| GPU001 | GPU server running the model container |
| bcm-headnode | BCM host running OpenCode and local tools |
| alice; /home/alice/project | BCM user and an existing project directory; replace as needed |
| a; 18000 | Instance name and model API port on GPU001, instance identifier and HTTP API port |

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
| server start | GPU001 | Validate resources, start and wait for API readiness; report result and log |
| server status | GPU001 | Explicit READY/NOT READY result with reason, listener and log |
| server stop | GPU001 | Stop the named instance; retain weights and host logs |
| image pull | Connected GPU preparation host | Pull the pinned image and record platform identity |
| image export | Docker preparation host | Image archive and companion lock file |
| image import | Offline GPU host | Verify archive and lock, then load the image |
| model download | Connected preparation host | Pinned config, tokenizer, index and all weight shards |
| client install | bcm-headnode | Install a selected native client release online or import local assets |
| client export | BCM preparation host | Client/public-cache archive without private history or credentials |
| chat | bcm-headnode | Connect to inference; execute tools locally as the current user |

server runs vLLM through Docker; the plan's command field shows the Docker arguments. chat connects to the specified API and starts native OpenCode. Tools do not execute inside the GPU container.

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
| --wait-timeout | start only | Positive seconds to wait for API readiness, default 600; timeout exits 1 and retains the container |
| --inventory | plan only | JSON hardware fixture instead of discovery; start does not accept it |
| --output | image export | Required destination archive path |
| --archive; --lock | image import | Required image archive and matching .lock.json |

TP is tensor parallelism: b300-tp4 uses four local B300 GPUs. See [deployment](deployment.md) for GB300 limitations. Data and source directories are separate. Options do not persist between commands; use the same data root for preparation, planning, starting and stopping.

On GPU001:

```bash
./local-ai server plan --host 0.0.0.0 --profile b300-tp4 --gpus 0,1,2,3 --name a --port 18000 --data-dir /raid/local-ai
./local-ai server start --host 0.0.0.0 --profile b300-tp4 --gpus 0,1,2,3 --name a --port 18000 --data-dir /raid/local-ai
./local-ai server status --name a
```

Plan neither reserves GPUs nor checks occupancy. Start checks resources and waits up to 600 seconds for API readiness; use --wait-timeout to adjust. Exit 0 means readiness was confirmed. Status checks immediately, exits 0 for READY or 1 for NOT READY/check failure, and writes no files.

The listen address affects engine arguments, instance identity and startup port checks.
Plan does not check local interface ownership. Default loopback instances stay compatible;
changing --host requires explicitly stopping, removing and recreating an existing container.
Wildcard listeners report a loopback health URL; specific IP listeners report that IP.
Managed instances still reserve the API port across interfaces.
Clients only connect to --endpoint. Administrators configure nginx/frp or other forwarding separately.
API keys/HTTPS are not configured; restrict network access. See [README](../../README.en.md).

Start immediately prints the runtime log, tail -f and status commands. When the API succeeds,
both terminal and instance server.log receive an explicit timestamped READY confirmation.
An open port alone is insufficient; HTTP 503 or a stopped container is NOT READY.
First compilation may take minutes. A past READY entry does not establish current health.

Timeout exits 1, records NOT READY and the cause, and retains the container. Container exit
records FAILED. Ctrl+C cancels waiting with exit 130 without stopping the container.
Use status afterward, or start with identical arguments to resume waiting and record readiness;
a matching running instance is not restarted. Status prints a human-readable result to stderr
and JSON ready/listening/health/log fields to stdout. It probes the container and API, not old logs.

## Client parameters

client install/export accept --client-dir, defaulting to clients/ARCH under the private user-state root. The root is ~/.local/state/local-ai, or $XDG_STATE_HOME/local-ai when set. Select native binaries for BCM's architecture independently of the GPU server.

| Option | Command | Meaning and default |
|---|---|---|
| --binary | client install | Import local OpenCode executable; omit for online installation |
| --seed-cache | client install | Optional offline public cache directory |
| --version | client install | Explicit release; otherwise reuse installed or detect imported version; first online reference 1.19.5 |
| --sha256 | client install | Optional expected checksum from a trusted binary manifest |
| --output | client export | Required archive destination; also creates .sha256 |

See [offline deployment](offline.md) for artifact paths and imports.

## Chat parameters

| Option | Meaning and default |
|---|---|
| --endpoint URL | Required reachable HTTP(S) model API base including port and /v1 |
| --project | Existing BCM project directory, default current directory |
| --client-dir | Native client asset directory; match installation location |
| --state-dir | Private history/cache/log root, default described above |
| --model | Served API model ID; default from profiles.json served_name |
| --check | Check connection and model availability; report ready/log path and exit |
| --run 'task' | Run one prompt, stream JSON events, save full logs and exit; omit for interactive use |

On bcm-headnode as alice:

```bash
./local-ai chat --endpoint http://GPU001:18000/v1 --check
./local-ai chat --endpoint http://GPU001:18000/v1 --project /home/alice/project
./local-ai chat --endpoint http://GPU001:18000/v1 --project /home/alice/project --run 'Run hostname and report its output.'
```

For model/image upgrades, validate a separate data directory and instance while retaining the old source, weights and image locks. Avoid forcing a replacement over production weights as a rollback strategy.

### Resume and terminal clipboard

The first chat invocation (including --check) creates a per-user resume launcher
at `~/.local/bin/opencode`. Run the exit hint `opencode -s ses_...` directly to
restore the original endpoint, project and private history. If needed, run
`export PATH="$HOME/.local/bin:$PATH"` and add it to `~/.profile`.
An existing unrelated opencode executable is preserved; use the explicit entry instead:

```bash
./local-ai chat --endpoint http://GPU001:18000/v1 --project /home/alice/project --session ses_example
./local-ai chat --endpoint http://GPU001:18000/v1 --project /home/alice/project --continue
```

`--session` (`-s`) restores a session; `--continue` (`-c`) resumes the latest for
this project. They are mutually exclusive. The launcher supports `opencode -s ID`,
not the entire native CLI. OpenCode mouse capture, copy on selection and built-in
clipboard copy/read shortcuts are disabled by default. Use terminal selection,
copy and paste, and keyboard navigation; UI mouse clicks and wheel scrolling
are disabled. tmux selection settings remain user-managed. Use `/export` for
long transcripts. Changes apply to new or resumed clients.

### Client versions and offline recovery

Select a release with `client install --version X.Y.Z`, or import a local
executable with --binary. The default download release is a validation reference,
not a runtime version allowlist. Resume uses public `session list --format json`,
not private database tables. An incompatible interface reports the failing
capability; arbitrary future releases may still require adaptation.
Validate upgrades in a separate client directory and temporary history: resume
flags, JSON session metadata, mouse disablement and terminal paste. Exit old
clients and back up history before switching. Downgrades may require restoring
the pre-upgrade history backup after database migrations.

If downloads become unavailable, reuse the local installation, import an existing
binary or restore a client export archive. Archives include executable, public
cache, version manifest and checksums, excluding history and credentials.
See [offline deployment](offline.md).

## Operations and troubleshooting

| Symptom / operation | Action |
|---|---|
| Service not ready | On GPU001 check server status and DATA_DIR/instances/a/server.log, inspect the reported reason or increase start --wait-timeout |
| Image extraction reports missing metadata.db | Follow the [deployment recovery procedure](deployment.md); check runtime storage and workloads before restarting Docker and containerd. File existence immediately after restart is not an acceptance check. |
| BCM cannot connect | Run chat --endpoint http://GPU001:18000/v1 --check; inspect API readiness, DNS, routing, firewall and proxy settings |
| Client cannot see GPUs | Expected on BCM; inspect inference processes with nvidia-smi on GPU001 |
| GPU or port conflict | Check allocations and workloads; choose free resources without stopping unrelated jobs |
| Change GPUs, port or profile | Inspect and stop the instance, explicitly remove its container, then recreate |
| Exit chat | The local client exits; inference remains running |
| Update or roll back | Record Git commit, image digest and model revision; validate a separate instance before switching clients. Switch back to a validated instance/version on failure. |

On GPU001, after confirming a is the instance to replace:

```bash
./local-ai server stop --name a --data-dir /raid/local-ai
# Remove only this stopped container; retain weights and host logs
docker rm local-ai-a
./local-ai server start --host 0.0.0.0 --profile b300-tp4 --gpus 0,1,2,3 --name a --port 18000 --data-dir /raid/local-ai
```

Exit relevant clients before backing up their private state. Never commit history, credentials or raw logs. Server logs are DATA_DIR/instances/NAME/server.log; installation/preparation logs are DATA_DIR/install.log. Client logs live under private services/ID/logs/session-.../. Plan image, weight and user-state backups separately.

Most management commands return JSON. chat returns the client's exit code; single-prompt runs stream JSON events. Invalid arguments and failures exit nonzero. For a traceback, use ./local-ai --debug GROUP COMMAND OPTIONS.

No automatic load balancing, user quotas, boot startup, cross-host TP or GPU scheduling is provided. Allocate dedicated, available GPU resources before startup. The application does not require a cluster scheduler. See [validation](validation.md) for B300/GB300 evidence and remaining acceptance work.

Select external model recipes with LOCAL_AI_CATALOG; see [compatibility](development.md#model-and-client-compatibility).
