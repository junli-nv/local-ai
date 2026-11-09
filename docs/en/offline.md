# Export, transfer and offline installation

This guide is the single complete migration procedure, separate from normal online deployment. Scenario 1 exports images/models on the old GPU host and client assets on the old BCM host, then imports each on its target. Scenario 2 prepares both roles on an online host. Offline import means checksum verification, extraction and install --offline; there is no separate top-level import command.

If resources are already installed and only program files need updating, use [offline program updates](update.md#offline-program-update). Transfer only the helper and small source archive; a complete model/image export is unnecessary.

The unpacked directory is the installation: /raid/local-ai here. local-ai is the launcher; src/ and docs/ hold source/manuals. models/, images/, clients/ hold weights, image archives/locks and public clients. dist/ holds exports. Defaults follow moved/renamed directories; no LOCAL_AI_DATA_DIR or --data-dir overrides are used.

Prerequisites: Python 3.10+, Bash, curl, tar, sha256sum (required for transfer verification); GPU hosts need compatible drivers, Docker API 1.49+ and NVIDIA Container Toolkit/CDI. BCM needs Git, rg and util-linux script. Use root or suitable sudo/Docker access. Example: Linux AMD64, four allocated B300 GPUs, b300-tp4, instance a. New GPU001 and bcm-headnode communicate internally on port 18000. Mount media at /media/local-ai. Allow roughly 510 GB for weights plus images and a complete dist/ copy. New targets must be empty.

Archives contain top-level local-ai/ and bundle.json checksums. They exclude dist/, instance state, logs, temporary caches, Git metadata, private histories and credentials. Docker active databases and drivers remain host-managed.

Both routes below are complete and independent; follow one route from start to finish. gpu-old/bcm-old are the existing source hosts; prep-host downloads assets without starting GPUs. New targets use GPU001/bcm-headnode as in README. Source downloads pin v1.3.4; record an exact commit when using main for development.

## Scenario 1: export an installed environment

### 1.1 Export on old GPU host gpu-old

Start from the complete current README installation, including local-ai and src/. Legacy data-only installations need the preparation below first. Do not update models during export. Export creates/reuses local image archives without downloading weights.

```bash
cd /raid/local-ai
./local-ai export
mkdir -p /media/local-ai/server
cp dist/local-ai.tar dist/local-ai.tar.sha256 /media/local-ai/server/
```

Success: media server/ contains local-ai.tar and its checksum, including program, images and models.

### 1.2 Export on old BCM host bcm-old

Use BCM's complete installation directory. Private history is excluded.

```bash
cd /raid/local-ai
./local-ai export
mkdir -p /media/local-ai/client
cp dist/local-ai.tar dist/local-ai.tar.sha256 /media/local-ai/client/
```

Carry the media to GPU001 and then bcm-headnode; mount it at /media/local-ai on each host.

### 1.3 Import offline and start on new GPU host GPU001

Installation verifies assets/imports the local image without starting inference. Check CDI and GPU allocation before startup.

```bash
cd /media/local-ai/server
sha256sum -c local-ai.tar.sha256
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
tar -xf local-ai.tar --strip-components=1 -C /raid/local-ai
cd /raid/local-ai
./local-ai install --role server --profile b300-tp4 --offline
./local-ai server inventory
nvidia-ctk cdi list
./local-ai server start --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000
./local-ai server status --name a
```

Success: installed=true, offline=true, then READY and ready=true.

### 1.4 Import offline and connect on new BCM host bcm-headnode

```bash
cd /media/local-ai/client
sha256sum -c local-ai.tar.sha256
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
tar -xf local-ai.tar --strip-components=1 -C /raid/local-ai
cd /raid/local-ai
./local-ai install --role client --offline --endpoint http://GPU001:18000/v1
./local-ai chat --check
./local-ai chat
```

Success: chat --check returns ready=true; execute hostname through chat and verify the new BCM host.

## Scenario 2: download on an online preparation host

### 2.1 Prepare target resources on any prep-host architecture

The preparation CPU need not match the target GPU server. Server media mainly consists
of the target vLLM image and pinned model files, plus source and checksums. Model files
and Python source are independent of AMD64/ARM64; container images follow the target
profile. Pulling and saving an image does not execute it.

This example uses an **AMD64 preparation host, AMD64 BCM and ARM64 GB200 server**,
so the target is gb200-tp4. It remains an unvalidated candidate requiring four GPUs
visible to one OS; see [GB200 and Rubin](gb200-rubin.md). Substitute another complete
target profile as needed. The preparation host needs Python 3.10+, tar, sha256sum, Docker API
1.49+ and access to GitHub, the registry and public Hugging Face models. It needs no
GPU, NVIDIA driver, CDI, ARM emulation or QEMU.

v1.3.5 includes prepare. Download the complete tagged source; the unpacked directory
remains the installation root:

```bash
local_ai_source=/tmp/local-ai-v1.3.5-source.tar.gz
curl -fL --retry 3 https://github.com/junli-nv/local-ai/archive/refs/tags/v1.3.5.tar.gz -o "$local_ai_source"
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
tar -xzf "$local_ai_source" --strip-components=1 -C /raid/local-ai
cd /raid/local-ai
./local-ai --version
./local-ai prepare --help
./local-ai prepare --profile gb200-tp4
```

Success: prepared=true, started=false; models/ contains complete weights and a revision
lock, and images/ contains the linux/arm64 image archive and content lock. Model downloads
use the host Python standard library over HTTP, checking file lengths and Hub content
identities with resumable transfers. No target container or inference program runs.
Complete local models and images are reused. Progress is in install.log. This downloader
supports public models; it neither reads nor bundles credentials.

To include this example AMD64 BCM client in the same package, run on the AMD64 prep-host:

```bash
cd /raid/local-ai
./local-ai install --role client --online
```

This optional step needs NPM and prepares the host-native OpenCode without GPUs. Omit it
for server-only media. If BCM and prep-host architectures differ, prepare the client
separately using the BCM route in scenario 1; do not execute foreign client binaries.
Do not substitute install --role server/both for cross-platform prepare.

### 2.2 Export to dist/ and copy onto media

```bash
cd /raid/local-ai
./local-ai export --profile gb200-tp4
mkdir -p /media/local-ai/both
cp dist/local-ai.tar dist/local-ai.tar.sha256 /media/local-ai/both/
```

Select the target profile explicitly at export. With the optional client step, this package contains ARM64 server resources and an AMD64 client; otherwise it is server-only. Target installation and startup still check CPU, GPU and CDI compatibility.

Prepare multiple target platforms together; complete models with the same repo/revision
are reused. prepare does not write host installation settings, so export lists profiles explicitly:

```bash
./local-ai prepare --profile b300-tp4 --profile gb200-tp4
./local-ai export --profile b300-tp4 --profile gb200-tp4 --output dist/local-ai-multi.tar
```

Use separate resource directories when one model_directory maps to different repo/revisions.

### 2.3 Import offline and start on new GPU host GPU001

```bash
cd /media/local-ai/both
sha256sum -c local-ai.tar.sha256
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
tar -xf local-ai.tar --strip-components=1 -C /raid/local-ai
cd /raid/local-ai
./local-ai install --role server --profile gb200-tp4 --offline
./local-ai server inventory
nvidia-ctk cdi list
./local-ai server start --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000
./local-ai server status --name a
```

Success: installed=true, offline=true, READY and ready=true.

### 2.4 Import offline and connect on new BCM host bcm-headnode

```bash
cd /media/local-ai/both
sha256sum -c local-ai.tar.sha256
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
tar -xf local-ai.tar --strip-components=1 -C /raid/local-ai
cd /raid/local-ai
./local-ai install --role client --offline --endpoint http://GPU001:18000/v1
./local-ai chat --check
./local-ai chat
```

Success: chat --check returns ready=true; execute hostname through chat to confirm tool location.

## Different directory names

Extract into another empty directory; defaults follow the new location.

```bash
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/ai-prod
tar -xf /media/local-ai/server/local-ai.tar --strip-components=1 -C /raid/ai-prod
cd /raid/ai-prod
./local-ai install --role server --offline
```

## Legacy installation with data but no program

Preserve custom source edits first. Obtain the complete program from GitHub and unpack into the existing data root; source packages contain no models or instances.

```bash
sudo install -d -o "$(id -u)" -g "$(id -g)" /raid/local-ai
curl -fL --retry 3 https://github.com/junli-nv/local-ai/archive/refs/tags/v1.3.5.tar.gz -o /tmp/local-ai-source.tar.gz
tar -xzf /tmp/local-ai-source.tar.gz --strip-components=1 -C /raid/local-ai
cd /raid/local-ai
./local-ai --version
```

On the old GPU host reuse local resources and export without weight downloads:

```bash
./local-ai install --role server --profile b300-tp4 --offline
./local-ai export
```

For legacy BCM client assets outside the installation, include the actual asset directory once:

```bash
./local-ai export --client-dir /home/alice/.local/state/local-ai/clients/amd64
```

## Configuration after import

v1.3.4 may carry GB200/Rubin definitions and synthetic fixtures. Complete resource
export cannot select rubin-tp2-framework because its image and memory guard are unresolved.
Export does not make unprepared source resources usable. See [GB200 and Rubin](gb200-rubin.md).

Before GPU startup, resolve missing UUID aliases through [CDI setup](deployment.md#cdi-setup).

The source endpoint is not carried in the bundle. The new BCM examples set an initial default during client installation; later use config set endpoint URL or edit the file reported by config show, without installation. For one invocation, chat --endpoint URL selects another reachable internal service; add --model ID for a different model. See [multi-service usage](../../README.en.md#connect-to-multiple-services-from-one-bcm) for history isolation.

Compilation caches and warmup records are excluded with instance state. After target installation and API startup, follow [explicit warmup](deployment.md#single-user-dspark-and-explicit-warmup) on the target GPU when needed; online preparation does not run inference.

## Optional document converters

Portable source includes the document MCP tool when exported from a version containing it. Host Poppler/LibreOffice are not bundled: provision matching offline system packages on the target BCM before using PDF/legacy Office/rendering. See [offline document requirements](documents.md#offline-environments).

## Logs and failures

Installation/export: INSTALL_ROOT/install.log. Startup: instances/a/server.log. READY requires a health check, not merely a running container. Clients print their private session Log path. Offline missing-file/checksum errors stop without download fallback. Resolve CDI, network, architecture or resource errors before continuing.

See [deployment](deployment.md), [commands](commands.md) and [validation](validation.md).
