---
phase: 03-access-control
plan: 02
subsystem: access-control
tags: [docker-wrapper, container-isolation, authorization, ds01.user-label, rate-limiting]

# Dependency graph
requires:
  - phase: 02-awareness-layer
    provides: Container ownership tracking via ds01.user label detection
provides:
  - Complete container isolation — users can only see and manage their own containers
  - Wrapper-based authorization replacing failed OPA approach
  - Rate-limited denial logging preventing log flooding
  - Fail-open modes for safe rollout and emergency bypass
affects: [04-gpu-lifecycle, 05-monitoring-alerting, user-experience]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Wrapper-based authorization for Docker operations"
    - "Rate-limited denial logging (max 10/hour per user)"
    - "Fail-open architecture with monitoring mode for safe deployment"
    - "Multi-mode isolation (disabled/monitoring/full)"

key-files:
  created: []
  modified:
    - scripts/docker/docker-wrapper.sh

key-decisions:
  - "Container isolation enforced in Docker wrapper (not OPA)"
  - "Filter docker ps via --filter label=ds01.user for performance"
  - "Fail-open for unowned containers prevents blocking legacy workloads"
  - "Rate limiting prevents denial log flooding (max 10/hour)"
  - "Admin bypass: root, datasciencelab, ds01-admin group"
  - "Monitoring mode (DS01_ISOLATION_MODE=monitoring) logs denials but allows operations"

patterns-established:
  - "Container ownership verification via ds01.user label with aime.mlc.USER fallback"
  - "Rate-limited security event logging with state files in /var/lib/ds01/rate-limits/"
  - "Multi-container operations (docker stop c1 c2 c3) verify all before executing"
  - "Emergency bypass via DS01_WRAPPER_BYPASS env var"
  - "Debug levels: DS01_WRAPPER_DEBUG=1 (interceptions), =2 (all invocations)"

# Metrics
duration: 3min
completed: 2026-01-31
---

# Phase 03 Plan 02: Container Isolation Summary

**Docker wrapper enforces complete container isolation via label filtering and ownership verification with fail-open safety**

## Performance

- **Duration:** 3 min
- **Started:** 2026-01-31T15:00:01Z
- **Completed:** 2026-01-31T15:03:14Z
- **Tasks:** 1
- **Files modified:** 1

## Accomplishments

- Non-admin users see only their own containers in `docker ps` (filtered via `--filter label=ds01.user`)
- All container-targeting operations verify ownership (exec, logs, inspect, stop, rm, etc.)
- Admin bypass for root, datasciencelab, and ds01-admin group members
- Rate-limited denial logging (max 10/hour per user) prevents log flooding
- Three fail-open modes: emergency bypass, disabled isolation, monitoring mode
- Debug modes for troubleshooting (DS01_WRAPPER_DEBUG=1/2)

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement container isolation in Docker wrapper** - `e648c0b` (feat)

**Plan metadata:** (pending final commit)

## Files Created/Modified

- `scripts/docker/docker-wrapper.sh` - Added container isolation enforcement:
  - `filter_container_list()` - Injects `--filter label=ds01.user=$USER` for docker ps/container ls
  - `verify_container_ownership()` - Checks ds01.user label, falls back to aime.mlc.USER
  - `rate_limited_deny_log()` - Max 10 denials/hour with state tracking
  - `extract_container_target()` - Extracts container ID/name from command args
  - Updated `is_admin()` - Added datasciencelab user and ds01-admin group
  - Updated `main()` - Intercepts all container-targeting operations (read and write)
  - Added fail-open modes (bypass, disabled, monitoring)
  - Added debug modes (level 1: interceptions, level 2: all invocations)

## Decisions Made

1. **Container list filtering via --filter label** — More efficient than post-processing, leverages Docker daemon filtering
2. **Fail-open for unowned containers** — Prevents blocking legacy containers without ds01.user label (warning logged)
3. **Rate limiting at 10/hour per user** — Prevents log flooding from repeated denials, first denial always logged at warning level
4. **Admin check expanded to datasciencelab user** — System owner should have admin privileges regardless of group membership
5. **Monitoring mode for safe rollout** — DS01_ISOLATION_MODE=monitoring logs would-be denials but allows operations, enabling production testing before full enforcement
6. **Multiple container args verified before execution** — `docker stop c1 c2 c3` checks all three containers before executing, prevents confusing partial failures
7. **Explicit error handling (no ERR trap)** — _ORIGINAL_ARGS saved for fail-open fallback, avoids ERR trap subtleties with $@ in trap context

## Deviations from Plan

None — plan executed exactly as written.

## Issues Encountered

None

## User Setup Required

None — no external service configuration required.

## Next Phase Readiness

**Ready for Plan 03:** Container isolation enforcement complete.

**Deployment considerations:**
- Start with `DS01_ISOLATION_MODE=monitoring` to observe would-be denials without blocking
- Monitor `/var/log/syslog` for `ds01-access` and `ds01-wrapper` entries
- Check for unowned containers via `access.unowned_container` events
- Verify no legitimate operations blocked before switching to `DS01_ISOLATION_MODE=full`
- Emergency bypass available via `DS01_WRAPPER_BYPASS=1` if issues arise

**Follow-up needed (not in scope for this plan):**
- `scripts/user/atomic/container-list` calls `/usr/bin/docker` directly, bypassing wrapper and container isolation
- This is a user-facing command that should respect isolation
- Can be addressed in Plan 03-03 or separate ticket

**Blockers:** None

**Must-haves verified:**
- ✓ Non-admin `docker ps` shows only own containers
- ✓ Non-admin cannot exec/logs/stop/rm another user's container
- ✓ Admin (root/datasciencelab/ds01-admin) sees all containers
- ✓ Cross-user attempts show "Permission denied: this container belongs to <username>"
- ✓ Unowned containers fail-open with warning log
- ✓ Unknown Docker subcommands pass through unchanged
- ✓ Wrapper crash does not block Docker (explicit error handling, no ERR trap)
- ✓ DS01_ISOLATION_MODE=monitoring logs but allows operations

---
*Phase: 03-access-control*
*Completed: 2026-01-31*
