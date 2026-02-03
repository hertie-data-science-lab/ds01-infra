---
phase: 02-awareness-layer
plan: 01
subsystem: monitoring
tags: [docker, nvidia-smi, workload-detection, event-logging, json, systemd]

# Dependency graph
requires:
  - phase: 01-foundation-observability
    provides: Event logging library (ds01_events.py) with JSON schema v1
provides:
  - Core workload detection scanner (detect-workloads.py)
  - Container classification by origin (ds01-managed, devcontainer, compose, raw-docker)
  - Host GPU process detection via nvidia-smi + /proc attribution
  - Unified inventory persistence (/var/lib/ds01/workload-inventory.json)
  - Detection event emission (container/process discovered/exited)
  - Transient process filtering (2-scan threshold)
affects: [02-02-systemd-timer, 02-03-workload-query, 02-04-container-labelling]

# Tech tracking
tech-stack:
  added: [docker-py]
  patterns:
    - "Transient filtering: 2-scan persistence threshold for host processes"
    - "Atomic JSON writes via temp file + os.rename()"
    - "Safe import fallback for event logging (no-op function)"
    - "Lazy docker import (only when needed)"

key-files:
  created:
    - scripts/monitoring/detect-workloads.py
  modified:
    - scripts/lib/ds01_events.py

key-decisions:
  - "Transient filtering uses 2-scan threshold to avoid event noise from short-lived processes"
  - "System GPU processes (nvidia-persistenced, DCGM, Xorg) excluded from user inventory"
  - "Near-real-time inventory semantics: max 30s lag from polling interval (acceptable for 60s detection window)"
  - "Container name pattern 'vsc-' classified as devcontainer (VSCode pattern)"
  - "Inventory includes ALL containers (running and stopped) to track lifecycle"

patterns-established:
  - "detected_at timestamp preservation across scans for accurate age tracking"
  - "_pending_processes internal state for transient filtering"
  - "Classification priority order: ds01.managed > devcontainer.* > compose > vsc- pattern > raw-docker"
  - "User attribution priority: ds01.user > aime.mlc.USER > devcontainer path > /proc owner > unknown"

# Metrics
duration: 4min
completed: 2026-01-30
---

# Phase 2 Plan 1: Workload Detection Scanner

**Core workload scanner with Docker API + nvidia-smi detection, origin classification, transient filtering, and event emission**

## Performance

- **Duration:** 4 min
- **Started:** 2026-01-30T15:05:16Z
- **Completed:** 2026-01-30T15:09:01Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Complete workload detection scanner with container and host GPU process discovery
- Container classification system (ds01-managed, devcontainer, compose, raw-docker)
- Transient process filtering (2-scan threshold) prevents event noise
- Atomic inventory persistence to /var/lib/ds01/workload-inventory.json
- State transition detection with event emission for new/exited workloads

## Task Commits

Each task was committed atomically:

1. **Task 1: Container detection, classification, and GPU access check** - `3cdf495` (feat)
2. **Task 2: Inventory persistence, state diffing, event emission, and transient filtering** - `fa54d47` (feat)

**Deviation fix:** `69f1a03` (fix: register Phase 2 detection event types)

## Files Created/Modified
- `scripts/monitoring/detect-workloads.py` - Core workload detection scanner (866 lines)
- `scripts/lib/ds01_events.py` - Added detection.* event types to EVENT_TYPES registry

## Decisions Made

**Transient filtering with 2-scan threshold:**
- Host GPU processes must persist across 2 consecutive scans before generating discovery events
- Prevents noise from short-lived test processes
- Process lifecycle: First scan → pending, Second scan → confirmed + event emitted
- Containers do NOT need transient filtering (stable, not transient)

**System process exclusion:**
- Hardcoded set: nvidia-persistenced, nv-hostengine, dcgm, dcgmi, nvidia-smi, Xorg, X
- Filtered out before inventory inclusion
- Prevents user-facing clutter from infrastructure processes

**Container classification priority:**
1. `ds01.managed` label → "ds01-managed"
2. `devcontainer.*` labels → "devcontainer"
3. `com.docker.compose.project` label → "compose"
4. Container name starts with `vsc-` → "devcontainer" (VSCode pattern)
5. Default → "raw-docker"

**Near-real-time semantics:**
- Inventory reflects state at last scan, not truly real-time
- Max 30s lag from systemd timer polling interval (30s)
- Acceptable for detection success criteria (new workloads within 60s)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Register detection event types in EVENT_TYPES registry**
- **Found during:** Task 2 (Event emission implementation)
- **Issue:** Phase 2 detection.* event types not registered in ds01_events.py EVENT_TYPES dict. While event logging works without registration (dict is optional documentation), consistency with Phase 1 pattern requires registration for `ds01_events.py types` command and documentation completeness
- **Fix:** Added 5 detection event types to EVENT_TYPES registry with expected detail fields
- **Files modified:** scripts/lib/ds01_events.py
- **Verification:** Python syntax check passed, types command will now show detection events
- **Committed in:** 69f1a03 (separate fix commit)

---

**Total deviations:** 1 auto-fixed (Rule 1 - bug fix)
**Impact on plan:** Necessary for consistency with Phase 1 event logging pattern. No scope creep.

## Issues Encountered
None - implementation proceeded smoothly.

## User Setup Required
None - no external service configuration required. Scanner will be deployed via systemd timer in plan 02-02.

## Next Phase Readiness

**Ready for next phase:**
- Scanner complete and executable
- Inventory format defined and stable
- Event types registered and documented
- Transient filtering prevents event noise

**Next steps (Plan 02-02):**
- Create systemd timer/service units for 30s polling
- Deploy scanner to system
- Verify inventory file creation

**Future dependencies:**
- Plan 02-03 will query this inventory file
- Plan 02-04 will use classification data for container labelling

---
*Phase: 02-awareness-layer*
*Completed: 2026-01-30*
