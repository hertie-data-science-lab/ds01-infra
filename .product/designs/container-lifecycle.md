# Container Lifecycle

The complete journey of a container from creation through cleanup, including idle detection, runtime enforcement, and GPU release.

## State Machine

```
                    ┌─────────┐
                    │ Created │  (docker create, never started)
                    └────┬────┘
                         │ docker start
                         ▼
                    ┌─────────┐
             ┌──── │ Running │ ◄──── user activity
             │     └────┬────┘
             │          │
             │    ┌─────┴──────┐
             │    │            │
             │  idle?      overtime?
             │    │            │
             │    ▼            ▼
             │  warn 80%    warn 75%
             │    │            │
             │  warn 95%    warn 90%
             │    │            │
             │    ▼            ▼
             │  ┌──────────────┐
             │  │   Stopped    │  (SIGTERM → grace → SIGKILL)
             │  └──────┬───────┘
             │         │
             │   gpu_hold_after_stop (15min)
             │         │
             │         ▼
             │  ┌──────────────┐
             │  │ GPU Released │
             │  └──────┬───────┘
             │         │
             │   container_hold_after_stop (30min)
             │         │
             │         ▼
             └───► ┌────────┐
                   │Removed │
                   └────────┘
```

## Lifecycle Enforcement Scripts

| Script | Schedule | Purpose |
|--------|----------|---------|
| `check-idle-containers.sh` | cron :30/hour | Detect idle GPU containers, warn, stop |
| `enforce-max-runtime.sh` | cron :45/hour | Detect overtime containers, warn, stop |
| `cleanup-stale-gpu-allocations.sh` | cron :15/hour | Release GPUs after hold timeout |
| `cleanup-stale-containers.sh` | cron :00/hour | Remove stopped containers after hold timeout |

## Idle Detection (Multi-Signal)

A container is idle when ALL signals indicate inactivity for the configured number of consecutive checks:

- **GPU utilisation** < threshold (default 5%)
- **CPU utilisation** < threshold (student: 2%, researcher: 3%)
- **Network I/O** < threshold (default 1MB)
- **Detection window**: N consecutive idle checks required (student: 3, researcher: 4)

Startup grace period: 30 minutes from container start (prevents false positives during package installation and data loading).

Keep-alive: `.keep-alive` file in workspace bypasses idle detection for up to 24 hours.

## Two-Level Escalation

**Idle timeout escalation:**
1. First warning at 80% of `idle_timeout` — informational, boxed TTY message.
2. Final warning at 95% of `idle_timeout` — urgent, mentions imminent stop.
3. Stop at 100% — SIGTERM with configurable grace period.

**Runtime limit escalation:**
1. First warning at 75% of `max_runtime`.
2. Final warning at 90% of `max_runtime`.
3. Stop at 100%.

## SIGTERM Grace Periods

Variable by container type to allow workload-appropriate shutdown:
- GPU containers: 60 seconds (model checkpoint saving)
- Dev containers: 30 seconds
- Compose services: 45 seconds
- Default: 30 seconds

## Exemptions

Time-bounded exemptions in `config/runtime/lifecycle-exemptions.yaml`:
```yaml
exemptions:
  - user: alice
    type: idle_timeout
    until: "2026-02-28"
    reason: "Thesis submission deadline"
```

Exempt users receive FYI-only warnings (no enforcement). Exemptions expire automatically. Eventual consistency: changes take effect at next cron cycle (~1 hour).

## Per-Group Policies

Each group can configure:
- `idle_timeout`, `max_runtime`
- `gpu_idle_threshold`, `cpu_idle_threshold`
- `idle_detection_window` (consecutive checks)
- `sigterm_grace_seconds`
- `container_hold_after_stop`, `gpu_hold_after_stop`

Inheritance: user_overrides → group → defaults.

## Container Type Handling

Different timeouts per interface type:

| Type | Idle Timeout | Max Runtime | Notes |
|------|-------------|-------------|-------|
| Atomic (DS01) | User-configured | User-configured | Full enforcement |
| Orchestration | User-configured | User-configured | Full enforcement |
| Dev container | Exempt | 168h (7 days) | MIG slice, bursty usage |
| Compose | 30min | 72h (3 days) | Service containers |
| Docker (raw) | 30min | 48h (2 days) | Unmanaged containers |
| Unknown | 15min | 24h | Strictest defaults |
