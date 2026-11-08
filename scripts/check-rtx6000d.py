"""Run inside the pinned GPU image with torchrun; no weights required."""

import os
from datetime import timedelta

import torch
import torch.distributed as dist

rank = int(os.environ["LOCAL_RANK"])
device = torch.device("cuda", rank)
torch.cuda.set_device(device)
dist.init_process_group("nccl", timeout=timedelta(seconds=120), device_id=device)
for size in [1, 1024, 1048576]:
    tensor = torch.full((size,), rank + 1, device=device, dtype=torch.float32)
    dist.all_reduce(tensor)
    torch.cuda.synchronize(device)
    assert bool(torch.all(tensor == 36)), (rank, size, tensor[0].item())
os.write(1, ("NCCL rank %d PASS\n" % rank).encode())
dist.barrier(device_ids=[rank])
dist.destroy_process_group()
