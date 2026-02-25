# Feature Inventory

Complete inventory of DS01 capabilities, grouped by subsystem.

## GPU Management

| Feature | Layer | Status | Key Files |
|---------|-------|--------|-----------|
| Stateless GPU allocation | Docker/Wrapper | Implemented | `gpu_allocator_v2.py` |
| MIG instance tracking | Docker/Wrapper | Implemented | `gpu_allocator_v2.py` |
| Per-user GPU quotas | Docker/Wrapper | Implemented | `get_resource_limits.py` |
| Aggregate GPU quota enforcement | Docker/Wrapper | Implemented | `docker-wrapper.sh` |
| GPU state reader (Docker labels) | Docker | Implemented | `gpu-state-reader.py` |
| GPU availability checker | Docker | Implemented | `gpu-availability-checker.py` |
| GPU hold after container stop | Maintenance | Implemented | `cleanup-stale-gpu-allocations.sh` |
| GPU health verification post-cleanup | Maintenance | Implemented | `cleanup-stale-gpu-allocations.sh` |
| Bare metal GPU access control | System | Implemented | profile.d scripts, video group |
| Full GPU allocation (non-MIG) | Docker/Wrapper | Implemented | `gpu_allocator_v2.py` |

## Container Lifecycle

| Feature | Layer | Status | Key Files |
|---------|-------|--------|-----------|
| Multi-signal idle detection | Monitoring | Implemented | `check-idle-containers.sh` |
| Two-level idle escalation (80%, 95%) | Monitoring | Implemented | `check-idle-containers.sh` |
| Max runtime enforcement | Monitoring | Implemented | `enforce-max-runtime.sh` |
| Two-level runtime escalation (75%, 90%) | Monitoring | Implemented | `enforce-max-runtime.sh` |
| Created-state container cleanup | Maintenance | Implemented | `cleanup-stale-containers.sh` |
| Per-group lifecycle policies | Config | Implemented | `resource-limits.yaml` |
| Time-bounded exemptions | Config | Implemented | `lifecycle-exemptions.yaml` |
| Variable SIGTERM grace periods | Monitoring | Implemented | Per container type |
| Keep-alive file support (24h max) | Monitoring | Implemented | `.keep-alive` in workspace |
| Stale container removal | Maintenance | Implemented | `cleanup-stale-containers.sh` |

## User Commands

| Feature | Layer | Status | Key Files |
|---------|-------|--------|-----------|
| container-create/start/stop/remove | L2 Atomic | Implemented | `scripts/user/atomic/` |
| container-deploy/retire | L3 Orchestrator | Implemented | `scripts/user/orchestrators/` |
| container-list/stats/attach/pause | L2 Atomic | Implemented | `scripts/user/atomic/` |
| image-create/list/update/delete | L2 Atomic | Partial | Bugs in create/update (Phase 9) |
| user-setup wizard | L4 Wizard | Partial | Bug reading existing images (Phase 9) |
| project-init/project-launch | L4 Wizard | Implemented | `scripts/user/wizards/` |
| devcontainer-init | L4 Wizard | Implemented | `scripts/user/wizards/` |
| check-limits (quota display) | Helper | Implemented | `scripts/user/helpers/` |
| Dispatcher routing (space-separated) | L1 Dispatcher | Implemented | `scripts/user/dispatchers/` |
| 4-tier help system | All layers | Implemented | --help, --info, --concepts, --guided |
| Context-aware output suppression | Orchestrators | Implemented | DS01_CONTEXT variable |

## Monitoring & Admin

| Feature | Layer | Status | Key Files |
|---------|-------|--------|-----------|
| System dashboard (GPU, containers) | Admin | Implemented | `scripts/admin/dashboard` |
| Dashboard views (interfaces, users, monitor) | Admin | Implemented | `scripts/admin/dashboard` |
| ds01-events query tool | Admin | Implemented | `scripts/admin/ds01-events` |
| ds01-workloads inventory | Admin | Implemented | `scripts/admin/ds01-workloads` |
| ds01-logs viewer | Admin | Implemented | `scripts/admin/ds01-logs` |
| Container owner tracking (real-time) | Docker | Implemented | `container-owner-tracker.py` |
| Periodic ownership sync | Docker | Implemented | `sync-container-owners.py` |
| Workload detection (host + container) | Monitoring | Implemented | `detect-workloads.py` |
| Bare metal GPU process detection | Monitoring | Implemented | `detect-bare-metal.py` |
| Health check (GPU, cgroups, permissions) | Monitoring | Implemented | `ds01-health-check` |
| MIG configuration tool | Admin | Implemented | `mig-configure` |

## Resource Enforcement

| Feature | Layer | Status | Key Files |
|---------|-------|--------|-----------|
| Per-user systemd cgroup slices | System | Implemented | `create-user-slice.sh` |
| Aggregate CPU quota (CPUQuota) | System | Implemented | Systemd drop-ins |
| Aggregate memory limit (MemoryMax/High) | System | Implemented | Systemd drop-ins |
| Aggregate pids limit (TasksMax) | System | Implemented | Systemd drop-ins |
| Per-container CPU/memory/pids limits | Docker/Wrapper | Implemented | `docker-wrapper.sh` |
| Pre-creation quota check | Docker/Wrapper | Implemented | `docker-wrapper.sh` |
| IO bandwidth enforcement | — | Deferred | Needs BFQ scheduler |
| Disk quota enforcement | — | Deferred | Needs XFS migration |

## Configuration & Deployment

| Feature | Layer | Status | Key Files |
|---------|-------|--------|-----------|
| YAML resource limits (SSOT) | Config | Implemented | `resource-limits.yaml` |
| 4-tier config resolution | Config | Implemented | `get_resource_limits.py` |
| Group membership files | Config | Implemented | `config/runtime/groups/*.members` |
| Deploy/runtime/state hierarchy | Config | Implemented | `config/` directory structure |
| Template-based deployment | System | Implemented | `deploy.sh` |
| Deterministic permissions manifest | System | Implemented | `permissions-manifest.sh` |
| YAML validation before deploy | System | Implemented | `deploy.sh` |
| Self-bootstrap deployment | System | Implemented | `deploy.sh` |
| Semantic versioning (CI) | CI/CD | Implemented | `.github/workflows/release.yml` |

## Notification & Logging

| Feature | Layer | Status | Key Files |
|---------|-------|--------|-----------|
| TTY notification delivery | Lib | Implemented | `ds01_notify.sh` |
| Container file fallback delivery | Lib | Implemented | `ds01_notify.sh` |
| Quota alerts (memory, GPU) | Monitoring | Implemented | `resource-alert-checker` |
| Login quota greeting (profile.d) | System | Implemented | `ds01-quota-greeting.sh` |
| JSONL event logging (4KB atomic) | Lib | Implemented | `ds01_events.py`, `ds01_events.sh` |
| Structured event schema (v1) | Lib | Implemented | `ds01_events.py` |
| ds01.* label schema | Config | Implemented | `label-schema.yaml` |
| Docker wrapper isolation (3 modes) | Docker/Wrapper | Implemented | `docker-wrapper.sh` |
| 6-strategy ownership detection | Docker | Implemented | `container-owner-tracker.py` |

## Summary

- **Total features:** 68
- **Implemented:** 63 (93%)
- **Partial:** 3 (4%) — image-create, image-update, user-setup bugs
- **Deferred:** 2 (3%) — IO bandwidth, disk quota
