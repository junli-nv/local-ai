# Deployment and operations

[中文（默认）](../deployment.zh-CN.md)

Follow [README](../../README.en.md) for first online installation. This page expands deployment branches and recovery, without repeating source download, client installation or chat. See [offline deployment](offline.md) for migration, and the [manual](commands.md) for parameters.

Conventions: GPU001, bcm-headnode, alice, /raid/local-ai, instance a, port 18000. Run local-ai commands on GPU001 from /raid/local-ai unless explicitly marked BCM. No data-directory overrides are used.

## CDI setup

nvidia-ctk cdi list must show nvidia.com/gpu=GPU-... UUID aliases for selected GPUs. Generate definitions on the target host; never copy another host's definitions.

With the automatic refresh service:

```bash
sudo systemctl restart nvidia-cdi-refresh.service
nvidia-ctk cdi list
```

Without that service, an administrator first checks /etc/cdi and /var/run/cdi for existing valid NVIDIA definitions/conflicts, then generates local UUID definitions:

```bash
sudo install -d /etc/cdi
sudo nvidia-ctk cdi generate --device-name-strategy uuid --output=/etc/cdi/nvidia.yaml
nvidia-ctk cdi list
```

Regenerate manual definitions after driver, GPU or MIG changes. Avoid duplicate definitions. If selected UUIDs remain absent, stop and investigate. Server image and BCM architectures are independent; see README for GB300 validation limits.

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
