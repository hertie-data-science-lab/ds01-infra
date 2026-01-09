# scripts/maintenance/CLAUDE.md

Cleanup automation and lifecycle management.

## Core Principle

**GPU access = ephemeral enforcement, No GPU = permanent OK.**

ALL containers with GPU access are subject to lifecycle enforcement regardless of how they were created (VS Code dev containers, docker-compose, direct docker run, API calls).

## Key Files

| File | Purpose |
|------|---------|
| `enforce-max-runtime.sh` | **Universal** max_runtime enforcement for ALL GPU containers |
| `cleanup-stale-gpu-allocations.sh` | Release GPUs after gpu_hold_after_stop |
| `cleanup-stale-containers.sh` | Remove stopped containers after timeout |
| `fix-home-permissions.sh` | Fix home directory permissions |
| `existing-users-permissions.sh` | Apply permissions to existing users |
| `backup-logs.sh` | Backup log files |
| `setup-scratch-dirs.sh` | Setup scratch directories |
| `ensure-admin-sudo.sh` | Ensure admin has sudo access |

Note: `check-idle-containers.sh` is in `scripts/monitoring/` (see that CLAUDE.md)

## Cron Schedule

| Script | Schedule | Purpose |
|--------|----------|---------|
| `check-idle-containers.sh` | :30/hour | Idle detection |
| `enforce-max-runtime.sh` | :45/hour | Runtime limits |
| `cleanup-stale-gpu-allocations.sh` | :15/hour | GPU cleanup |
| `cleanup-stale-containers.sh` | :00/hour | Container removal |

## Cleanup Flow

```
Container Stop
    ↓
mark-stopped (record timestamp)
    ↓
gpu_hold_after_stop elapsed?
    ↓ yes
cleanup-stale-gpu-allocations.sh (release GPU)
    ↓
container_hold_after_stop elapsed?
    ↓ yes
cleanup-stale-containers.sh (remove container)
```

## Universal Enforcement

Both `enforce-max-runtime.sh` and `check-idle-containers.sh` use container type detection:

**Max runtimes by container type** (from `config/resource-limits.yaml`):
- `orchestration/atomic`: User's configured max_runtime
- `devcontainer`: 168h (7 days)
- `compose`: 72h (3 days)
- `docker`: 48h (2 days)
- `unknown`: 24h (strictest)

## Idle Detection

`check-idle-containers.sh` (in `scripts/monitoring/`):
- Checks CPU usage (< 1% = idle)
- Respects `.keep-alive` file in workspace
- Warns at 80% of idle_timeout
- Stops at 100%

## Log Locations

| Log | Path |
|-----|------|
| Idle cleanup | `/var/log/ds01/idle-cleanup.log` |
| Runtime enforcement | `/var/log/ds01/runtime-enforcement.log` |
| GPU cleanup | `/var/log/ds01/gpu-cleanup.log` |
| Container cleanup | `/var/log/ds01/container-cleanup.log` |

## Notes

- All cleanup scripts run as root via cron
- Each script reads owner-specific limits from resource-limits.yaml
- Cleanup is conservative (skips containers without metadata)
- `.keep-alive` file prevents idle timeout

---

**Parent:** [/CLAUDE.md](../../CLAUDE.md) | **Related:** [README.md](README.md)
