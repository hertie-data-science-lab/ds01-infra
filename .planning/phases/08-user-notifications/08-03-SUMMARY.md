---
phase: 08-user-notifications
plan: 03
subsystem: quota-alerts
tags: [quota-alerts, terminal-delivery, memory-alerts, cron, login-greeting]
dependency_graph:
  requires: [scripts/lib/ds01_notify.sh, scripts/docker/get_resource_limits.py, scripts/lib/username_utils.py]
  provides: [scripts/monitoring/resource-alert-checker.sh, config/deploy/cron.d/ds01-maintenance, config/deploy/profile.d/ds01-quota-greeting.sh]
  affects: [user terminal sessions, SSH login experience]
tech_stack:
  added: []
  patterns: [cgroup-memory-read, 4-hour-cooldown-via-json-field, single-python-call-at-login]
key_files:
  created: []
  modified:
    - scripts/monitoring/resource-alert-checker.sh
    - config/deploy/cron.d/ds01-maintenance
    - config/deploy/profile.d/ds01-quota-greeting.sh
decisions:
  - "deliver_alert_to_terminal skips container fallback — quota alerts are user-level, no specific container context"
  - "cooldown tracked via last_notified_at field added to existing alert JSON entry (no new file)"
  - "check_user skips admin group but still calls check_gpu_alerts since GPU uses --max-gpus separately from aggregate"
  - "login greeting uses single Python call reading existing JSON — no additional get_resource_limits.py calls at login"
  - "check_container_alerts uses --max-containers flag (fixing pre-existing grep-based parsing bug)"
metrics:
  duration_seconds: 360
  completed: 2026-02-17
  tasks_completed: 2
  files_created: 0
  files_modified: 3
---

# Phase 8 Plan 3: Quota Alert Terminal Delivery + Memory Alerts + Cron + Login Greeting Summary

**One-liner:** Extends resource-alert-checker.sh with memory quota detection, real-time terminal delivery with 4-hour cooldown, fixes cron to hourly :10, and adds pending alerts section to login greeting.

## What Was Built

### resource-alert-checker.sh — extended

Three key additions to the existing alert checker:

**1. `check_memory_alerts()`** — new function following the same pattern as `check_gpu_alerts()`:
- Gets `memory_max` from `get_resource_limits.py --aggregate` (handles G/M suffix or raw bytes)
- Reads current usage from `/sys/fs/cgroup/ds01.slice/ds01-{group}-{user}.slice/memory.current`
- Uses `username_utils.sanitize_username_for_slice()` for correct cgroup path construction
- Skips users with no active slice (cgroup file absent = no running containers)
- Two thresholds: 80% → `memory_usage_high`, 100% → `memory_limit_reached`
- Clears both types when below threshold

**2. `deliver_alert_to_terminal()`** — terminal delivery with cooldown:
- Reads `last_notified_at` from the alert's JSON entry in `/var/lib/ds01/alerts/{user}.json`
- If elapsed time < 4 hours, returns without delivery (no spam)
- Calls `ds01_format_message()` from ds01_notify.sh for bordered-box format
- Calls `ds01_notify()` with empty container name (user-level, no fallback needed)
- Writes `last_notified_at` back to JSON on successful delivery attempt
- Used by all three check functions (GPU, container, memory)

**3. Quiet cron output** — replaced `echo` stdout with `log_event()` calls. Only explicit user outputs (single-user mode) still print.

### config/deploy/cron.d/ds01-maintenance — updated

- Removed `*/15 * * * *` resource-alert-checker entry
- Added `10 * * * * root ...resource-alert-checker.sh` at :10 past each hour
- Updated lifecycle flow comment: `:05 GPU cleanup -> :10 quota alerts -> :20 idle -> :35 runtime -> :50 container cleanup`

### config/deploy/profile.d/ds01-quota-greeting.sh — updated

- Added pending alerts section after quota display, before "Useful commands"
- Single Python call reads `/var/lib/ds01/alerts/${_username}.json` and prints `[ALERT]` or `[WARNING]` prefix per alert
- Only renders section if alerts file exists and contains entries
- `_alerts_file` and `_alert_summary` added to `unset` cleanup line

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed check_container_alerts to use proper --max-containers flag**
- **Found during:** Task 1 — reviewing existing check_container_alerts()
- **Issue:** Original used `python3 "$RESOURCE_PARSER" "$username" | grep -oP 'max_containers_per_user:\s*\K\S+'` — grepping raw script output is fragile and doesn't use the script's actual CLI interface
- **Fix:** Changed to `python3 "$RESOURCE_PARSER" "$username" --max-containers` which is the documented flag (consistent with how check_gpu_alerts uses --max-gpus)
- **Files modified:** scripts/monitoring/resource-alert-checker.sh
- **Commit:** bb9ba11

## Verification

```
bash -n scripts/monitoring/resource-alert-checker.sh         → exit 0 (syntax clean)
grep -c "check_memory_alerts"  resource-alert-checker.sh     → 3 (def + call in check_user + call in check_memory_alerts)
grep -c "deliver_alert_to_terminal" resource-alert-checker.sh → 9 (def + calls in 3 check functions)
grep -c "ds01_notify" resource-alert-checker.sh              → 3 (source line + library calls)
grep "10 * * * *.*resource-alert" ds01-maintenance           → present
grep "*/15.*resource-alert" ds01-maintenance                 → NOT present
bash -n ds01-quota-greeting.sh                               → exit 0 (syntax clean)
grep "Pending alerts" ds01-quota-greeting.sh                 → present
grep "unset.*_alert_summary" ds01-quota-greeting.sh          → present (on unset line)
```

## Self-Check: PASSED

- `scripts/monitoring/resource-alert-checker.sh` — FOUND, syntax OK
- `config/deploy/cron.d/ds01-maintenance` — FOUND, :10 entry present, */15 removed
- `config/deploy/profile.d/ds01-quota-greeting.sh` — FOUND, syntax OK, pending alerts section present
- Commit bb9ba11 — FOUND (Task 1)
- Commit cbf70d2 — FOUND (Task 2)
