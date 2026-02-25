# Resource Enforcement

Two-layer enforcement architecture: systemd cgroup slices for aggregate per-user limits, Docker flags for per-container limits.

## Architecture

```
┌──────────────────────────────────────────────────┐
│                 Kernel (cgroup v2)                │
│                                                   │
│  ds01.slice                                      │
│  ├── ds01-student.slice                          │
│  │   └── ds01-student-alice.slice  ◄── Layer 1   │
│  │       │  CPUQuota=9600%                       │
│  │       │  MemoryMax=96G                        │
│  │       │  TasksMax=12288                       │
│  │       │                                       │
│  │       ├── docker-abc.scope  ◄── Layer 2       │
│  │       │   --cpus=32 --memory=32g              │
│  │       └── docker-def.scope                    │
│  │           --cpus=32 --memory=32g              │
│  └── ds01-researcher.slice                       │
│      └── ...                                     │
└──────────────────────────────────────────────────┘
```

## Layer 1: Aggregate Limits (Systemd Slices)

Per-user systemd slices enforce total resource consumption across all containers.

**Limit calculation:** `per_container_limit × max_containers_per_user`

| Resource | Mechanism | Example (student, 3 containers) |
|----------|-----------|--------------------------------|
| CPU | `CPUQuota` | 32 × 3 = 9600% (96 CPUs) |
| Memory (hard) | `MemoryMax` | 32G × 3 = 96G |
| Memory (soft) | `MemoryHigh` | 90% of MemoryMax = 86G |
| PIDs | `TasksMax` | 4096 × 3 = 12288 |

**Implementation:**
- Generator: `scripts/system/generate-user-slice-limits.py`
- Creates drop-in files at `/etc/systemd/system/ds01-{group}-{user}.slice.d/10-resource-limits.conf`
- Idempotent: skips unchanged configs, removes stale ones
- Triggered by: `deploy.sh`, `setup-resource-slices.sh`, `create-user-slice.sh`

**Admin group exception:** No aggregate limits. Systemd convention: absence of limit = no enforcement.

## Layer 2: Per-Container Limits (Docker)

Docker wrapper injects resource flags on container creation:
- `--cpus=32` (from `max_cpus`)
- `--memory=32g` (from `memory`)
- `--memory-swap=32g` (from `memory_swap`)
- `--shm-size=16g` (from `shm_size`)
- `--pids-limit=4096` (from `pids_limit`)
- `--cgroup-parent=ds01-{group}-{user}.slice`

## Pre-Creation Quota Check

Before GPU allocation, the Docker wrapper checks aggregate quotas:

1. **Memory:** Read current usage from cgroup `memory.current`. Calculate projected usage with new container. Reject if exceeds `aggregate.memory_max`.
2. **GPU:** Count current GPU allocations. Reject if adding new container exceeds `aggregate.gpu_limit`.
3. **PIDs:** Soft warning at 90% of `aggregate.tasks_max`. Does not block creation.
4. **CPU:** No pre-check (kernel enforces continuously via CPUQuota).

## Deferred Enforcement

| Resource | Status | Blocker |
|----------|--------|---------|
| I/O bandwidth | Deferred | Requires BFQ scheduler (currently mq-deadline) |
| Disk quota | Deferred | Requires XFS migration (currently ext4) |
| Network bandwidth | Deferred | Not relevant until multi-node or network contention |
| Fair-share GPU scheduling | Deferred | Relevant for SLURM integration (M4) |

## Configuration

All limits in `config/runtime/resource-limits.yaml`:

```yaml
groups:
  student:
    max_cpus: 32
    memory: 32g
    pids_limit: 4096
    max_containers_per_user: 3
    aggregate:
      cpu_quota: "9600%"
      memory_max: "96G"
      memory_high: "86G"
      tasks_max: 12288
      gpu_limit: 3
```

Changes to runtime config take effect immediately — no restart needed. Aggregate slice limits require `deploy.sh` or `create-user-slice.sh` to regenerate drop-ins.
