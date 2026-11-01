# Offline deployment: two complete workflows

[中文（默认）](../offline.md)

Choose one workflow and follow it from preparation through acceptance.
You do not need to assemble steps from the other workflow.

| Workflow | Starting point | Preparation hosts |
|---|---|---|
| [Scenario 1](#scenario-1-export-an-installed-environment-and-migrate) | A working installation to migrate | gpu-old and bcm-old |
| [Scenario 2](#scenario-2-download-on-an-online-preparation-host) | No existing installation; internet available | prep-host |

## Fixed example hosts and paths

The example uses b300-tp4: an AMD64 server with four allocated B300 GPUs and
a Linux AMD64 BCM client. Select server and client architectures independently.

| Item | Value throughout both workflows |
|---|---|
| Installation root including source | /raid/local-ai |
| Old/new GPU data root | /raid/local-ai |
| Online preparation scratch data | /data/local-ai-prep |
| Preparation artifact bundle | /data/local-ai-offline |
| Removable-media mount on preparation/new hosts | /media/local-ai-offline |
| BCM account and client assets | alice; /home/alice/.local/state/local-ai/clients/amd64 |
| New inference endpoint | http://GPU001:18000/v1; instance a, GPUs 0,1,2,3 |

Before starting:

- The example account alice has sudo and Docker access; root can omit sudo.
  Replace account/path values consistently for another setup.
- New GPU001 already has Python 3.10+, compatible drivers, Docker API 1.49+
  and NVIDIA Container Toolkit/CDI. New bcm-headnode has Python 3.10+,
  Bash, Git, rg and util-linux script.
- rsync, tar, sha256sum, find, sort and xargs are available. BCM can reach the
  internal model API. Media is mounted with enough space: roughly 510 GB of
  weights plus images, archives and copies.
- Use an empty /raid/local-ai install root on new hosts and an empty bundle for each
  preparation batch. Preserve old installations; use their actual source/data paths if different.
  Prepare OS/driver packages separately.
- For custom recipes, carry and verify the same JSON catalog, select it through
  LOCAL_AI_CATALOG at every stage, and retain matching source/recipe/locks.

Source resides directly in /raid/local-ai, alongside GPU models/, images/,
instances/ and install.log. BCM client assets remain in the user-private path.

The complete bundle must contain:

```text
/data/local-ai-offline/
  local-ai-source.tar.gz
  local-ai-source.tar.gz.sha256
  vllm-amd64.tar
  vllm-amd64.tar.lock.json
  models/
  MODELS.sha256
  client-amd64.tar.gz
  client-amd64.tar.gz.sha256
```

## Scenario 1: export an installed environment and migrate

### 1.1 Export source, image and model on old GPU host gpu-old

Run from the actual installation root. Git checkouts export committed source;
extracted installations without .git package an explicit source list. Review local
changes first. Neither branch archives models/, images/, instances/ or the whole root.
These commands do not download or require stopping a read-only serving instance.
Do not update model files during the copy.

```bash
cd /raid/local-ai
./local-ai --version
sudo install -d -o "$(id -u)" -g "$(id -g)" /data/local-ai-offline
if [ -e .git ]; then
  git archive --format=tar.gz --output=/data/local-ai-offline/local-ai-source.tar.gz HEAD
else
  tar --exclude='__pycache__' --exclude='*.pyc' --exclude='*.log' --exclude='.env*' \
    -czf /data/local-ai-offline/local-ai-source.tar.gz \
    local-ai pyproject.toml src README.md README.en.md AGENTS.md docs scripts tests
fi

./local-ai image export --profile b300-tp4 --data-dir /raid/local-ai \
  --output /data/local-ai-offline/vllm-amd64.tar

mkdir -p /data/local-ai-offline/models
rsync -aL /raid/local-ai/models/ /data/local-ai-offline/models/
cd /data/local-ai-offline
sha256sum local-ai-source.tar.gz > local-ai-source.tar.gz.sha256
find models -type f -print0 | sort -z | xargs -0 -r sha256sum > MODELS.sha256
```

Success: source/checksum, image/matching lock and complete models/MODELS.sha256
exist. rsync -L copies link targets, making the bundle self-contained.
Preserve existing model locks; never fabricate a revision for missing locks.
Do not migrate active Docker/containerd databases, old instances, logs or histories.

### 1.2 Export the client on old BCM host bcm-old and collect it on gpu-old

Use the current account's actual client asset directory, not the
~/.local/bin/opencode resume launcher. The example uses scp instead of assuming
that the two old hosts share storage.

```bash
cd /raid/local-ai
sudo install -d -o "$(id -u)" -g "$(id -g)" /data/local-ai-offline
./local-ai client export \
  --client-dir /home/alice/.local/state/local-ai/clients/amd64 \
  --output /data/local-ai-offline/client-amd64.tar.gz
scp /data/local-ai-offline/client-amd64.tar.gz \
  /data/local-ai-offline/client-amd64.tar.gz.sha256 \
  alice@gpu-old:/data/local-ai-offline/
```

Success: gpu-old now has the entire bundle checklist. Client archives contain
binary, public cache and manifest, excluding private history and credentials.

### 1.3 Transfer the complete bundle onto offline media

Run on gpu-old after mounting the media.

```bash
rsync -a /data/local-ai-offline/ /media/local-ai-offline/
```

Carry the media to the new environment and mount it at the same
/media/local-ai-offline path. Import on GPU001 next, then on bcm-headnode;
the same media can be mounted on each host in turn.

### 1.4 Import and start on new GPU host GPU001

Verify/extract source, copy weights, verify destination hashes, import the image,
then start. This source archive is produced by the packaging commands above
without a directory prefix; do not add --strip-components.

```bash
cd /media/local-ai-offline
sha256sum -c local-ai-source.tar.gz.sha256
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
tar -xzf local-ai-source.tar.gz -C /raid/local-ai

mkdir -p /raid/local-ai/models
rsync -a /media/local-ai-offline/models/ /raid/local-ai/models/
cd /raid/local-ai
sha256sum -c /media/local-ai-offline/MODELS.sha256

cd /raid/local-ai
./local-ai --version
./local-ai image import --profile b300-tp4 --data-dir /raid/local-ai \
  --archive /media/local-ai-offline/vllm-amd64.tar \
  --lock /media/local-ai-offline/vllm-amd64.tar.lock.json
./local-ai server inventory
nvidia-ctk cdi list
./local-ai server start --host 0.0.0.0 --profile b300-tp4 \
  --gpus 0,1,2,3 --name a --port 18000 --data-dir /raid/local-ai
./local-ai server status --name a
```

Success: all checksums report OK, image import returns imported=true, startup
reports READY and status returns ready=true. Import checks archive/platform/content
identity. Confirm new GPUs 0,1,2,3 are allocated and their UUIDs exist in CDI;
do not copy old host GPU UUIDs. Loading/compilation may take minutes.
If not ready, inspect /raid/local-ai/instances/a/server.log and preparation
/raid/local-ai/install.log. Resolve the failure before continuing.

### 1.5 Import the client and connect on new BCM host bcm-headnode

Extract the same source on this host. Unpack client assets under the writable
user directory; the offline media itself may be read-only.

```bash
cd /media/local-ai-offline
sha256sum -c local-ai-source.tar.gz.sha256
sha256sum -c client-amd64.tar.gz.sha256
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
tar -xzf local-ai-source.tar.gz -C /raid/local-ai
mkdir -p /home/alice/local-ai-client-import
tar -xzf client-amd64.tar.gz -C /home/alice/local-ai-client-import

cd /raid/local-ai
./local-ai client install \
  --client-dir /home/alice/.local/state/local-ai/clients/amd64 \
  --binary /home/alice/local-ai-client-import/client/bin/opencode \
  --seed-cache /home/alice/local-ai-client-import/client/seed-cache
./local-ai chat --endpoint http://GPU001:18000/v1 \
  --client-dir /home/alice/.local/state/local-ai/clients/amd64 --check
./local-ai chat --endpoint http://GPU001:18000/v1 \
  --client-dir /home/alice/.local/state/local-ai/clients/amd64 \
  --run 'Run hostname with bash and report its actual output.'
```

Success: installation uses the local binary, chat --check returns ready=true,
and the one-shot task actually invokes the hostname tool on the new BCM host
(bcm-headnode in this example). Start interactive use:

```bash
cd /raid/local-ai
./local-ai chat --endpoint http://GPU001:18000/v1 \
  --client-dir /home/alice/.local/state/local-ai/clients/amd64
```

### 1.6 Completion criteria

With no internet but internal BCM-to-GPU001 connectivity, complete READY,
client check and the actual hostname task above. The client's printed Log path
contains its full session log. Configure new users' SSH/Slurm/Kubernetes access
and project dependencies separately; do not migrate private histories or keys
inside shared client archives. Explicit external plugins/MCP or download tasks
still require their own prepared resources.

## Scenario 2: download on an online preparation host

prep-host is Linux AMD64 with Python 3.10+, Git, Docker API 1.49+ and copy/checksum
tools, and access to GitHub, the registry, Hugging Face and NPM. No GPU is required.
Client version validation executes the binary, so the host must also match the
target BCM CPU and Linux compatibility. This example selects v1.0.0; another
reviewed version can be selected consistently.

### 2.1 Download source, image and model, then export on prep-host

```bash
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai /data/local-ai-prep
git clone --branch v1.0.0 --depth 1 https://github.com/junli-nv/local-ai.git /raid/local-ai
cd /raid/local-ai
./local-ai --version
sudo install -d -o "$(id -u)" -g "$(id -g)" /data/local-ai-offline
git archive --format=tar.gz --output=/data/local-ai-offline/local-ai-source.tar.gz HEAD

./local-ai image pull --profile b300-tp4 --data-dir /data/local-ai-prep
./local-ai model download --profile b300-tp4 --data-dir /data/local-ai-prep
./local-ai image export --profile b300-tp4 --data-dir /data/local-ai-prep \
  --output /data/local-ai-offline/vllm-amd64.tar

mkdir -p /data/local-ai-offline/models
rsync -aL /data/local-ai-prep/models/ /data/local-ai-offline/models/
cd /data/local-ai-offline
sha256sum local-ai-source.tar.gz > local-ai-source.tar.gz.sha256
find models -type f -print0 | sort -z | xargs -0 -r sha256sum > MODELS.sha256
```

Success: source, image/archive lock and complete model/checksum exist.
Model download runs a native-CPU container, not merely an image fetch;
b300-tp4 matches this AMD64 preparation host.

### 2.2 Download and export the BCM client on the same prep-host

```bash
cd /raid/local-ai
./local-ai client install --client-dir /data/local-ai-prep/client-amd64
./local-ai client export --client-dir /data/local-ai-prep/client-amd64 \
  --output /data/local-ai-offline/client-amd64.tar.gz
```

Success: /data/local-ai-offline contains the complete checklist.
Add --version X.Y.Z to client install when selecting a particular release;
offline import detects the actual binary version.

### 2.3 Transfer the complete bundle onto offline media

Run on prep-host after mounting the media.

```bash
rsync -a /data/local-ai-offline/ /media/local-ai-offline/
```

Carry the media to the new environment and mount it at the same
/media/local-ai-offline path. Import on GPU001 next, then on bcm-headnode;
the same media can be mounted on each host in turn.

### 2.4 Import and start on new GPU host GPU001

Verify/extract source, copy weights, verify destination hashes, import the image,
then start. This source archive is produced by the packaging commands above
without a directory prefix; do not add --strip-components.

```bash
cd /media/local-ai-offline
sha256sum -c local-ai-source.tar.gz.sha256
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
tar -xzf local-ai-source.tar.gz -C /raid/local-ai

mkdir -p /raid/local-ai/models
rsync -a /media/local-ai-offline/models/ /raid/local-ai/models/
cd /raid/local-ai
sha256sum -c /media/local-ai-offline/MODELS.sha256

cd /raid/local-ai
./local-ai --version
./local-ai image import --profile b300-tp4 --data-dir /raid/local-ai \
  --archive /media/local-ai-offline/vllm-amd64.tar \
  --lock /media/local-ai-offline/vllm-amd64.tar.lock.json
./local-ai server inventory
nvidia-ctk cdi list
./local-ai server start --host 0.0.0.0 --profile b300-tp4 \
  --gpus 0,1,2,3 --name a --port 18000 --data-dir /raid/local-ai
./local-ai server status --name a
```

Success: all checksums report OK, image import returns imported=true, startup
reports READY and status returns ready=true. Import checks archive/platform/content
identity. Confirm new GPUs 0,1,2,3 are allocated and their UUIDs exist in CDI;
do not copy old host GPU UUIDs. Loading/compilation may take minutes.
If not ready, inspect /raid/local-ai/instances/a/server.log and preparation
/raid/local-ai/install.log. Resolve the failure before continuing.

### 2.5 Import the client and connect on new BCM host bcm-headnode

Extract the same source on this host. Unpack client assets under the writable
user directory; the offline media itself may be read-only.

```bash
cd /media/local-ai-offline
sha256sum -c local-ai-source.tar.gz.sha256
sha256sum -c client-amd64.tar.gz.sha256
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
tar -xzf local-ai-source.tar.gz -C /raid/local-ai
mkdir -p /home/alice/local-ai-client-import
tar -xzf client-amd64.tar.gz -C /home/alice/local-ai-client-import

cd /raid/local-ai
./local-ai client install \
  --client-dir /home/alice/.local/state/local-ai/clients/amd64 \
  --binary /home/alice/local-ai-client-import/client/bin/opencode \
  --seed-cache /home/alice/local-ai-client-import/client/seed-cache
./local-ai chat --endpoint http://GPU001:18000/v1 \
  --client-dir /home/alice/.local/state/local-ai/clients/amd64 --check
./local-ai chat --endpoint http://GPU001:18000/v1 \
  --client-dir /home/alice/.local/state/local-ai/clients/amd64 \
  --run 'Run hostname with bash and report its actual output.'
```

Success: installation uses the local binary, chat --check returns ready=true,
and the one-shot task actually invokes the hostname tool on the new BCM host
(bcm-headnode in this example). Start interactive use:

```bash
cd /raid/local-ai
./local-ai chat --endpoint http://GPU001:18000/v1 \
  --client-dir /home/alice/.local/state/local-ai/clients/amd64
```

### 2.6 Completion criteria

With no internet but internal BCM-to-GPU001 connectivity, complete READY,
client check and the actual hostname task above. The client's printed Log path
contains its full session log. Configure new users' SSH/Slurm/Kubernetes access
and project dependencies separately; do not migrate private histories or keys
inside shared client archives. Explicit external plugins/MCP or download tasks
still require their own prepared resources.

## Troubleshoot at the failing step

| Failure | Check first |
|---|---|
| Old image export cannot find assets | Actual old --data-dir, images/ lock and local platform image; do not migrate active runtime databases |
| SHA256 mismatch | Stop at that step; verify one matching export batch and recopy damaged files |
| Missing model/revision conflict | Complete models/ including configuration/tokenizer/index/shards and existing locks; do not fabricate provenance |
| Missing CDI/start failure | Complete host/CDI prerequisites in the [deployment guide](deployment.md), then inspect the runtime log above |
| BCM cannot reach API | GPU001 READY, port 18000, DNS/routing/firewall; never use 0.0.0.0 as endpoint |
| Client cannot execute | Exported manifest CPU and target BCM Linux compatibility, independently of the GPU host |

These examples do not use --force. Do not redownload complete artifacts just to
validate offline use. See the [manual](commands.md) and [validation](validation.md)
for options and the actually tested scope.
