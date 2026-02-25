# GPU Allocation Flow

How GPU resources are requested, validated, allocated, and released.

## Overview

GPU allocation follows a request → validate → lock → allocate → label flow. The allocator is stateless — Docker container labels are the source of truth, read fresh on each operation.

## Flow Diagram

```
User runs: docker run --gpus all myimage
         │
         ▼
┌─────────────────────────┐
│    Docker Wrapper        │  /usr/local/bin/docker
│  (docker-wrapper.sh)     │
│                          │
│  1. Detect --gpus flag   │
│  2. Read user limits     │
│  3. Check aggregate      │
│     quota (memory, GPU)  │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  GPU Allocator           │  gpu_allocator_v2.py
│                          │
│  1. Acquire file lock    │
│     (5s SIGALRM timeout) │
│  2. Read current state   │
│     from Docker labels   │
│  3. Check per-user quota │
│     (max_mig_instances)  │
│  4. Find available GPU   │
│  5. Return device ID     │
│  6. Release lock         │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Wrapper continues       │
│                          │
│  1. Rewrite --gpus all   │
│     → --gpus device=UUID │
│  2. Inject labels:       │
│     ds01.user, ds01.managed │
│     ds01.gpu.uuids       │
│  3. Inject --cgroup-parent │
│  4. Call real docker      │
└──────────┬──────────────┘
           │
           ▼
┌─────────────────────────┐
│  Container Created       │
│                          │
│  Owner tracker detects   │
│  event, updates          │
│  container-owners.json   │
└─────────────────────────┘
```

## Key Components

| Component | File | Role |
|-----------|------|------|
| Docker wrapper | `scripts/docker/docker-wrapper.sh` | Intercepts docker commands, orchestrates allocation |
| GPU allocator | `scripts/docker/gpu_allocator_v2.py` | Stateless allocation with file locking |
| State reader | `scripts/docker/gpu-state-reader.py` | Reads current GPU state from Docker labels |
| Availability checker | `scripts/docker/gpu-availability-checker.py` | Checks GPU availability against quotas |
| Resource limits parser | `scripts/docker/get_resource_limits.py` | Reads per-user limits from resource-limits.yaml |

## MIG Instance Tracking

GPUs are tracked as `physical_gpu:instance` notation (e.g., `0:1`, `2:3`). When MIG is enabled, each physical GPU is partitioned into instances. The allocator tracks instance-level allocation.

When MIG is disabled, GPUs are tracked as whole devices (`0`, `1`, `2`, `3`).

## Quota Enforcement (Two Layers)

1. **Aggregate GPU quota** (`aggregate.gpu_limit`): Total MIG instances across all of a user's containers. Checked in Docker wrapper before allocation attempt.
2. **Per-container quota** (`max_mig_per_container`): Maximum instances in a single container. Checked in GPU allocator.

## Release Flow

```
Container stops
    │
    ▼ (gpu_hold_after_stop elapsed, default 15min)
cleanup-stale-gpu-allocations.sh (cron :15/hour)
    │
    ├── Read stopped containers with GPU labels
    ├── Check stop timestamp vs hold timeout
    ├── Release GPU allocation
    └── Run GPU health verification (SLURM epilog pattern)
    │
    ▼ (container_hold_after_stop elapsed, default 30min)
cleanup-stale-containers.sh (cron :00/hour)
    │
    └── docker rm <container>
```

## Error Handling

- **Lock timeout (5s):** Fail-open — proceed without lock, log warning. Risk of rare double-allocation, corrected by periodic sync.
- **Allocator crash:** Wrapper catches exception, shows error to user, does not create container.
- **State reader failure:** Allocator falls back to empty state (conservative — may reject valid allocation, but never double-allocates).
- **Config read failure:** Safe defaults applied for user's group.

## Configuration

All allocation parameters in `config/runtime/resource-limits.yaml`:
- `defaults.max_mig_instances` — per-container default
- `groups.<group>.max_mig_instances` — per-group override
- `groups.<group>.aggregate.gpu_limit` — aggregate per-user cap
- `user_overrides.<user>.max_mig_instances` — per-user exception
