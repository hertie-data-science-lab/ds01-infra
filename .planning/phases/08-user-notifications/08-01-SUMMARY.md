---
phase: 08-user-notifications
plan: 01
subsystem: notification-library
tags: [bash-library, notifications, tty-delivery, quota-summary]
dependency_graph:
  requires: [scripts/lib/init.sh, scripts/docker/get_resource_limits.py, scripts/lib/username_utils.py]
  provides: [scripts/lib/ds01_notify.sh]
  affects: [scripts/monitoring/check-idle-containers.sh, scripts/maintenance/enforce-max-runtime.sh, scripts/monitoring/resource-alert-checker.sh]
tech_stack:
  added: []
  patterns: [bash-library-with-idempotent-guard, tty-write-with-fallback, cgroup-memory-read, per-run-caching]
key_files:
  created: [scripts/lib/ds01_notify.sh]
  modified: []
decisions:
  - "docker exec -e for env var passing avoids shell quoting issues with arbitrary message content"
  - "Quota cache uses printf -v into _DS01_QUOTA_CACHE_<safe_user> variable — safe for concurrent use within a single cron run"
  - "Memory display omitted when aggregate JSON is null/missing — avoids blank lines in message"
  - "gpu_display uses docker ps label filter count, not gpu_allocator_v2.py — simpler, no Python subprocess"
metrics:
  duration_seconds: 75
  completed: 2026-02-17
  tasks_completed: 1
  files_created: 1
  files_modified: 0
---

# Phase 8 Plan 1: Shared Notification Library Summary

**One-liner:** Bash notification library (ds01_notify.sh) with TTY delivery, /workspace/.ds01-alerts fallback, bordered-box formatting, and per-user GPU/memory/container quota summary with per-run caching.

## What Was Built

`scripts/lib/ds01_notify.sh` — the foundation for all Phase 8 notification work. Extracted and extended the duplicated `notify_user()` pattern from check-idle-containers.sh and enforce-max-runtime.sh into a single source of truth.

### Public API

| Function | Signature | Purpose |
|----------|-----------|---------|
| `ds01_notify` | `<username> <container> <message>` | Primary delivery: TTY, falls back to container file |
| `ds01_notify_container` | `<container> <message>` | Write to `/workspace/.ds01-alerts` inside container |
| `ds01_format_message` | `<severity> <title> <body> <username>` | Bordered box with severity header + quota section |
| `ds01_quota_summary` | `<username>` | GPU/memory/container snapshot, cached per run |

### Severity Labels

- `WARNING` — approaching a limit, recoverable
- `ALERT` — at limit or blocked
- `STOPPED` — container was just stopped
- `NOTICE` — informational / exempt user

### Quota Summary Format

```
  GPUs: 1/3 | Memory: 4.2/16 GB | Containers: 1/3
```

- GPU count: `docker ps --filter label=ds01.user=<user>`
- Memory current: `/sys/fs/cgroup/ds01.slice/ds01-<group>-<user>.slice/memory.current`
- Memory limit: `get_resource_limits.py <user> --aggregate`
- Container count: `docker ps --filter label=ds01.user=<user>`
- Any dimension with null/missing limits is silently omitted

### Caching

`ds01_quota_summary` caches results in `_DS01_QUOTA_CACHE_<safe_user>` shell variable. Subsequent calls within the same cron run return immediately without spawning Python, addressing the latency pitfall identified in research.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed docker exec env var passing pattern**
- **Found during:** Task 1 — initial implementation review
- **Issue:** Plan's research snippet used `docker exec container bash -c "..." DS01_MSG="$message"` which passes DS01_MSG as $0 to bash -c (positional arg), not as an environment variable
- **Fix:** Changed to `docker exec -e "DS01_MSG=${message}" container bash -c '... "$DS01_MSG" ...'` — correct env var injection via docker exec -e flag
- **Files modified:** scripts/lib/ds01_notify.sh
- **Commit:** 6d429f4

## Verification

```
bash -n scripts/lib/ds01_notify.sh        → exit 0 (syntax clean)
type ds01_notify                           → function defined
type ds01_notify_container                 → function defined
type ds01_format_message                   → function defined
type ds01_quota_summary                    → function defined
double source                              → OK (idempotent guard works)
```

## Self-Check: PASSED

- File exists: `scripts/lib/ds01_notify.sh` — FOUND
- Commit exists: `6d429f4` — FOUND
- All 4 public functions defined after source — VERIFIED
- Syntax check passes — VERIFIED
- Double-source idempotent — VERIFIED
