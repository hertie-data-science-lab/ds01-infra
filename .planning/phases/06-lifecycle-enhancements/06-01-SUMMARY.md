---
phase: 06-lifecycle-enhancements
plan: 01
subsystem: lifecycle-management
tags: [lifecycle, idle-detection, exemptions, yaml, resource-limits, python]

# Dependency graph
requires:
  - phase: 05-lifecycle-bug-fixes
    provides: Container lifecycle enforcement (idle detection, max runtime, cleanup)
provides:
  - Per-group lifecycle policy configuration (thresholds, detection window)
  - Time-bounded exemption system with Azure Policy pattern
  - Policy inheritance: global → group → user
affects: [06-02, 06-03, lifecycle-enforcement]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Per-group policy inheritance with YAML configuration"
    - "Time-bounded exemptions with audit trail preservation"
    - "Azure Policy exemption pattern (expires_on with record preservation)"

key-files:
  created:
    - config/runtime/lifecycle-exemptions.yaml
  modified:
    - config/runtime/resource-limits.yaml
    - scripts/docker/get_resource_limits.py

key-decisions:
  - "CPU threshold tuned from <1% to 2-5% range to reduce false positives (LIFE-06)"
  - "Student group gets 2% CPU threshold (bursty), researcher/faculty get 3% (data-heavy)"
  - "Exemptions preserved after expiry for audit trail (Azure Policy pattern)"
  - "Eventual consistency: exemptions take effect at next cron cycle (~1 hour max)"

patterns-established:
  - "Per-group lifecycle policies with inheritance hierarchy"
  - "Time-bounded exemptions with ISO 8601 expiry dates"
  - "CLI-based policy resolution for maintenance scripts"

# Metrics
duration: 2min
completed: 2026-02-14
---

# Phase 6 Plan 01: Configuration Schema for Lifecycle Policies Summary

**Per-group lifecycle thresholds (CPU 2-5%, GPU 5%, network 1MB) and time-bounded exemptions with audit trail preservation**

## Performance

- **Duration:** ~2 minutes
- **Started:** 2026-02-14T14:20:53Z
- **Completed:** 2026-02-14T14:22:53Z (approximate)
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Extended resource-limits.yaml with per-group lifecycle policies (cpu_idle_threshold, gpu_idle_threshold, network_idle_threshold, idle_detection_window)
- Created lifecycle-exemptions.yaml with time-bounded exemption support and Azure Policy pattern
- Added get_lifecycle_policies() and check_exemption() methods to get_resource_limits.py with CLI flags
- Pre-populated exemption for Silke Kaiser (migrated from user-overrides.yaml pattern)

## Task Commits

Each task was committed atomically:

1. **Task 1: Extend resource-limits.yaml with per-group lifecycle policies** - `d63a262` (feat)
2. **Task 2: Create lifecycle-exemptions.yaml and extend get_resource_limits.py** - `47bfb38` (feat)

## Files Created/Modified

### Created
- `config/runtime/lifecycle-exemptions.yaml` - Time-bounded exemption records with expiry dates and audit preservation

### Modified
- `config/runtime/resource-limits.yaml` - Added global cpu_idle_threshold/network_idle_threshold/idle_detection_window, per-group policies subsections, sigterm_grace_seconds to container_types
- `scripts/docker/get_resource_limits.py` - Added get_lifecycle_policies() and check_exemption() methods with --lifecycle-policies and --check-exemption CLI flags

## Decisions Made

1. **CPU threshold tuning (LIFE-06):** Raised from <1% to 2-5% range based on research findings
   - Students: 2% (bursty but shorter jobs)
   - Researchers/Faculty: 3% (data-heavy workflows with longer preprocessing)
   - Rationale: <1% too strict for modern multi-core systems, caused false positives during data loading

2. **Per-group policies structure:** Added `policies` subsection to each group definition
   - Follows existing pattern where groups override defaults
   - Enables different workload patterns across research groups
   - Admin group intentionally has no per-group policies (uses global defaults)

3. **Exemption file structure:** Separate lifecycle-exemptions.yaml rather than embedded in resource-limits.yaml
   - Follows Azure Policy exemption pattern (time-bounded, preserved after expiry)
   - Easier to audit and review exemptions independently
   - Clear separation: resource-limits.yaml = limits, lifecycle-exemptions.yaml = exceptions

4. **Eventual consistency:** Exemption changes take effect at next cron cycle
   - Acceptable delay (~1 hour max) for lifecycle enforcement use case
   - Simpler architecture than immediate propagation (no file watchers, reload signals)
   - Documented in lifecycle-exemptions.yaml header

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all YAML validation passed, CLI flags tested successfully, exemption handling verified for both exempt and non-exempt users.

## Next Phase Readiness

Configuration foundation complete for Plans 02 and 03:
- Plan 02 (idle detection) can call get_lifecycle_policies() to resolve per-group thresholds
- Plan 03 (enforcement) can call check_exemption() to determine if user is exempt from enforcement
- Existing Phase 5 enforcement scripts need no immediate changes (backward compatible)

## Technical Notes

### Policy Inheritance Hierarchy
1. Global `policies` section (defaults)
2. Group `policies` subsection (overrides global)
3. User `policies` in user-overrides.yaml (overrides group)

### CLI Interface
```bash
# Get lifecycle policies for user (resolved with inheritance)
python3 scripts/docker/get_resource_limits.py <username> --lifecycle-policies

# Check exemption status
python3 scripts/docker/get_resource_limits.py <username> --check-exemption idle_timeout
python3 scripts/docker/get_resource_limits.py <username> --check-exemption max_runtime
```

### Exemption Lifecycle
- **Before expiry:** Exemption honored, user not subject to enforcement
- **After expiry:** Exemption no longer honored, but record preserved for audit
- **Optional cleanup:** Expired records older than 90 days can be removed periodically

---
*Phase: 06-lifecycle-enhancements*
*Completed: 2026-02-14*
