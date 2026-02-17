---
phase: 08-user-notifications
plan: 02
subsystem: lifecycle-notifications
tags: [bash-refactor, notifications, two-level-escalation, idle-timeout, max-runtime]
dependency_graph:
  requires: [scripts/lib/ds01_notify.sh, scripts/lib/init.sh, scripts/docker/get_resource_limits.py]
  provides: [scripts/monitoring/check-idle-containers.sh, scripts/maintenance/enforce-max-runtime.sh]
  affects: [users receiving idle/runtime warnings, container state files in /var/lib/ds01/]
tech_stack:
  added: []
  patterns: [two-level-escalation, warned-final-state-tracking, library-source-pattern]
key_files:
  created: []
  modified:
    - scripts/monitoring/check-idle-containers.sh
    - scripts/maintenance/enforce-max-runtime.sh
decisions:
  - "Idle thresholds: 80% first warning, 95% final warning — gives two meaningful intervention points"
  - "Runtime thresholds: 75% first warning, 90% final warning — earlier heads-up for longer-running jobs"
  - "hours_until_stop floored at 1h in runtime warnings — avoids confusing '0 hours' message near limit"
  - "WARNED_FINAL uses grep+sed guard pattern — safe for existing state files missing the key"
  - "update_activity() resets WARNED_FINAL alongside WARNED — clean slate on container activity"
metrics:
  duration_seconds: 480
  completed: 2026-02-17
  tasks_completed: 2
  files_created: 0
  files_modified: 2
---

# Phase 8 Plan 2: Lifecycle Notification Refactor Summary

**One-liner:** Refactored check-idle-containers.sh and enforce-max-runtime.sh to use ds01_notify.sh with two-level escalating warnings (80%+95% idle, 75%+90% runtime) replacing the prior single-warning approach.

## What Was Built

Both lifecycle enforcement scripts now source `scripts/lib/ds01_notify.sh` and use its public API for all user-facing notifications. The local `notify_user()` function that was duplicated verbatim in both scripts has been removed. All messages now use the unified bordered-box format via `ds01_format_message`, with the container-file fallback provided by `ds01_notify`.

### Idle Escalation (check-idle-containers.sh)

| Threshold | Action | Function |
|-----------|--------|----------|
| 80% of idle timeout | First warning sent, `WARNED=true` | `send_warning()` |
| 95% of idle timeout | Final warning sent, `WARNED_FINAL=true` | `send_final_warning()` |
| 100% of idle timeout | Container stopped | `stop_idle_container()` |

- `send_warning()`: "IDLE CONTAINER WARNING" with ~N minutes remaining, instructions to keep container alive
- `send_final_warning()`: "FINAL IDLE WARNING — STOPPING SOON" — urgent, shorter, emphasises immediate action
- `send_informational_warning()`: "IDLE CONTAINER NOTICE (FYI only)" for exempt users — uses `NOTICE` severity
- `stop_idle_container()`: "CONTAINER AUTO-STOPPED" — delivered before docker stop, container fallback fires if user offline

### Runtime Escalation (enforce-max-runtime.sh)

| Threshold | Action | Function |
|-----------|--------|----------|
| 75% of runtime limit | First warning sent, `WARNED=true` | `send_warning()` |
| 90% of runtime limit | Final warning sent, `WARNED_FINAL=true` | `send_final_warning()` |
| 100% of runtime limit | Container stopped | `stop_runtime_exceeded()` |

- `send_warning()`: "MAX RUNTIME WARNING" with ~N hours remaining, checkpointing guidance
- `send_final_warning()`: "FINAL RUNTIME WARNING — STOPPING SOON" — urgent save-now instructions
- `stop_runtime_exceeded()`: "CONTAINER STOPPED — RUNTIME LIMIT" — sent before docker stop

### State File Extension

Both scripts extend their state files with `WARNED_FINAL`:

```
# check-idle-containers — /var/lib/ds01/container-states/<container>.state
LAST_ACTIVITY=<epoch>
LAST_CPU=0.0
WARNED=false
WARNED_FINAL=false        # NEW
IDLE_STREAK=0

# enforce-max-runtime — /var/lib/ds01/container-runtime/<container>.state
WARNED=false
WARNED_FINAL=false        # NEW
```

Existing state files without `WARNED_FINAL` are handled by:
- `${WARNED_FINAL:-false}` default for the comparison (safe read)
- `grep -q "^WARNED_FINAL=" "$state_file" && sed -i ... || echo "WARNED_FINAL=true" >> "$state_file"` for the write (safe update)

## Notification Flow

```
User's container becomes idle
        ↓
  < 80% of timeout      → no action
        ↓
  >= 80%, WARNED=false  → send_warning() → ds01_notify → TTY or /workspace/.ds01-alerts
        ↓
  >= 95%, WARNED_FINAL=false → send_final_warning() → ds01_notify → TTY or /workspace/.ds01-alerts
        ↓
  >= 100%               → send stop notification → docker stop → docker rm
```

## Deviations from Plan

None — plan executed exactly as written. Minor implementation detail: `hours_until_stop` is floored at 1 in both runtime warning functions (plan showed this in code examples, confirmed as correct behaviour).

## Verification

```
bash -n check-idle-containers.sh      → exit 0 (syntax clean)
bash -n enforce-max-runtime.sh        → exit 0 (syntax clean)
grep notify_user both scripts         → 0 matches (removed)
grep ds01_notify check-idle           → 5 matches (source + 4 calls)
grep ds01_notify enforce-runtime      → 4 matches (source + 3 calls)
grep ds01_format_message check-idle   → 4 matches
grep ds01_format_message enforce      → 3 matches
grep WARNED_FINAL check-idle          → 5 occurrences (init x2, reset, check, update)
grep WARNED_FINAL enforce-runtime     → 3 occurrences (init, check, update)
grep "75 / 100" enforce-runtime       → confirms first warning at 75%
grep "90 / 100" enforce-runtime       → confirms final warning at 90%
grep "80 / 100" check-idle            → confirms first warning at 80%
grep "95 / 100" check-idle            → confirms final warning at 95%
```

## Self-Check: PASSED

- File exists: `scripts/monitoring/check-idle-containers.sh` — FOUND
- File exists: `scripts/maintenance/enforce-max-runtime.sh` — FOUND
- Commit exists: `fd88955` (check-idle) — FOUND
- Commit exists: `db8a695` (enforce-runtime) — FOUND
- Both syntax clean — VERIFIED
- No local notify_user() in either — VERIFIED
- Both source ds01_notify.sh — VERIFIED
- Two-level thresholds correct in both — VERIFIED
- WARNED_FINAL state tracked in both — VERIFIED
