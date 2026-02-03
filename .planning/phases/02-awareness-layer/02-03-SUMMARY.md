---
phase: 02-awareness-layer
plan: 03
subsystem: monitoring
tags: [workload-detection, jq, bash, docker-stats, admin-tools]

# Dependency graph
requires:
  - phase: 02-awareness-layer
    plan: 01
    provides: Workload inventory file (/var/lib/ds01/workload-inventory.json)
provides:
  - Admin query tool for unified workload inventory (ds01-workloads)
  - Multiple output formats (compact, wide, by-user, JSON)
  - Filter capabilities (--user, --type, --gpu-only, --all)
  - 4-tier help system (--help, --info, --concepts, --guided)
affects: [02-04-container-labelling, 03-enforcement-layer]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "jq-based JSON querying for structured data"
    - "Single docker stats call for efficiency (not per-container)"
    - "Age calculation from ISO 8601 timestamp"
    - "Color-coded output with ANSI codes"

key-files:
  created:
    - scripts/monitoring/ds01-workloads
  modified: []

key-decisions:
  - "Single docker stats call for all containers in wide mode (efficient batch query)"
  - "Host processes shown as type 'host-process' with PID:XXXX format for ID"
  - "By-user mode sorts alphabetically with 'unknown' user always last"
  - "Age display: Xd/Xh/Xm/Xs format for human readability"

patterns-established:
  - "Graceful missing inventory handling (informative message, not error)"
  - "Help works regardless of inventory file existence"
  - "Filter flags combine with AND logic"
  - "Summary line shows container count, GPU container count, host process count, last scan timestamp"

# Metrics
duration: 7min
completed: 2026-01-30
---

# Phase 2 Plan 3: Workload Query Command

**Admin query tool with compact/wide/by-user/JSON modes, filter flags, and 4-tier help for unified workload visibility**

## Performance

- **Duration:** 7 min
- **Started:** 2026-01-30T15:13:02Z
- **Completed:** 2026-01-30T15:20:04Z
- **Tasks:** 2
- **Files modified:** 1

## Accomplishments
- Complete ds01-workloads query command with 4 output modes
- Filter system (--user, --type, --gpu-only, --all) for targeted queries
- Live docker stats integration in wide mode (single efficient batch call)
- 4-tier help system following DS01 conventions (--help, --info, --concepts, --guided)
- Graceful handling of missing inventory file with helpful troubleshooting message

## Task Commits

Each task was committed atomically:

1. **Task 1: Create ds01-workloads with default table output and filter flags** - `64ed6cb` (feat)
2. **Task 2: Add --wide, --by-user, and complete 4-tier help** - `fbd5adb` (feat)

## Files Created/Modified
- `scripts/monitoring/ds01-workloads` - Admin query tool for workload inventory (829 lines)

## Decisions Made

**Single docker stats call for efficiency:**
- Wide mode fetches live stats once for all containers (not per-container loops)
- Stats cached in temp file, looked up by container ID during output
- Avoids N docker stats calls for N containers

**Host process display as unified type:**
- Host GPU processes shown as type="host-process" in TYPE column
- ID column shows "PID:XXXX" format to distinguish from container IDs
- Integrates cleanly with container data in unified output

**By-user grouping with alphabetical sort:**
- Users sorted alphabetically for predictable output
- "unknown" user always appears last (common convention)
- Each user section shows workload count and GPU count

**Age display format:**
- Compact time format: Xd (days), Xh (hours), Xm (minutes), Xs (seconds)
- Calculated from detected_at timestamp in inventory
- Provides quick scan visibility for workload duration

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - implementation proceeded smoothly.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

**Ready for next phase:**
- Query tool complete and functional
- All output modes implemented and tested
- Filter system works as specified
- Help system complete with educational content

**Next steps (Plan 02-04):**
- Use inventory data for automated container labelling
- Detect and label unmanaged containers
- Emit labelling events

**Integration points:**
- ds01-workloads reads `/var/lib/ds01/workload-inventory.json`
- Provides visibility layer that enforcement phases will build upon
- Educational content in --concepts explains detection architecture for admins

---
*Phase: 02-awareness-layer*
*Completed: 2026-01-30*
