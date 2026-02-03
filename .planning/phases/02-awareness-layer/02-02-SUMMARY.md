---
phase: 02-awareness-layer
plan: 02
subsystem: infra
tags: [systemd, timer, monitoring, automation]

# Dependency graph
requires:
  - phase: 01-foundation
    provides: "Event logging infrastructure (ds01_events)"
provides:
  - "Systemd timer for 30-second periodic workload scanning"
  - "Systemd service for oneshot workload detection execution"
  - "Deploy script automation for timer/service installation"
affects: [03-enforcement-layer, monitoring, operations]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Systemd timer pattern for periodic scanning (30s intervals, 1s accuracy)"
    - "Oneshot service pattern for stateless scans"
    - "Deploy script integration for systemd units"

key-files:
  created:
    - config/deploy/systemd/ds01-workload-detector.timer
    - config/deploy/systemd/ds01-workload-detector.service
  modified:
    - scripts/system/deploy.sh

key-decisions:
  - "AccuracySec=1s required to override systemd default 1min accuracy for precise 30s intervals"
  - "TimeoutSec=25s ensures service completes before next 30s timer trigger"
  - "Nice=10 and IOSchedulingClass=idle to minimize impact on user workloads"
  - "State directory /var/lib/ds01 with root:docker 775 permissions"

patterns-established:
  - "Systemd units stored in config/deploy/systemd/ for version control"
  - "Deploy script handles systemd unit installation, daemon reload, enable, and start"
  - "Timer uses OnUnitActiveSec for interval-after-completion scheduling"

# Metrics
duration: 2min
completed: 2026-01-30
---

# Phase 02 Plan 02: Systemd Scheduler Summary

**Systemd timer triggers workload detection every 30 seconds with 1s accuracy, deployed via automated deploy script**

## Performance

- **Duration:** 2 min
- **Started:** 2026-01-30T15:06:04Z
- **Completed:** 2026-01-30T15:08:10Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments

- Systemd timer and service units created for periodic workload scanning
- Timer configured for precise 30s intervals (AccuracySec=1s critical)
- Service configured as oneshot with 25s timeout, lower priority
- Deploy script automated: state directory creation, Python docker package check, systemd unit installation and activation

## Task Commits

Each task was committed atomically:

1. **Task 1: Create systemd timer and service units** - `5df950b` (feat)
2. **Task 2: Update deploy script and ensure dependencies** - `dd8e1b1` (feat)

## Files Created/Modified

- `config/deploy/systemd/ds01-workload-detector.timer` - Systemd timer unit (30s interval, 1s accuracy, triggers service)
- `config/deploy/systemd/ds01-workload-detector.service` - Systemd service unit (oneshot, 25s timeout, runs detect-workloads.py)
- `scripts/system/deploy.sh` - Updated with systemd deployment section (state dir, Python docker package, timer/service installation)

## Decisions Made

- **AccuracySec=1s**: Required to override systemd's default 1-minute accuracy window for precise 30-second intervals
- **TimeoutSec=25s**: Service must complete before next timer trigger (30s interval) to prevent overlap
- **Nice=10 + IOSchedulingClass=idle**: Lower priority to avoid impacting user workloads during scan
- **OnUnitActiveSec vs OnCalendar**: Using OnUnitActiveSec=30s for interval-after-completion (not wall-clock) to prevent scan overlap
- **Persistent=false**: Don't catch up missed runs on boot (fresh scan is better than stale catch-up)
- **State directory permissions**: /var/lib/ds01 as root:docker 775 to allow docker group access for inventory reads

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - systemd units created smoothly following Phase 1 patterns from DCGM exporter and DS01 exporter service deployments.

## User Setup Required

None - systemd units will be deployed automatically when `sudo deploy` is run. No manual intervention required.

## Next Phase Readiness

**Ready for plan 02-01:**
- Systemd scheduler infrastructure complete
- Deploy script automation ready
- State directory and Python docker package requirements handled

**Blockers:**
- Plan 02-01 must create `scripts/monitoring/detect-workloads.py` before systemd service can run successfully
- Note: This is expected - plan 02-02 creates the scheduler, plan 02-01 creates the scanner script it will invoke

**Execution order note:**
The plans can be executed in either order:
- This plan (02-02) creates the systemd units that reference detect-workloads.py
- Plan 02-01 will create the actual detect-workloads.py script
- Both are needed for the workload detector to run
- Deploy script gracefully handles missing detect-workloads.py with a message

---
*Phase: 02-awareness-layer*
*Completed: 2026-01-30*
