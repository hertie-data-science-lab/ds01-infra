# Notification System

How DS01 delivers warnings and alerts to users about container lifecycle events and quota status.

## Architecture

```
Enforcement scripts                    Notification library
(cron jobs)                           (ds01_notify.sh)
    │                                      │
    ├── check-idle-containers.sh ──────────┤
    ├── enforce-max-runtime.sh ────────────┤
    ├── resource-alert-checker (cron) ─────┤
    └── ds01-quota-greeting (login) ───────┘
                                           │
                                     ┌─────┴──────┐
                                     │             │
                                     ▼             ▼
                              ┌───────────┐  ┌───────────┐
                              │ TTY Write │  │ Container  │
                              │ /dev/pts/*│  │ File Write │
                              └───────────┘  └───────────┘
                                Primary        Fallback
```

## Delivery Strategies

### Primary: TTY Delivery

Discover active terminals via `who` command:
```bash
who | awk -v user="$username" '$1 == user {print $2}'
# Result: pts/0, pts/1, etc.
```

Write notification to each terminal:
```bash
echo "$message" > "/dev/$tty" 2>/dev/null
```

Reaches all active SSH sessions. Non-intrusive — appears inline in terminal output.

### Fallback: Container File

When user has no active terminals, append to container's workspace:
```bash
docker exec -e "DS01_MSG=${message}" "$container" bash -c \
    'printf "%s\n%s\n\n" "--- Alert: $(date) ---" "$DS01_MSG" >> /workspace/.ds01-alerts'
```

Uses `docker exec -e` flag to pass message via environment variable, avoiding shell quoting issues.

## Notification Types

| Type | Trigger | Delivery | Cooldown |
|------|---------|----------|----------|
| Idle warning (first) | 80% of idle timeout | TTY + container file | Per-container state |
| Idle warning (final) | 95% of idle timeout | TTY + container file | Per-container state |
| Runtime warning (first) | 75% of max runtime | TTY + container file | Per-container state |
| Runtime warning (final) | 90% of max runtime | TTY + container file | Per-container state |
| Quota alert (memory) | >80% aggregate memory | TTY only | 4-hour cooldown |
| Quota alert (GPU) | >80% GPU quota | TTY only | 4-hour cooldown |
| Login greeting | SSH login | TTY (profile.d) | Per-login |

## Message Format

Boxed formatting for visibility:
```
╔════════════════════════════════════════════╗
║    Container Approaching Idle Timeout      ║
╠════════════════════════════════════════════╣
║ Container: jupyter-alice                   ║
║ Idle time: 24 mins (expires in 6 mins)    ║
║ Quota: 1/3 GPUs, 16.2/32 GB Memory       ║
║ Action: Use container or it will stop     ║
╚════════════════════════════════════════════╝
```

## Quota Summary Caching

The quota summary (GPU count, memory usage, container count) is cached in a shell variable per notification run. This avoids repeated Python startup overhead when notifying about multiple containers for the same user.

```bash
ds01_quota_summary  # Calls get_resource_limits.py once, caches result
```

## Login Greeting

`ds01-quota-greeting.sh` (profile.d script) shows quota status at SSH login:
- Colour-coded progress bars (green <70%, yellow 70-84%, red 85%+)
- Memory, GPU, and tasks usage from direct cgroup reads (`memory.current`, `pids.current`)
- Target latency: <200ms (cgroup direct reads, no Python startup)
- Pending alerts from `resource-alert-checker` shown below greeting

## Exemption Handling

Exempt users (per `lifecycle-exemptions.yaml`) receive FYI-only warnings — notification says "informational only, no enforcement" instead of "your container will stop".

## Key Design Properties

- **Best-effort:** Notification delivery never blocks enforcement actions.
- **Non-disruptive:** TTY messages are brief and boxed for visual distinction.
- **Stateful escalation:** Container state files track `WARNED_FIRST` and `WARNED_FINAL` states to prevent duplicate notifications.
- **Fail-safe:** If delivery fails (no TTY, container unreachable), enforcement proceeds regardless.

## File Reference

- Notification library: `scripts/lib/ds01_notify.sh`
- Idle detection: `scripts/monitoring/check-idle-containers.sh`
- Runtime enforcement: `scripts/monitoring/enforce-max-runtime.sh`
- Quota alerts: `scripts/monitoring/resource-alert-checker`
- Login greeting: `config/deploy/profile.d/ds01-quota-greeting.sh`
