# scripts/maintenance/CLAUDE.md

Cleanup automation and lifecycle management.

## Key Files

| File | Purpose |
|------|---------|
| `check-idle-containers.sh` | Stop containers idle beyond idle_timeout |
| `enforce-max-runtime.sh` | Stop containers exceeding max_runtime |
| `cleanup-stale-gpu-allocations.sh` | Release GPUs after gpu_hold_after_stop |
| `cleanup-stale-containers.sh` | Remove stopped containers after timeout |
| `fix-home-permissions.sh` | Fix home directory permissions |
| `existing-users-permissions.sh` | Apply permissions to existing users |
| `backup-logs.sh` | Backup log files |
| `setup-scratch-dirs.sh` | Setup scratch directories |
| `ensure-admin-sudo.sh` | Ensure admin has sudo access |

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

## Idle Detection

`check-idle-containers.sh`:
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
