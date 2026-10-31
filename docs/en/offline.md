# Offline deployment

[中文（默认）](../offline.md)

Prepare three independent artifact sets: source, GPU-server image/weights, and
BCM-native client assets. A GB300 server usually needs ARM64 images while its BCM
client may still need AMD64. Never choose client architecture from the GPU name.

The target OS must already have the required tools: compatible GPU driver,
Docker/CDI/Toolkit on the server; Python/Bash/git/SSH/rg/script on BCM. Host driver
and OS packages are not included inside vLLM. Plan offline installation packages
for the actual distro/kernel. Linux ELF architecture is not an entire ABI check.

## 1. Source snapshot

From a reviewed commit:
```bash
mkdir -p dist
git archive --format=tar.gz --output=dist/local-ai-source.tar.gz HEAD
cd dist
sha256sum local-ai-source.tar.gz > local-ai-source.tar.gz.sha256
cd ..
```

Do not package the whole working directory: ignored files may include raw logs
and personal state. Source does not include 510 GB model weights or native binaries.

## 2. GPU image and weights

On a connected Docker preparation host:
```bash
./local-ai image pull --profile b300-tp4 --data-dir /data/local-ai
./local-ai image export --profile b300-tp4 --data-dir /data/local-ai \
  --output /data/export/vllm-amd64.tar
```

For GB300 replace the profile with gb300-tp4 (or gb300-tp2) and use a distinct
vllm-arm64.tar. Pull/inspect/save explicitly select the image platform. Preparing
an ARM64 image archive on AMD64 does not require executing ARM64 code.
Cross-platform image handling requires Docker API 1.49+; Docker 29 is the tested baseline.

Export writes a companion `.lock.json` with the archive SHA256 and selected image
config/layer fingerprint. Carry both files. No mutable-tag-only fallback is used.

Download model weights on a preparation host using a native-CPU profile:
```bash
./local-ai model download --profile b300-tp4 --data-dir /data/local-ai
rsync -a /data/local-ai/models/ /data/export/models/
cd /data/export
find models -type f -print0 | sort -z | xargs -0 sha256sum > MODELS.sha256
```

Model files are CPU-architecture independent; copies must include configuration,
tokenizer, index and all shards. The same model copy can serve two instances.

On the offline GPU host, extract source, verify/copy weights, regenerate local
CDI if needed, then import:
```bash
cd /media/export
sha256sum -c MODELS.sha256
sudo mkdir -p /raid/local-ai/models
sudo rsync -a models/ /raid/local-ai/models/
cd /path/to/local-ai
./local-ai image import --profile b300-tp4 --data-dir /raid/local-ai \
  --archive /media/export/vllm-amd64.tar \
  --lock /media/export/vllm-amd64.tar.lock.json
./local-ai server start --profile b300-tp4 --gpus 0,1,2,3 --name a
curl --fail http://127.0.0.1:18000/health
```

Use the ARM64 archive/profile on GB300. Local image identity can be represented
differently after Docker import; equivalent config/layer content and matching
platform are required. Cached CUDA kernels are not assumed portable; first start
may compile locally using the pinned image.

## 3. BCM client assets

On a connected headnode with the same target CPU/compatible Linux environment:
```bash
./local-ai client install
./local-ai client doctor
./local-ai client export --output /data/export/client-amd64.tar.gz
```

The export contains `client/bin/opencode`, a public `seed-cache`, and an asset
manifest. It excludes histories, auth databases and SSH keys.
Matching architecture matters for cached executables too.

On offline BCM:
```bash
cd /media/export
sha256sum -c client-amd64.tar.gz.sha256
mkdir -p client-unpacked
tar -xzf client-amd64.tar.gz -C client-unpacked
cd /path/to/local-ai
./local-ai client install \
  --binary /media/export/client-unpacked/client/bin/opencode \
  --seed-cache /media/export/client-unpacked/client/seed-cache
./local-ai client doctor
./local-ai chat --server gpu-a --check
./local-ai chat --server gpu-a --run 'Use bash to run hostname and report the result.'
```

No Node/npm/Docker is required on BCM. Use `--sha256` with the exported manifest's
binary checksum when importing a standalone binary outside the checked archive.
Verify network-free operation after any new client release or plugin change.

## 4. Acceptance

With internet unavailable but internal SSH intact:
1. Cold-start the image and complete model locally; check API readiness.
2. Start a fresh user's client, not just an administrator's already-warm account.
3. Verify search/read/edit/test tools and that hostname is the BCM host.
4. Check complete private logs, selected GPU UUIDs, HBM and absence of stray tunnels.
5. Test representative input lengths and concurrency; do not extrapolate decode speed.

HF/Transformers offline flags are enabled in the server. Client updates, model
catalog fetch, default external plugins and LSP downloads are disabled.
Explicit project plugins, external MCP/search, git clone or pip/npm/apt downloads
can still require internet; prepare project dependencies and tools in advance.

See validation.md for what was actually tested. Network-isolated client tests
do not by themselves establish a fresh GPU-server cold start on another platform.
