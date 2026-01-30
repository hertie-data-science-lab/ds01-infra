# Architecture Research

**Domain:** Multi-user GPU Container Management Platform Evolution
**Researched:** 2026-01-30
**Confidence:** HIGH

## Current Architecture (As-Built)

DS01 uses a **5-layer enforcement architecture** with systemd cgroup hierarchy and universal Docker wrapper interception.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                         CURRENT DS01 ARCHITECTURE                        │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  L5: WIZARDS (user-setup, project-init, project-launch)                 │
│       │                                                                  │
│       ▼                                                                  │
│  L4: ORCHESTRATORS (container deploy, container retire)                 │
│       │                                                                  │
│       ▼                                                                  │
│  L3: ATOMIC COMMANDS (container-create, container-stop, etc.)           │
│       │                                                                  │
│       ▼                                                                  │
│  L2: DOCKER WRAPPER (/usr/local/bin/docker) ◄──┐                        │
│       │                                         │                        │
│       │  ┌──────────────────────────────────┐  │                        │
│       │  │ UNIVERSAL INTERCEPTION           │  │                        │
│       │  │ • Injects cgroup-parent          │  │ Intercepts ALL:       │
│       │  │ • Adds ds01.* labels             │  │ - Dev containers      │
│       │  │ • Calls GPU allocator            │  │ - docker-compose      │
│       │  │ • Rewrites --gpus all → device   │  │ - Raw docker run      │
│       │  └──────────────────────────────────┘  │                        │
│       │                                         │                        │
│       ▼                                         │                        │
│  L1: AIME ML CONTAINERS (mlc-patched.py)       │                        │
│       │                                         │                        │
│       ▼                                         │                        │
│  L0: REAL DOCKER (/usr/bin/docker) ◄───────────┘                        │
│       │                                                                  │
│       ▼                                                                  │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │              SYSTEMD CGROUP HIERARCHY                             │  │
│  │                                                                   │  │
│  │  ds01.slice/                                                     │  │
│  │  ├── ds01-student.slice/                                         │  │
│  │  │   ├── ds01-student-alice.slice/                              │  │
│  │  │   │   └── docker-<id>.scope  (alice's containers)            │  │
│  │  │   └── ds01-student-bob.slice/                                │  │
│  │  │       └── docker-<id>.scope                                  │  │
│  │  ├── ds01-researcher.slice/                                     │  │
│  │  │   └── ds01-researcher-charlie.slice/                         │  │
│  │  └── ds01-admin.slice/                                          │  │
│  │      └── ds01-admin-dana.slice/                                 │  │
│  │                                                                   │  │
│  │  Resource limits enforced at slice level:                        │  │
│  │  • CPUQuota, MemoryMax (currently implemented)                   │  │
│  │  • IOWeight, IOReadBandwidthMax (NOT yet implemented)            │  │
│  │  • TasksMax (NOT yet implemented)                                │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │              GPU ALLOCATION STATE                                 │  │
│  │  /var/lib/ds01/gpu-state.json (file locking for atomicity)       │  │
│  │  {                                                                │  │
│  │    "gpu_0": {"user": "alice", "container": "ml-train"},          │  │
│  │    "gpu_1": null,                                                 │  │
│  │    "gpu_2.0": {"user": "bob", "container": "dev"}  # MIG         │  │
│  │  }                                                                │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
│  ┌───────────────────────────────────────────────────────────────────┐  │
│  │              LIFECYCLE ENFORCEMENT (CRON)                         │  │
│  │  • check-idle-containers.sh (every 30m)                           │  │
│  │  • enforce-max-runtime.sh (every hour at :45)                     │  │
│  │  • cleanup-stale-gpu-allocations.sh (every hour at :15)           │  │
│  │  • cleanup-stale-containers.sh (every hour at :00)                │  │
│  └───────────────────────────────────────────────────────────────────┘  │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Key Architectural Properties

| Property | Current State | Notes |
|----------|---------------|-------|
| **Container awareness** | DS01-created only | Wrapper intercepts external, but no retroactive discovery |
| **GPU tracking** | Container-based | Host GPU processes invisible |
| **Resource enforcement** | CPU + Memory | IO and disk limits not implemented |
| **User isolation** | Systemd cgroups | OPA attempted but failed; cgroups work but incomplete |
| **Monitoring** | Prometheus/Grafana deployed | DCGM + DS01 Exporter hybrid architecture |
| **Event logging** | Implemented but empty | `/var/log/ds01/events.jsonl` has 0 lines |

### Critical Assumption

**DS01 assumes it created all containers.** Three bypass paths break this:
1. **Dev containers** - VS Code creates via Docker API, not DS01 commands
2. **Raw docker** - Users with docker group can `docker run` directly
3. **Host GPU processes** - Python scripts on bare metal using CUDA

Docker wrapper catches (1) and (2) at creation time, but if containers exist before wrapper deployment, they're invisible. Problem (3) is completely unaddressed.

## Recommended Evolution Architecture

Evolve to **awareness-first architecture** where DS01 discovers reality, then enforces policy.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                    EVOLVED DS01 ARCHITECTURE                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                 AWARENESS LAYER (NEW)                              │ │
│  │                                                                    │ │
│  │  Discovery Subsystem:                                             │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────┐ │ │
│  │  │ Container        │  │ Host Process     │  │ Docker Events   │ │ │
│  │  │ Scanner          │  │ Scanner          │  │ Listener        │ │ │
│  │  │                  │  │                  │  │                 │ │ │
│  │  │ docker ps -a     │  │ nvidia-smi pmon  │  │ docker events   │ │ │
│  │  │ + label inspect  │  │ + /proc/<pid>    │  │ (real-time)     │ │ │
│  │  │ (all containers) │  │ (user mapping)   │  │                 │ │ │
│  │  └────────┬─────────┘  └────────┬─────────┘  └────────┬────────┘ │ │
│  │           │                     │                     │          │ │
│  │           └─────────────────────┼─────────────────────┘          │ │
│  │                                 ▼                                │ │
│  │                    ┌─────────────────────────┐                   │ │
│  │                    │ Unified Resource State  │                   │ │
│  │                    │ /var/lib/ds01/          │                   │ │
│  │                    │ • containers.json       │                   │ │
│  │                    │ • host-processes.json   │                   │ │
│  │                    │ • gpu-allocations.json  │                   │ │
│  │                    └─────────────────────────┘                   │ │
│  │                                                                    │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                 │                                       │
│                                 ▼                                       │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                 ENFORCEMENT LAYER                                  │ │
│  │                                                                    │ │
│  │  Policy Engine:                                                   │ │
│  │  ┌──────────────────┐  ┌──────────────────┐  ┌─────────────────┐ │ │
│  │  │ Quota Enforcer   │  │ Lifecycle Mgr    │  │ Isolation Guard │ │ │
│  │  │                  │  │                  │  │                 │ │ │
│  │  │ Checks resource  │  │ Idle timeout     │  │ Prevents cross- │ │ │
│  │  │ usage vs limits  │  │ Max runtime      │  │ user interference│ │ │
│  │  │ (GPU,CPU,IO,disk)│  │ Auto-cleanup     │  │ (cgroups+labels)│ │ │
│  │  └──────────────────┘  └──────────────────┘  └─────────────────┘ │ │
│  │                                                                    │ │
│  │  Enforcement Mechanisms:                                          │ │
│  │  • Systemd cgroup limits (CPU, memory, IO, disk, tasks)          │ │
│  │  • Docker wrapper interception (GPU rewrite, label injection)     │ │
│  │  • Container action restrictions (docker CLI authorization)       │ │
│  │  • Host process termination (for bare metal GPU violations)       │ │
│  │                                                                    │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                 │                                       │
│                                 ▼                                       │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │                 OBSERVABILITY LAYER                                │ │
│  │                                                                    │ │
│  │  ┌──────────────────────────────────────────────────────────────┐ │ │
│  │  │ Prometheus Stack                                             │ │ │
│  │  │  ┌────────────┐  ┌────────────┐  ┌────────────┐             │ │ │
│  │  │  │ DCGM       │  │ DS01       │  │ Node       │             │ │ │
│  │  │  │ Exporter   │  │ Exporter   │  │ Exporter   │             │ │ │
│  │  │  │            │  │            │  │            │             │ │ │
│  │  │  │ GPU hw     │  │ Allocations│  │ CPU/Mem/IO │             │ │ │
│  │  │  │ metrics    │  │ Users      │  │ system     │             │ │ │
│  │  │  └─────┬──────┘  └─────┬──────┘  └─────┬──────┘             │ │ │
│  │  │        └────────────────┼────────────────┘                   │ │ │
│  │  │                         ▼                                    │ │ │
│  │  │              ┌─────────────────────┐                         │ │ │
│  │  │              │ Prometheus          │                         │ │ │
│  │  │              │ • 7-day retention   │                         │ │ │
│  │  │              │ • Recording rules   │                         │ │ │
│  │  │              │ • Alert rules       │                         │ │ │
│  │  │              └──────────┬──────────┘                         │ │ │
│  │  │                         │                                    │ │ │
│  │  │        ┌────────────────┴────────────────┐                   │ │ │
│  │  │        ▼                                 ▼                   │ │ │
│  │  │  ┌─────────────┐                  ┌─────────────┐           │ │ │
│  │  │  │ Grafana     │                  │ Alertmanager│           │ │ │
│  │  │  │ Dashboards  │                  │ Email/Teams │           │ │ │
│  │  │  └─────────────┘                  └─────────────┘           │ │ │
│  │  └──────────────────────────────────────────────────────────────┘ │ │
│  │                                                                    │ │
│  │  ┌──────────────────────────────────────────────────────────────┐ │ │
│  │  │ Event & Audit System (NEW)                                   │ │ │
│  │  │  • Docker events stream → structured logging                 │ │ │
│  │  │  • All enforcement actions logged                            │ │ │
│  │  │  • Historical analytics (usage patterns, demand trends)      │ │ │
│  │  │  • Compliance audit trail                                    │ │ │
│  │  └──────────────────────────────────────────────────────────────┘ │ │
│  │                                                                    │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │              EXISTING L0-L5 COMMAND HIERARCHY                      │ │
│  │  (Unchanged - continues to work, now informed by awareness layer)  │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│                                                                          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Evolution Principles

1. **Non-Breaking:** Existing 5-layer hierarchy untouched; awareness layer sits underneath
2. **Discovery-First:** System discovers reality (containers, processes), then applies policy
3. **Comprehensive Enforcement:** Extend systemd cgroup controls to IO, disk, tasks
4. **Event-Driven:** Real-time Docker events stream replaces polling where possible
5. **Operational Maturity:** Full observability with historical analytics and alerting

## Component Boundaries

### 1. Awareness Layer (NEW)

| Component | Responsibility | Data Source | Output |
|-----------|---------------|-------------|--------|
| **Container Scanner** | Discover all containers (managed + unmanaged) | `docker ps -a` + label inspection | `/var/lib/ds01/containers.json` |
| **Host Process Scanner** | Detect bare-metal GPU processes | `nvidia-smi pmon` + `/proc/<pid>/status` | `/var/lib/ds01/host-processes.json` |
| **Docker Events Listener** | Real-time container lifecycle tracking | `docker events` stream | Updates to state files + event log |
| **User Attribution Engine** | Map processes → users | Labels, /proc, cgroup membership | Enriched state with ownership |

**Integration point:** Runs as systemd service, updates state files atomically (file locking), consumed by enforcement layer and exporters.

### 2. Enforcement Layer (ENHANCED)

| Component | Current State | Evolution |
|-----------|---------------|-----------|
| **Docker Wrapper** | Intercepts run/create, injects cgroups+labels+GPU | Add authorization checks (prevent alice from `docker stop bob-container`) |
| **GPU Allocator** | Allocates at creation, releases on stop | Extend to track host processes, enforce limits on bare metal |
| **Systemd Cgroup Manager** | CPU + Memory limits | Add IO, disk quota, task limits via `IOWeight`, `IOReadBandwidthMax`, `TasksMax` |
| **Lifecycle Enforcer** | Cron jobs (idle timeout, max runtime, cleanup) | Migrate to event-driven triggers where possible |
| **User Isolation** | Cgroups + labels | Add Docker CLI authorization (wrapper checks if user owns target container) |

**Integration point:** Reads unified state, applies policy, logs actions to event system.

### 3. Observability Layer (ENHANCED)

| Component | Current State | Evolution |
|-----------|---------------|-----------|
| **DCGM Exporter** | GPU hardware metrics | No change (working well) |
| **DS01 Exporter** | GPU allocations + container counts | Add host process metrics, unmanaged container tracking |
| **Prometheus** | 7-day retention, basic alerts | Add recording rules for historical analytics (30d, 1y aggregations) |
| **Grafana** | 3 dashboards (overview, user, DCGM) | Add operational dashboard (cleanup stats, lifecycle events) |
| **Alertmanager** | Deployed but not configured | Configure email routing, silence management |
| **Event Log System** | Empty (0 lines) | Populate via Docker events listener + enforcement action logging |

**Integration point:** Exporters scrape state files, Prometheus queries exporters, Grafana visualizes.

### 4. Existing L0-L5 Hierarchy (UNCHANGED)

Wizards, orchestrators, atomic commands, AIME, Docker wrapper, Docker remain intact. They now:
- Benefit from awareness layer (better error messages: "GPU in use by alice's jupyter")
- Contribute to observability (actions logged to event system)
- Enforce richer policies (IO limits configured in resource-limits.yaml)

## Data Flow Architecture

### Creation Flow (Container with GPU)

```
User runs: project-launch (L5)
    ↓
Orchestrator: container deploy (L4)
    ↓
Atomic: container-create (L3)
    ↓
Docker wrapper intercepts (L2)
    │
    ├→ [NEW] Check awareness state: any unmanaged containers by this user?
    ├→ Get resource limits (CPU, memory, IO, disk, GPU)
    ├→ Ensure user slice exists with systemd limits applied
    ├→ Allocate GPU via gpu_allocator_v2.py
    │   └→ [NEW] Check host process scanner: GPU already in use on bare metal?
    ├→ Inject cgroup-parent, labels
    ↓
Real Docker creates container (L0)
    ↓
[NEW] Docker Events Listener sees 'container:start' event
    ↓
Updates /var/lib/ds01/containers.json
Logs to /var/log/ds01/events.jsonl
Triggers DS01 Exporter metric update
```

### Discovery Flow (Unmanaged Container)

```
System Boot / Scanner Run
    ↓
Container Scanner: docker ps -a
    │
    ├→ For each container:
    │   ├→ Inspect labels (ds01.user, ds01.managed, devcontainer.*)
    │   ├→ Check cgroup membership → extract user
    │   ├→ Fallback: /proc/<pid>/status → UID → username
    │   └→ Classify: managed, unmanaged-devcontainer, unmanaged-docker, unknown
    │
    └→ Write /var/lib/ds01/containers.json (atomic)

Host Process Scanner: nvidia-smi pmon
    │
    ├→ For each GPU process:
    │   ├→ Get PID
    │   ├→ Read /proc/<pid>/status → UID
    │   ├→ Map UID → username
    │   └→ Check against user GPU quota
    │
    └→ Write /var/lib/ds01/host-processes.json (atomic)

[If violations detected]
    ↓
Policy Engine: check quotas
    ↓
[Action based on policy]
    ├→ Alert only (grace period)
    ├→ Terminate process (kill <pid>)
    └→ Log to event system
```

### Enforcement Flow (Lifecycle)

```
Docker Events Listener (real-time)
    ↓
Event: container stops
    ↓
Update state: mark container as stopped, timestamp
    ↓
[After gpu_hold_after_stop duration]
    ↓
GPU Allocator: release GPU
    ↓
[After container_hold_after_stop duration]
    ↓
Cleanup: docker rm <container>
    ↓
Log all actions to event system
    ↓
Metrics updated in real-time (not polled)
```

### Observability Flow

```
┌─────────────────┐
│ State Files     │ Scraped every 15-30s
│ /var/lib/ds01/  ├─────────────────────┐
└─────────────────┘                     │
                                        ▼
                              ┌──────────────────┐
                              │ DS01 Exporter    │
                              │ :9101            │
                              └────────┬─────────┘
                                       │
┌─────────────────┐                   │
│ DCGM (GPU hw)   ├───────────────────┤
│ :9400           │                   │
└─────────────────┘                   │
                                      ▼
┌─────────────────┐         ┌──────────────────┐
│ Node Exporter   ├────────►│ Prometheus       │
│ :9100           │         │ :9090            │
└─────────────────┘         └────────┬─────────┘
                                     │
                    ┌────────────────┴────────────────┐
                    ▼                                 ▼
          ┌──────────────────┐            ┌──────────────────┐
          │ Grafana          │            │ Alertmanager     │
          │ :3000            │            │ :9093            │
          │                  │            │                  │
          │ Dashboards:      │            │ Routes:          │
          │ • Overview       │            │ • Email          │
          │ • My Usage       │            │ • Teams webhooks │
          │ • DCGM Hardware  │            │ • Silencing      │
          │ • Operations     │            └──────────────────┘
          │ • Historical     │
          └──────────────────┘
```

## Comprehensive Resource Enforcement

Extend systemd cgroup controls beyond CPU/Memory to full resource spectrum.

### Systemd Resource Control Directives

| Resource | Directive | Purpose | DS01 Application |
|----------|-----------|---------|------------------|
| **CPU** | `CPUQuota=50%` | Limit CPU time percentage | ✓ Currently implemented |
| **CPU** | `CPUWeight=100` | Relative CPU scheduling weight | Consider for priority users |
| **Memory** | `MemoryMax=16G` | Hard memory limit (OOM kill) | ✓ Currently implemented |
| **Memory** | `MemoryHigh=14G` | Soft limit (throttling before OOM) | Add for better UX |
| **IO** | `IOWeight=100` | Relative IO scheduling weight (1-10000) | **Implement** for fair disk access |
| **IO** | `IOReadBandwidthMax=/dev/sda 50M` | Cap read bandwidth per device | **Implement** to prevent disk monopolization |
| **IO** | `IOWriteBandwidthMax=/dev/sda 50M` | Cap write bandwidth per device | **Implement** for fairness |
| **IO** | `IOReadIOPSMax=/dev/sda 1000` | Limit read IOPS | Consider for database workloads |
| **Tasks** | `TasksMax=512` | Max processes/threads per user | **Implement** to prevent fork bombs |
| **Disk** | Requires quota tools | Disk space limits | Needs separate quota subsystem |

**Implementation approach:**

```bash
# Example: /etc/systemd/system/ds01-student-alice.slice.d/limits.conf
[Slice]
CPUQuota=200%
MemoryMax=32G
MemoryHigh=28G
IOWeight=100
IOReadBandwidthMax=/dev/nvme0n1 100M
IOWriteBandwidthMax=/dev/nvme0n1 100M
TasksMax=1024
```

Applied dynamically based on `config/resource-limits.yaml`:

```yaml
defaults:
  cpu_quota: "200%"
  memory_max: "32G"
  io_read_bw_max: "100M"
  io_write_bw_max: "100M"
  tasks_max: 1024
```

**Sources:**
- [systemd.resource-control documentation](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html) — authoritative reference for all cgroup v2 directives
- [Red Hat cgroup limits guide](https://access.redhat.com/solutions/3949221) — IO bandwidth configuration examples
- [cgroup2 IO controller](https://facebookmicrosites.github.io/cgroup2/docs/io-controller.html) — technical details on IO control mechanisms

**Confidence: HIGH** — systemd cgroup v2 is mature, well-documented, and already in use for CPU/memory.

## User Isolation Without OPA

OPA (Open Policy Agent) was attempted but caused problems. Alternative approaches for multi-user isolation:

### Approach 1: Docker Wrapper Authorization (RECOMMENDED)

Extend existing Docker wrapper to authorize container operations.

```bash
# In docker-wrapper.sh, before passing to real Docker:

case "$1" in
    stop|kill|rm|exec|attach|logs)
        CONTAINER_ID="$2"
        CONTAINER_USER=$(docker inspect --format '{{.Config.Labels.ds01.user}}' "$CONTAINER_ID" 2>/dev/null)

        if [[ "$CONTAINER_USER" != "$CURRENT_USER" ]] && [[ "$CURRENT_USER" != "root" ]]; then
            echo "Error: You don't own container $CONTAINER_ID (owned by $CONTAINER_USER)"
            exit 1
        fi
        ;;
esac
```

**Pros:**
- Reuses existing wrapper infrastructure
- No new dependencies
- Simple to understand and audit
- Leverages ds01.user labels already being injected

**Cons:**
- Bypassable if user has access to real `/usr/bin/docker`
- Requires docker group users to use wrapper

**Mitigation:** Remove users from docker group, provide sudo access to wrapper only.

### Approach 2: Rootless Containers (Podman/Docker Rootless)

Run containers as unprivileged users with user namespaces.

**Technology:** [Podman](https://podman.io/) or [Docker Rootless mode](https://docs.docker.com/engine/security/rootless/)

**How it works:**
- Each user runs their own container runtime daemon
- Containers run in user namespace (UID 0 inside → user's UID outside)
- Kernel enforces isolation (even if container escapes, limited to user's permissions)

**Pros:**
- True kernel-level isolation
- No trust in userspace policy enforcement
- Industry standard for multi-tenant environments

**Cons:**
- Requires migration from current Docker daemon model
- Some features limited in rootless mode (privileged ports, certain volume mounts)
- GPU access more complex (needs cgroup delegation, device permissions)

**Assessment:** Overkill for DS01's trust model (university users, not hostile multi-tenancy). Consider for future.

### Approach 3: Enhanced Cgroup Isolation

Use systemd cgroup delegation with restricted permissions.

**Technology:** [systemd cgroup delegation](https://systemd.io/CGROUP_DELEGATION/)

**How it works:**
- Each user gets delegated cgroup subtree they control
- User can only manipulate processes within their subtree
- Systemd enforces boundaries

**Pros:**
- Leverages existing cgroup infrastructure
- No application-level policy needed
- Kernel-enforced boundaries

**Cons:**
- Requires users to manage cgroups directly (high complexity)
- Docker doesn't naturally fit this model (daemon runs as root)

**Assessment:** Interesting but requires fundamental redesign.

### Approach 4: Container Runtime Interception (gVisor/Kata)

Use hardened container runtimes with VM-level isolation.

**Technologies:**
- [gVisor](https://gvisor.dev/) — user-space kernel that intercepts syscalls
- [Kata Containers](https://katacontainers.io/) — lightweight VMs per container

**Pros:**
- Strongest isolation (even if container escapes, contained to VM/gVisor sandbox)
- Reduces kernel attack surface

**Cons:**
- Significant performance overhead (10-30% for gVisor)
- GPU passthrough complex (Kata requires VFIO, gVisor doesn't support GPUs well)
- Heavy dependency addition

**Assessment:** Inappropriate for GPU workloads. Performance overhead unacceptable.

### Recommendation: Docker Wrapper Authorization

**For DS01, extend existing Docker wrapper with authorization checks.**

Rationale:
1. **Already have wrapper infrastructure** — small incremental change
2. **Trust model appropriate** — university users, not hostile actors
3. **GPU compatibility** — no issues with direct GPU access
4. **Operationally simple** — single admin can understand and maintain
5. **Backward compatible** — existing containers continue working

**Implementation roadmap:**
1. Add authorization checks to wrapper for stop/kill/rm/exec operations
2. Audit docker group membership — remove users, provide sudo wrapper access
3. Add monitoring for bypass attempts (direct /usr/bin/docker usage)
4. Document escape paths honestly, accept residual risk

**Future migration path:** If multi-tenancy requirements increase, migrate to Podman rootless or Kubernetes RBAC.

**Sources:**
- [Podman security features](https://signoz.io/comparisons/docker-alternatives/) — rootless containers overview
- [gVisor kernel interception](https://cybersecuritynews.com/docker-monitoring-tools/) — mentions gVisor as isolation technology
- [systemd cgroup delegation guide](https://systemd.io/CGROUP_DELEGATION/) — authoritative systemd documentation
- [Kata Containers for multi-tenancy](https://signoz.io/comparisons/docker-alternatives/) — VM-based container isolation

**Confidence: MEDIUM** — wrapper approach is pragmatic but relies on userspace enforcement. Rootless containers are proven but complex to deploy with GPUs.

## Monitoring & Observability Integration

DS01 has **hybrid DCGM + DS01 Exporter architecture** already deployed. Evolution focuses on completeness and operational maturity.

### Current State Analysis

**Working well:**
- DCGM Exporter provides sub-second GPU hardware metrics (utilization, memory, temperature, power)
- DS01 Exporter provides allocation/business metrics (who owns which GPU, container counts)
- Grafana dashboards for overview, per-user usage, and detailed DCGM metrics
- Prometheus with 7-day retention and basic alert rules

**Gaps:**
- Event log empty (0 lines in `/var/log/ds01/events.jsonl`)
- No historical analytics beyond 7 days (can't answer "GPU usage last semester")
- Alertmanager deployed but not configured (no email routing)
- No operational dashboards (cleanup stats, lifecycle enforcement)
- Exporters occasionally crash (stability issues noted)

### Evolution Strategy

**Phase 1: Event System Foundation**

Implement Docker events listener as systemd service.

```python
# /opt/ds01-infra/scripts/monitoring/docker-events-daemon.py
import docker
import json
from datetime import datetime

client = docker.from_env()
event_log = open('/var/log/ds01/events.jsonl', 'a')

for event in client.events(decode=True):
    if event['Type'] == 'container':
        log_entry = {
            'timestamp': datetime.utcnow().isoformat(),
            'type': f"container.{event['Action']}",
            'container_id': event['Actor']['ID'][:12],
            'user': event['Actor']['Attributes'].get('ds01.user', 'unknown'),
            'container_type': event['Actor']['Attributes'].get('ds01.container_type', 'unknown'),
            'image': event['Actor']['Attributes'].get('image', 'unknown')
        }
        event_log.write(json.dumps(log_entry) + '\n')
        event_log.flush()
```

**Benefits:**
- Real-time event stream instead of polling
- Complete audit trail
- Foundation for event-driven enforcement

**Phase 2: Historical Analytics**

Add Prometheus recording rules for long-term aggregations.

```yaml
# prometheus/rules/ds01_recording.yml
groups:
  - name: ds01_historical
    interval: 1h
    rules:
      # Daily aggregations
      - record: ds01:gpu_utilization:avg_1d
        expr: avg_over_time(DCGM_FI_DEV_GPU_UTIL[1d])

      # Weekly aggregations
      - record: ds01:gpu_hours:user:week
        expr: sum by (user) (ds01_gpu_allocated * 24 * 7)

      # Monthly aggregations
      - record: ds01:gpu_hours:total:month
        expr: sum(ds01_gpu_allocated) * 24 * 30
```

External storage for >7 days (options):
1. **Prometheus remote write** → InfluxDB/VictoriaMetrics (long-term storage)
2. **Periodic metric export** → CSV files for analysis
3. **Thanos** → distributed Prometheus with object storage backend

**Recommendation:** Start with periodic CSV exports (simple, no new dependencies), upgrade to Thanos if demand materializes.

**Phase 3: Operational Dashboards**

Add Grafana dashboard for lab manager operational view.

Panels:
- **Cleanup stats:** Containers retired in last 24h, GPU hours reclaimed
- **Lifecycle events:** Idle timeouts triggered, max runtime violations
- **User activity:** Active users, new containers created
- **System health:** Exporter uptime, cron job success rate
- **Quota violations:** Users approaching limits

**Phase 4: Alerting Configuration**

Configure Alertmanager with email routing.

```yaml
# alertmanager/alertmanager.yml
global:
  smtp_smarthost: 'smtp.hertie-school.org:587'
  smtp_from: 'ds01-alerts@hertie-school.org'
  smtp_auth_username: 'ds01-alerts@hertie-school.org'
  smtp_auth_password: '<password>'
  smtp_require_tls: true

route:
  receiver: 'lab-manager'
  routes:
    # Critical: immediate email
    - match:
        severity: critical
      receiver: 'lab-manager'
      repeat_interval: 1h

    # Warning: email daily digest
    - match:
        severity: warning
      receiver: 'lab-manager'
      repeat_interval: 24h

receivers:
  - name: 'lab-manager'
    email_configs:
      - to: 'lab-manager@hertie-school.org'
```

**Sources:**
- [Docker events API documentation](https://docs.docker.com/reference/cli/docker/system/events/) — official Docker events reference
- [Prometheus Alertmanager configuration](https://prometheus.io/docs/alerting/latest/alertmanager/) — authoritative Alertmanager docs
- [Docker monitoring with Wazuh](https://documentation.wazuh.com/current/proof-of-concept-guide/monitoring-docker.html) — event monitoring patterns

**Confidence: HIGH** — Docker events API is stable, Prometheus recording rules are standard practice.

## Build Order & Dependencies

Implementation phases ordered by dependency relationships.

### Phase 1: Foundation (Weeks 1-2)

**What:** Fix event logging, stabilize monitoring stack

**Components:**
1. Docker events listener daemon (systemd service)
2. Event log population (backfill from Docker history if possible)
3. DCGM exporter stability fixes (restart policies, resource limits)
4. Alertmanager email configuration

**Dependencies:** None (pure additions)

**Validation:** Event log grows, exporters stay up, test alerts received

**Why first:** Observability must work before adding complexity. Can't debug what you can't see.

### Phase 2: Awareness (Weeks 3-4)

**What:** Discover all GPU-using workloads (containers + host processes)

**Components:**
1. Container scanner (docker ps -a + label inspection)
2. Host process scanner (nvidia-smi pmon + /proc/<pid> user mapping)
3. Unified state files (/var/lib/ds01/containers.json, host-processes.json)
4. DS01 Exporter updates to expose unmanaged workloads

**Dependencies:** Phase 1 (event logging for audit trail)

**Validation:**
- Unmanaged containers appear in Grafana
- Host GPU processes visible in metrics
- State files update in real-time

**Why second:** Can't enforce what you can't see. Awareness before enforcement.

### Phase 3: Comprehensive Enforcement (Weeks 5-7)

**What:** Extend systemd cgroups to IO/disk/tasks, add wrapper authorization

**Components:**
1. Update resource-limits.yaml schema (add IO, tasks config)
2. Update create-user-slice.sh to apply new limits
3. Extend Docker wrapper with authorization checks (stop/kill/exec)
4. Policy engine for host process violations (alert vs kill)

**Dependencies:** Phase 2 (needs container ownership data)

**Validation:**
- IO bandwidth limits visible in systemd slice config
- Cross-user container operations blocked
- Host process quota violations detected

**Why third:** Enforcement requires awareness data. Gradual rollout (alert-only first).

### Phase 4: Operational Maturity (Weeks 8-10)

**What:** Historical analytics, operational dashboards, automation

**Components:**
1. Prometheus recording rules for daily/weekly/monthly aggregations
2. Operational Grafana dashboard (cleanup stats, lifecycle events)
3. Automated cleanup improvements (event-driven instead of cron)
4. CSV export for long-term analytics (>7 days)

**Dependencies:** Phase 1-3 (needs complete event stream and state)

**Validation:**
- Historical GPU usage queries work (last month, last semester)
- Operational dashboard shows cleanup metrics
- Lifecycle enforcement more responsive (event-driven)

**Why fourth:** Polish after core functionality works.

### Phase 5: Hygiene & Hardening (Weeks 11-12)

**What:** User offboarding, disk cleanup, backup/recovery

**Components:**
1. Departed user cleanup automation (detect inactive accounts, archive/remove)
2. Disk space optimization (image cleanup, build cache limits)
3. Backup system for /home, /var/lib/ds01, configs
4. Documentation refresh (README, architecture diagrams)

**Dependencies:** Phase 1-4 (needs stable foundation)

**Validation:**
- Departed user workflow documented and tested
- Disk usage controlled (old images cleaned)
- Backup restore tested successfully

**Why last:** Hygiene matters, but core functionality first.

## Integration with Existing Architecture

Evolution layers integrate cleanly with existing 5-layer hierarchy.

### Integration Points

| Existing Component | How It Changes | Integration Mechanism |
|--------------------|----------------|----------------------|
| **L5: Wizards** | No code changes | Read awareness state for better error messages |
| **L4: Orchestrators** | No code changes | Benefit from richer policy enforcement |
| **L3: Atomic commands** | No code changes | Awareness layer provides context |
| **L2: Docker wrapper** | Enhanced authorization | Add checks before passing to real Docker |
| **L1: AIME** | No changes | Continues to work unchanged |
| **L0: Docker** | No changes | Real binary unchanged |
| **Cron jobs** | Migrate to event-driven | Replace polling with Docker events triggers where possible |
| **Systemd slices** | Enhanced limits | Add IO/tasks to existing CPU/memory limits |
| **GPU allocator** | Extended scope | Add host process tracking |
| **Monitoring stack** | Enhanced exporters | DS01 Exporter adds unmanaged workload metrics |

### Backward Compatibility

**Critical constraint:** Existing containers must continue working.

**Compatibility guarantees:**
1. **Existing containers:** All containers created before evolution continue to run, managed by lifecycle enforcement
2. **Existing commands:** All `container-*`, `image-*`, orchestrator, wizard commands work unchanged
3. **Existing dashboards:** Current Grafana dashboards continue to function (new metrics added, not removed)
4. **Existing configs:** resource-limits.yaml schema backward compatible (new fields optional)

**Migration path:**
- Deploy awareness layer as separate systemd services (non-intrusive)
- Enable enforcement gradually (alert-only mode first, then blocking)
- Roll out new systemd limits per-user (opt-in initially)

## Scalability Considerations

DS01 is currently single-server. Architecture should support future scaling.

| Scale | Current Architecture | Adjustments Needed |
|-------|----------------------|-------------------|
| **1 server, 4 GPUs** | ✓ Current state | None |
| **1 server, 8 GPUs** | ✓ Supported | GPU allocator handles arbitrary GPU count |
| **2-3 servers** | Requires SLURM | Awareness layer per-server, centralized Prometheus federation |
| **4+ servers** | Requires Kubernetes | Migration to K8s + NVIDIA GPU Operator, cgroup model translates to Pod resource limits |

**Design decisions for future scaling:**

1. **State files local to server** — /var/lib/ds01/ remains server-local, federated via Prometheus
2. **Centralized monitoring** — Prometheus federation aggregates metrics from multiple servers
3. **User slices per-server** — Each server maintains its own systemd cgroup hierarchy
4. **GPU allocation per-server** — No cross-server GPU awareness needed (SLURM handles scheduling)

**Kubernetes migration path:**
- Systemd cgroup limits → Kubernetes ResourceQuotas and LimitRanges
- Docker wrapper → Kubernetes admission webhooks (validating/mutating)
- GPU allocator → NVIDIA Device Plugin + GPU Operator
- User slices → Kubernetes namespaces per user/group
- DCGM + DS01 Exporter → Unchanged (runs as DaemonSet)

## Anti-Patterns to Avoid

### Anti-Pattern 1: Global Container Scanning Without Rate Limiting

**What people do:** Run `docker ps -a` in tight loop to maintain real-time awareness

**Why it's wrong:** Docker API calls are expensive, creates CPU load, slows down Docker daemon

**Do this instead:** Use Docker events stream for real-time updates, poll `docker ps` only on startup or periodic reconciliation (5-15 minutes)

### Anti-Pattern 2: Killing Unmanaged Containers Immediately

**What people do:** Discover container without ds01.managed label → `docker kill` immediately

**Why it's wrong:** May be legitimate dev container, breaks user workflows, destroys data

**Do this instead:**
1. Alert first (grace period: 24-48h)
2. Inject management labels retroactively if possible
3. Only kill after user notification and grace period
4. Provide escape hatch (whitelist for specific containers)

### Anti-Pattern 3: Overwriting User-Specified Cgroup Parents

**What people do:** Always inject --cgroup-parent, even if user specified one

**Why it's wrong:** Breaks intentional configuration (e.g., user testing cgroup limits), prevents escape hatches for admin

**Do this instead:** Only inject if --cgroup-parent not already specified; respect explicit user configuration

### Anti-Pattern 4: Synchronous GPU Allocation in Wrapper

**What people do:** Docker wrapper blocks until GPU available, no timeout

**Why it's wrong:** `docker run` hangs indefinitely if all GPUs busy, user has no feedback

**Do this instead:** Timeout after 3 minutes (current implementation correct), provide clear error message with queue status

### Anti-Pattern 5: Relying on OPA for Basic Authorization

**What people do:** Deploy OPA for simple "user can only touch own containers" policy

**Why it's wrong:** OPA adds complexity, requires learning Rego, extra service to monitor, overkill for simple checks

**Do this instead:** Implement authorization in wrapper with simple bash/Python logic, reserve OPA for complex multi-constraint policies

### Anti-Pattern 6: Hardcoded Alertmanager Routes

**What people do:** Alertmanager config has hardcoded email addresses, no documentation

**Why it's wrong:** Breaks when personnel change, requires editing YAML and restart

**Do this instead:** Document how to update routes, provide examples, consider external configuration (environment variables)

### Anti-Pattern 7: No Historical Data Retention Strategy

**What people do:** Prometheus 7-day retention, no thought about long-term analytics

**Why it's wrong:** Can't answer "What was GPU usage during fall semester?" for impact reports

**Do this instead:** Plan for >7 day data (recording rules + external storage or CSV exports), define retention policy upfront

## Sources

**Systemd & Cgroups:**
- [systemd.resource-control documentation](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html)
- [Red Hat cgroup IO limits guide](https://access.redhat.com/solutions/3949221)
- [cgroup2 IO controller technical details](https://facebookmicrosites.github.io/cgroup2/docs/io-controller.html)
- [systemd cgroup delegation guide](https://systemd.io/CGROUP_DELEGATION/)

**Container Monitoring:**
- [Better Stack Docker monitoring tools 2026](https://betterstack.com/community/comparisons/docker-monitoring-addons/)
- [Docker events API documentation](https://docs.docker.com/reference/cli/docker/system/events/)
- [Wazuh Docker event monitoring](https://documentation.wazuh.com/current/proof-of-concept-guide/monitoring-docker.html)

**GPU Monitoring:**
- [NVIDIA nvidia-smi queries](https://nvidia.custhelp.com/app/answers/detail/a_id/3751/~/useful-nvidia-smi-queries)
- [nvitop interactive GPU monitoring](https://github.com/XuehaiPan/nvitop)
- [Linux GPU monitoring tools](https://www.cyberciti.biz/open-source/command-line-hacks/linux-gpu-monitoring-and-diagnostic-commands/)

**Container Isolation:**
- [SigNoz Docker alternatives comparison (Podman, gVisor, Kata)](https://signoz.io/comparisons/docker-alternatives/)
- [Docker alternatives 2026 overview](https://cybersecuritynews.com/docker-monitoring-tools/)

**Observability:**
- [Prometheus Alertmanager documentation](https://prometheus.io/docs/alerting/latest/alertmanager/)
- [Prometheus recording rules](https://prometheus.io/docs/prometheus/latest/configuration/alerting_rules/)

---

*Architecture research for DS01 Infrastructure milestone evolution*
*Researched: 2026-01-30*
