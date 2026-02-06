---
created: 2026-02-05T17:45
title: Add failure logging to orchestrators (container-deploy)
area: observability
files:
  - scripts/user/orchestrators/container-deploy
---

## Problem

When `container-deploy` calls `container-create` and it fails (e.g., "Permission denied" on script execution), there is **no logging**. The error shows on the user's terminal via stderr, but nothing is recorded in `/var/log/ds01/`. This makes debugging user-reported issues impossible — we can't see when they tried or what failed.

Discovered during investigation of a user's "Permission denied" error — we had login timestamps but zero trace of the failed container creation attempt.

## Solution

Add failure logging to orchestrators at the point where they invoke atomic commands:

```bash
# In container-deploy, around line 478
if ! "$CONTAINER_CREATE" "${CREATE_ARGS[@]}" 2>&1 | tee -a /var/log/ds01/orchestrator-errors.log; then
    log_event "orchestrator.create_failed" "container=$PROJECT" "exit_code=$?"
    exit 1
fi
```

Or simpler: just log all orchestrator invocations with timestamps and outcomes to a dedicated log file.

## Scope

- `container-deploy` (primary)
- `container-retire` (secondary)
- Potentially all L3/L4 commands
