# Deployment and operations

[Software prerequisites and version checks](prerequisites.md)

[中文（默认）](../deployment.zh-CN.md)

Follow [README](../../README.en.md) for first online installation. This page expands deployment branches and recovery, without repeating source download, client installation or chat. See [offline deployment](offline.md) for migration, and the [manual](commands.md) for parameters.

Conventions: GPU001, bcm-headnode, alice, /raid/local-ai, instance a, port 18000. Run local-ai commands on GPU001 from /raid/local-ai unless explicitly marked BCM. No data-directory overrides are used.

For program-only upgrades of an existing installation, use the [update guide](update.md). It preserves running instances/resources and needs no image/model preparation. Changes to inference recipes remain explicit instance replacement operations.

## CDI setup

The complete first-deployment check, refresh/manual-generation commands and UUID acceptance criteria are in [README: configure GPU CDI definitions](../../README.en.md#configure-gpu-cdi-definitions-before-first-deployment), before model installation/startup. Follow that procedure on the target GPU host; do not copy another host's definitions.

For missing/duplicate aliases, inspect /etc/cdi and /var/run/cdi and resolve conflicting definitions before continuing. Regenerate manual definitions after driver, GPU or MIG changes; existing complete aliases do not require regeneration.

## Docker storage failures

On GPU001:

```bash
docker version
docker info --format 'Server={{.ServerVersion}} Driver={{.Driver}} Root={{.DockerRootDir}}'
docker ps -a
```

Docker must reach its server. systemctl active does not establish storage health. Initial image inspect No such image is expected; the following pull's actual error determines the failure.

--data-dir controls project assets, not Docker/containerd live storage. Docker 29 may use /var/lib/docker and /var/lib/containerd separately; inspect actual configuration. Never delete/move these directories while running or share their databases across nodes.

### Missing metadata.db

Stop installation if pull reports:

```text
failed to prepare extraction snapshot
/var/lib/containerd/io.containerd.snapshotter.v1.overlayfs/metadata.db: no such file or directory
```

One observed cause is deletion of storage while services still hold deleted database handles. Restarting Docker alone does not restart independent containerd. Have an administrator inspect configuration, mounts and original data; recover required storage first.

Inspect Docker containers and all containerd namespaces/tasks before arranging maintenance:

```bash
docker ps -a
sudo ctr namespaces list
for ns in $(sudo ctr namespaces list -q); do
    sudo ctr --namespace "$ns" tasks list
    sudo ctr --namespace "$ns" containers list
done
```

After confirming interruption is allowed and original storage need not be restored:

```bash
sudo systemctl stop docker.service docker.socket
sudo systemctl restart containerd.service
sudo systemctl start docker.socket docker.service
docker info
```

Return to README and retry installation; if the original operation was image pull, retry that first. Persistent failures require install.log and journalctl -u containerd -u docker, not repeated restarts/database deletion.

metadata.db may be created only when a snapshot is first created; absence immediately after restart is not proof of failure. Do not touch it manually. Successful pull/extraction establishes recovery. These steps do not restore lost images, containers or volumes and are not a routine installation requirement.

## Listening and networking

--host defaults to 127.0.0.1. README uses 0.0.0.0 so BCM can access http://GPU001:18000/v1; a specific local IPv4 address is also accepted. 0.0.0.0 is not a client address; --host accepts neither hostnames nor IPv6.

Health probes use 127.0.0.1 for wildcard binding, otherwise the configured IP. Configure routing/firewalls for BCM access. Existing instances require replacement to change addresses. API keys/HTTPS are not configured; restrict trusted-client access.

Administrators manage nginx/frp forwarding separately. Clients use the final reachable endpoint; model access does not require SSH. Operational tools may still use SSH. Add GPU001/the actual IP to NO_PROXY/no_proxy if proxy variables interfere.

A single BCM client can also choose services on other GPU hosts with chat --endpoint URL; this is independent of the two-instance-on-one-host example below. See [multi-node usage](../../README.en.md#connect-to-multiple-services-from-one-bcm) for optional defaults, model selection and session isolation.

## Replace an instance

For GPU, port, address or recipe changes, confirm a is the intended instance and record old/new parameters. Stop and explicitly remove its container, then start with new arguments. Restarting the same container does not change arguments.

This example recreates a with the same parameters; apply actual changes consistently to plan/start:

```bash
cd /raid/local-ai
./local-ai server status --name a
./local-ai server stop --name a
docker rm local-ai-a
./local-ai server plan --profile b300-tp4 --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000
./local-ai server start --profile b300-tp4 --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000
```

Weights and host logs remain. Different specs are never silently substituted. Readiness/timeouts/logging are described in [README](../../README.en.md#1-install-and-start-on-gpu001); exit codes are in the manual.

Startup checks permit TCP TIME_WAIT reuse after a stopped HTTP service, while rejecting active listeners. Other applications owning the port still require a different port or explicit operator action.

## RTX 6000D eight-GPU (experimental)

v1.3.2 adds independent `rtx6000d-tp8`: AMD64, eight GPUs with at least 85000 MiB each, and 256 GiB available host RAM. It uses 32K, one sequence, CPU Engram and text input, without DSpark/CUDA graphs. Complete [software prerequisites](prerequisites.md) and CDI checks, then follow the [RTX 6000D guide](rtx6000d.md) to install, start and select `DeepSeek-V4.1-Flash-SM120` on BCM. Eight-GPU API smoke and native tool round trips passed; full 32K, concurrency and sustained stability remain unvalidated.

## B200 four-GPU (experimental)

`b200-tp4-cpu` stores Engram tables in host memory; `b200-tp4` retains GPU Engram.
Both require AMD64, four B200 GPUs and at least 180000 MiB HBM per GPU.
The CPU profile additionally checks 256 GiB MemAvailable. These are conservative
guards, not measured minimum requirements. Both retain the fixed model revision,
AMD64 image digest and B300 baseline engine settings: 131072 context, four active
sequences, 8192 batched tokens and a 0.80 memory budget, without DSpark.
Both passed bounded four-GPU API smoke checks in the recorded environment;
full-context boundaries and long-running loads remain unvalidated.
These profiles are included since v1.3.2; obtain current tagged source through README
and check ./local-ai profiles. Freed weight memory may be reused for KV cache,
so nvidia-smi total usage need not fall. API READY does not eliminate first-shape JIT.

Run on GPU001 after the README Docker, selected CDI UUID and idle-device checks.
Examples use generic GPUs 0–3; select allocated healthy devices using your topology, preferably on one NUMA node.
Indices are not part of the recipe. Host-memory locality needs a separate check;
selecting GPUs alone does not bind CPU memory.

```bash
cd /raid/local-ai
./local-ai install --role server --profile b200-tp4-cpu
./local-ai server plan --profile b200-tp4-cpu --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000
./local-ai server start --profile b200-tp4-cpu --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000
./local-ai server status --name a
```

For GPU Engram, explicitly replace the instance using `b200-tp4`, keeping devices,
context, concurrency and requests identical. Do not run both on the same GPUs.
Measure TTFT, generation speed, HBM and host memory; capacity does not establish
performance. LOCAL_AI_CATALOG or config/catalog.json replaces the entire catalog;
merge these recipes explicitly into a custom catalog.

Reasoning can be switched with Ctrl+T in the BCM chat UI; see [dynamic reasoning variants](commands.md#dynamic-reasoning-variants). This is independent of B200 CPU/GPU Engram placement and needs no server replacement.

## Single-user DSpark and explicit warmup

The default b300-tp4 keeps its existing settings. Optional b300-tp4-dspark favors single-user generation speed, with a possible concurrency throughput cost. DSpark uses speculative decoding with target-model verification to improve the decode phase; lower TTFT is not guaranteed. It uses the same image and weights. See [validation](validation.md) for measurements and limits. This recipe is not validated on GB300.

Run on GPU001 from /raid/local-ai with free GPUs and port. If a already exists, first confirm and follow [instance replacement](#replace-an-instance) to stop and remove its container.

```bash
./local-ai server plan --profile b300-tp4-dspark --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000
./local-ai server start --profile b300-tp4-dspark --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000 --wait-timeout 1200 --warmup --warmup-timeout 600
./local-ai server status --name a
```

--wait-timeout covers API startup only. After API health succeeds, --warmup sends real generation requests under a separate --warmup-timeout. Ordinary start does not generate requests. READY means API health; WARMUP COMPLETE means explicit warmup finished.

A healthy running instance can also be warmed separately, without installation or restart, including the baseline recipe:

```bash
./local-ai server warmup --name a
./local-ai server status --name a
```

Warmup consumes GPU resources and competes with traffic; run before admitting users. Defaults cover exact input lengths 1024, 8192 and 32768 tokens when context permits, output length 256, concurrency 1, 2, 4 and 8, twice per group: 90 requests for this recipe. Requests beyond four active sequences queue. Fresh prefixes avoid mistaking prefix-cache hits for compilation coverage. Finite warmup cannot eliminate JIT for every later length or batch.

For a smaller workload-specific suite:

```bash
./local-ai server warmup --name a --input-tokens 1024,8192 --concurrency 1,4 --output-tokens 256 --repeats 2 --timeout 600
```

install.log and instances/a/server.log show WARMING, progress and WARMUP COMPLETE, or WARMUP INCOMPLETE. instances/a/warmup.json records shapes, elapsed time and completed counts. Status only reads this record and sends no generation requests. completed=true requires matching configuration and container start time; after restart it becomes stale and needs explicit warmup again. Failure/timeout exits 1; Ctrl+C exits 130. Both retain the container, whose API may remain healthy: inspect ready and warmup separately.

The DSpark recipe places TileLang and CUDA compilation caches inside persisted instances/a/cache for reuse by the same instance. Engine versions, GPU architectures or settings may require recompilation; weight loading and all first-use compilation are not eliminated. Exports exclude instance caches; warm again on the target GPU after migration.

LOCAL_AI_CATALOG or installation config/catalog.json fully replaces the built-in catalog and does not automatically acquire new recipes. Merge and validate the desired recipe using the [development guide](development.md#model-and-client-compatibility).

## Two instances and multiple users

Only this section introduces another service: on eight B300 GPUs, a uses GPUs 0–3/port 18000 and b uses GPUs 4–7/port 18001. Confirm spare devices and port availability, then run on GPU001:

```bash
cd /raid/local-ai
./local-ai server start --profile b300-tp4 --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000
./local-ai server start --profile b300-tp4 --host 0.0.0.0 --gpus 4,5,6,7 --name b --port 18001
```

Only read-only weights are shared; GPUs, memory, KV, ports, caches and logs are separate. On BCM, select b for these invocations:

```bash
cd /raid/local-ai
./local-ai chat --endpoint http://GPU001:18001/v1 --check
./local-ai chat --endpoint http://GPU001:18001/v1 --project /home/alice/project
```

Without --endpoint, chat still uses the saved 18000 address. To change the saved default, use config set endpoint URL; no installation is required. Histories are separate per endpoint and are not migrated by changing ports.

Use separate Linux accounts/private state, default ~/.local/state/local-ai/. Shared binaries do not share histories. Different directories under one account are not permission isolation; administrators can access user data. Exit clients before state backup.

Four active sequences per engine is a scheduling limit, not a four-user limit; additional requests queue. No automatic balancing, quotas, boot startup or cross-host TP is provided. Measure concurrency separately; see [validation](validation.md).
