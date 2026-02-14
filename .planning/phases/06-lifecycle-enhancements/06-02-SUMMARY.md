---
phase: 06-lifecycle-enhancements
plan: 02
subsystem: lifecycle-management
tags: [lifecycle, idle-detection, exemptions, enforcement, bash, multi-signal]

# Dependency graph
requires:
  - phase: 06-lifecycle-enhancements
    plan: 01
    provides: Per-group lifecycle configuration schema
  - phase: 05-lifecycle-bug-fixes
    provides: Container lifecycle enforcement scripts
provides:
  - Per-group multi-signal idle detection with AND logic
  - Detection window (consecutive idle checks) to reduce false positives
  - Exemption-aware lifecycle enforcement (idle and max runtime)
  - Variable SIGTERM grace periods by container type
affects: [lifecycle-enforcement, maintenance-automation]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "Multi-signal AND logic for idle detection (GPU + CPU + network)"
    - "Detection window with consecutive-check tracking (IDLE_STREAK)"
    - "Exemption checking with informational-only warnings"
    - "Variable SIGTERM grace by container type with config fallback chain"

key-files:
  created: []
  modified:
    - scripts/monitoring/check-idle-containers.sh
    - scripts/maintenance/enforce-max-runtime.sh

key-decisions:
  - "Multi-signal AND logic prevents false positives during data loading (LIFE-05)"
  - "Detection window requires N consecutive idle checks before action (LIFE-06)"
  - "Exempt users receive FYI-only warnings but no enforcement"
  - "SIGTERM grace varies by container type: GPU=60s, devcontainer=30s, compose=45s (LIFE-07)"
  - "CPU threshold configurable per group via lifecycle policies (raised from 1% to 2-5%)"

patterns-established:
  - "Per-group threshold resolution via get_lifecycle_policies()"
  - "Exemption checking via check_exemption() before enforcement"
  - "Detection window with IDLE_STREAK state tracking"
  - "Variable SIGTERM grace with container_types config override"

# Metrics
duration: 3min
completed: 2026-02-14
---

# Phase 6 Plan 02: Per-Group Lifecycle Enforcement Summary

**Per-group multi-signal idle detection with AND logic, detection window, exemptions, and variable SIGTERM grace**

## Performance

- **Duration:** ~3 minutes
- **Started:** 2026-02-14T14:27:24Z
- **Completed:** 2026-02-14T14:30:24Z (approximate)
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments

- Rewrote idle detection to use per-group thresholds (GPU, CPU, network) resolved via get_lifecycle_policies()
- Implemented multi-signal AND logic: container idle only when ALL signals below their per-group thresholds
- Added detection window with IDLE_STREAK tracking: N consecutive idle checks required before action
- Integrated exemption checking in both idle and max runtime enforcement
- Exempt users skip enforcement but receive informational-only warnings
- Implemented variable SIGTERM grace periods by container type (GPU=60s, devcontainer=30s, compose=45s)
- CPU threshold raised from hardcoded 1% to configurable 2-5% per group

## Task Commits

Each task was committed atomically:

1. **Task 1: Per-group idle detection with AND logic and detection window** - `ea129a5` (feat)
2. **Task 2: Exemption checking and variable SIGTERM for max runtime** - `ca63730` (feat)

## Files Modified

### scripts/monitoring/check-idle-containers.sh
**Changes:**
- Added `get_lifecycle_policies()` and `check_exemption()` functions
- Rewrote `is_container_active_secondary()` to accept configurable CPU and network thresholds
- Modified `get_last_activity()` to initialize IDLE_STREAK=0 in state files
- Updated `update_activity()` to reset IDLE_STREAK when container becomes active
- Added `send_informational_warning()` for exempt users (FYI-only)
- Added `get_sigterm_grace()` to resolve container-type-specific grace periods
- Updated `stop_idle_container()` to use variable SIGTERM grace
- Removed global `get_gpu_idle_threshold()` function (now per-group)
- Completely rewrote `process_container_universal()` with:
  - Per-group policy resolution (GPU, CPU, network thresholds, detection window)
  - Exemption checking before enforcement
  - Multi-signal AND logic (GPU idle AND CPU idle AND network idle = idle)
  - Detection window implementation (IDLE_STREAK tracking)
  - Informational warnings for exempt users
- Updated `monitor_containers()` to remove global gpu_idle_threshold variable

### scripts/maintenance/enforce-max-runtime.sh
**Changes:**
- Added `check_exemption()` function
- Modified `process_container_runtime_universal()` to:
  - Check exemption status before enforcement
  - Skip enforcement for exempt users with audit logging
  - Return early if exempt
- Updated `stop_runtime_exceeded()` to use container-type-specific SIGTERM grace:
  - Looks up grace in container_types config first
  - Falls back to global policies.sigterm_grace_seconds
  - Defaults to 60s if config read fails

## Decisions Made

1. **Multi-signal AND logic (LIFE-05):** Container is idle ONLY when ALL signals (GPU, CPU, network) are below their respective thresholds
   - Prevents stopping containers during data loading (GPU idle but CPU/network active)
   - Reduces false positives from transient GPU idle periods
   - Rationale: Real idle = all resources quiet, not just GPU

2. **Detection window (LIFE-06):** Requires N consecutive idle checks before action (configurable per group)
   - Student group: 3 consecutive checks (default)
   - Prevents transient dips from triggering stops
   - Tracked via IDLE_STREAK in state file
   - Reset to 0 when container becomes active
   - Rationale: Bursty workloads have brief idle periods that aren't true idle

3. **Exemption handling:** Exempt users receive informational warnings but no enforcement
   - FYI-only warnings via `send_informational_warning()`
   - Clearly states "you are exempt" in message
   - Still tracks idle state for audit purposes
   - Audit events logged for exempt containers (runtime_exempt)
   - Rationale: Awareness without disruption for active research exceptions

4. **Variable SIGTERM grace (LIFE-07):** Grace period varies by container type
   - GPU containers: 60s (time for model checkpointing)
   - Devcontainers: 30s (shorter for interactive sessions)
   - Compose: 45s (balanced for services)
   - Config hierarchy: container_types → global policies → 60s default
   - Rationale: Different workload patterns need different grace periods

5. **CPU threshold tuning:** Raised from hardcoded 1% to configurable 2-5%
   - Students: 2% (bursty but shorter jobs)
   - Researchers/Faculty: 3% (data-heavy workflows)
   - Per-group resolution via lifecycle policies
   - Rationale: Modern multi-core systems have background processes, <1% too strict

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - all bash syntax checks passed, verification criteria met, backward compatibility maintained.

## Next Phase Readiness

Plan 02 complete. Ready for Plan 03 (enforcement improvements):
- Per-group thresholds operational via get_lifecycle_policies()
- Exemptions integrated into enforcement flow
- Detection window prevents false positives
- Variable SIGTERM grace ensures checkpoint time

Existing Phase 5 enforcement scripts enhanced with Phase 6 capabilities:
- check-idle-containers.sh: Now uses per-group thresholds, AND logic, detection window, exemptions
- enforce-max-runtime.sh: Now checks exemptions, uses variable SIGTERM grace

## Technical Notes

### Multi-Signal AND Logic

**Idle determination:**
```bash
if GPU active:
    NOT idle (regardless of secondary signals)
elif GPU idle:
    if CPU > threshold OR network > threshold:
        NOT idle (data loading detected)
    else:
        idle (all signals quiet)
else (GPU unknown):
    if CPU > threshold OR network > threshold:
        NOT idle
    else:
        idle
```

### Detection Window Implementation

State file tracking:
```bash
# State file: /var/lib/ds01/container-states/{container}.state
LAST_ACTIVITY=1771079200
LAST_CPU=0.0
WARNED=false
IDLE_STREAK=0  # New field

# On idle check:
IDLE_STREAK++
if IDLE_STREAK < detection_window:
    skip enforcement (waiting for consecutive checks)

# On activity detected:
IDLE_STREAK=0
```

### Exemption Flow

```bash
# Check exemption before enforcement
exemption_status=$(check_exemption "$username" "idle_timeout")

if exempt:
    # Send FYI-only warning (informational)
    if idle_threshold_reached:
        send_informational_warning "$username" "$container" "$reason"
    return 0  # Skip enforcement

# Non-exempt: proceed with normal enforcement
if idle_threshold_reached:
    send_warning "$username" "$container" "$minutes_until_stop"
if timeout_reached:
    stop_idle_container "$username" "$container"
```

### Variable SIGTERM Grace Resolution

Config hierarchy:
1. `container_types.{type}.sigterm_grace_seconds` (most specific)
2. `policies.sigterm_grace_seconds` (global default)
3. `60` (hardcoded fallback)

Example config:
```yaml
policies:
  sigterm_grace_seconds: 60  # Global default

container_types:
  devcontainer:
    sigterm_grace_seconds: 30  # Override for devcontainers
  compose:
    sigterm_grace_seconds: 45  # Override for compose
```

### Backward Compatibility

All changes are backward compatible:
- Scripts work if new config fields are missing (safe defaults)
- State files auto-initialize IDLE_STREAK if missing
- Exemption file optional (no exemptions if missing)
- Per-group policies fall back to global defaults

---
*Phase: 06-lifecycle-enhancements*
*Completed: 2026-02-14*
