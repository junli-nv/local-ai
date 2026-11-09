# GB200 TP4 candidate and single-node Rubin framework

Offline media can be prepared on another CPU architecture with prepare --profile gb200-tp4: reuse the pinned model and select the ARM64 image. See [online preparation](offline.md#scenario-2-download-on-an-online-preparation-host). This does not extend GB200 hardware acceptance.

v1.3.4 includes the GB200 TP4 candidate and Rubin TP2 framework. Neither platform is
available locally. CPU tests verify configuration, pure planning and rejection, without proving
model startup or performance. GPU001 denotes the future GPU host. BCM continues using an API
endpoint with independently selected client architecture. Only GPUs visible to one OS are used;
there is no rack management or cross-node tensor parallelism.

## Experimental GB200 TP4 recipe

`gb200-tp4` requires ARM64, exactly four local GB200/B200 GPUs and at least 180000 MiB per GPU.
This is a provisional B200-class capacity guard, not a measured minimum. B200 names accommodate
device reporting; CPU architecture, card count, unique UUIDs and individual memory are checked.

Retains the pinned DeepSeek-V4.1-Flash revision and B200 TP4 engine baseline: GPU Engram,
131072 context, four active sequences, FP8 KV and original CUDA Graph settings, without adding
DSpark. It uses the existing pinned multi-architecture image with ARM64 platform digest
`sha256:b1bea6490db94268e68577929ae4b800a662b91a3cd4a1fcba81cfb3946ddcff`.
The public registry confirmed Linux ARM64 and CUDA 13.0.2 on 2026-11-09. This does not establish
GB200 compatibility of every DeepSeek kernel, target drivers, memory, full context or concurrency.

Run from current source on a development host, without GPUs, Docker, weights or network access:

```bash
./local-ai server plan --profile gb200-tp4 --host 0.0.0.0 --gpus 0,1,2,3 --name a --port 18000 --inventory tests/fixtures/gb200-tp4.json --data-dir /tmp/local-ai-gb200-plan
```

Exits 0 with `deployable=true` and an ARM64 Docker command; creates no data directory.
Deployable means recipe inputs are filled in and a launch command can be generated, not that
hardware is validated or allocated. The fixture is explicitly synthetic: GPU names, indices,
UUIDs, PCI addresses and memory values are illustrative, not measurements. No GB200 TP2 is added.

## Planning-only Rubin framework

`rubin-tp2-framework` models two Rubin/VR200 GPUs visible to one ARM64 OS, with planned CPU
Engram offload. Official capacity is 288GB HBM4 per GPU, or 576GB nominal for two, not usable
model capacity. Current weights occupy about 510GB on disk, which also differs from resident
GPU memory. A rough 0.80 budget gives only about 460.8GB, with KV, communication and kernel
workspace still required, motivating offload. The existing GB300 TP2 recipe estimates about
189 GiB for CPU Engram; the provisional host guard is 256 GiB MemAvailable, with loading/OS
headroom still required. This guarantees neither two-GPU startup nor full context. Nominal
GB and device-reported MiB must not be treated as measured available capacity.
Vera Rubin NVL72 describes a system; OS visibility determines usable cards, not its 72-GPU name.
Image, platform digest and minimum memory are null, with `planning_only=true` and no executable
engine arguments.

```bash
./local-ai server plan --profile rubin-tp2-framework --host 0.0.0.0 --gpus 0,1 --name a --port 18000 --inventory tests/fixtures/rubin-tp2.json --data-dir /tmp/local-ai-rubin-plan
```

A successful framework plan exits 0 with `deployable=false`, `blockers`, `command=null` and
`spec.args=null`. CPU architecture, card count, duplicate UUIDs and GPU names are still checked;
unknown memory capacity requirements and engine compatibility are not checked. Fixture memory
values are neither requirements nor measurements.

Selecting this framework for server/both install, server start, image pull/export/import,
model download or complete export exits 1 with a not-deployable error, before logging,
GPU/Docker probes, downloads or resource writes. Python operation entry points also refuse.
Clearing planning_only alone leaves missing-field blockers; filling the image alone leaves the
framework flag. Ordinary source/client exports may carry the definition, but cannot select it
as prepared server resources.

## Acceptance after obtaining hardware

Allocate devices and ports, prepare current source in an isolated GPU001 directory, and retain
existing services/configuration. Start with read-only inventory, including for Rubin before
removing deployment restrictions:

```bash
cd /raid/local-ai
./local-ai server inventory
nvidia-smi
nvidia-smi topo -m
nvidia-ctk cdi list
```

1. Record sanitized CPU/OS, GPU names/compute capability, driver, HBM, host memory and NUMA.
   Confirm OS-visible GPUs (four GB200 or two Rubin), complete selected CDI UUIDs, and free devices/ports.
2. Validate CUDA, BF16 and NCCL for the selected card count in an isolated container. Record full image/platform
   digests and CUDA, PyTorch, vLLM, FlashInfer, Triton, DeepGEMM/CUTLASS and NCCL versions.
3. Check the GB200 candidate against real capacity. Validate startup and bounded input before
   expanding context, concurrency and graph capture. For Rubin, define a separate model/hardware
   recipe in a complete external catalog, establish image/memory requirements, kernels and client
   capabilities, then explicitly clear planning_only. Do not borrow a GB300 image digest.
4. Validate weight loading, health, Chinese streaming, reasoning fields and tool round trips.
   Execute hostname, file edits and reads on BCM. API READY alone does not establish these.
5. Record failures, untested limits and rollback before promoting individual validation levels.
   Performance, full context, concurrency, DSpark and sustained stability require separate tests;
   none is established by this CPU work.

Upstream Rubin builds currently have CUDA 13.4, specialized Triton and NCCL requirements.
Older dependency combinations have reported DeepGEMM/CUTLASS assertions with this model;
verify actual image dependencies and fixing commits rather than inferring compatibility from
a platform name. References: [vLLM builds](https://github.com/vllm-project/vllm/blob/main/docs/getting_started/installation/gpu.cuda.inc.md),
[DeepGEMM issue](https://github.com/deepseek-ai/DeepGEMM/issues/461), and
[Rubin reference tray](https://docs.nvidia.com/dgx/dgxvr-user-guide/hardware.html).
The 288GB HBM4 figure comes from [NVIDIA's Vera Rubin NVL72 specifications](https://www.nvidia.com/en-us/data-center/vera-rubin-nvl72/).

External catalogs fully replace built-ins. If an upgraded installation lacks the candidates,
merge using [development](development.md#model-and-client-compatibility). Resource packaging and
actual GPU acceptance remain governed by [offline](offline.md) and [validation](validation.md).

[中文（默认）](../gb200-rubin.md)
