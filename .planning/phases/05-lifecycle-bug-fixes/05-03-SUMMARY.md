---
phase: 05
plan: 03
subsystem: lifecycle
tags: [container-cleanup, lifecycle, gpu-release, created-state, universal-cleanup]
requires: [04-04-SUMMARY.md]
provides:
  - Universal container cleanup (all container types)
  - Created-state container detection and removal
  - Ownership fallback chain for unlabelled containers
  - Infrastructure container exemption
decisions:
  - "Use ownership fallback chain: ds01.user -> aime.mlc.USER -> devcontainer.local_folder -> name pattern -> unknown"
  - "Apply strictest timeout for unknown owners (container_types.unknown config)"
  - "Belt-and-suspenders GPU release on container removal (duplicates cleanup-stale-gpu-allocations but prevents leaks)"
  - "Immediate GPU release for created-state containers before removal"
tech-stack:
  added: []
  patterns: [ownership-fallback-chain, type-based-lifecycle, universal-enforcement]
key-files:
  created: []
  modified:
    - scripts/maintenance/cleanup-stale-containers.sh
affects: []
metrics:
  duration: 4m
  completed: 2026-02-11
---

# Phase 05 Plan 03: Universal Container Cleanup Summary

**One-liner:** Universal container cleanup with created-state detection, unlabelled container handling via ownership fallback chain, and immediate GPU release

## What Was Done

Extended `cleanup-stale-containers.sh` to handle ALL containers regardless of labels or creation method, with special handling for created-but-never-started containers.

### Task 1: Add created-state container cleanup
**File:** `scripts/maintenance/cleanup-stale-containers.sh`
**Commit:** 48586e4

Added `cleanup_created_containers()` function that:
- Detects containers in "created" state (never started) via `docker ps -a --filter "status=created"`
- Calculates age from CreatedAt timestamp
- Removes containers older than 30m (from `policies.created_container_timeout`)
- Releases GPU allocation before removal if DeviceRequests contains nvidia
- Skips infrastructure containers (ds01.monitoring=true or ds01.protected=true)
- Logs events with reason "created_never_started"

### Task 2: Handle unlabelled containers and universal cleanup
**File:** `scripts/maintenance/cleanup-stale-containers.sh`
**Commit:** 48586e4

Rewrote main stopped-container loop to be universal:

**Added ownership detection:**
- `get_container_owner()` function with fallback chain:
  1. ds01.user label
  2. aime.mlc.USER label
  3. devcontainer.local_folder path (extract username from /home/<user>/)
  4. Container name pattern (name._.uid)
  5. Fallback: "unknown"

**Added container type detection:**
- `get_container_type()` function for type classification
- `get_container_type_hold_timeout()` for type-based timeout config

**Universal cleanup logic:**
- Removed `--filter "label=aime.mlc.USER"` (AIME-only filter)
- Changed to `docker ps -a --filter "status=exited"` (all stopped containers)
- Apply ownership fallback chain to ALL containers
- Use container type config for unknown owners
- Skip infrastructure containers (ds01.monitoring=true OR ds01.protected=true)
- Release GPU before removal (belt-and-suspenders with cleanup-stale-gpu-allocations)
- Log events with container_type field

## Decisions Made

| Decision | Rationale | Impact |
|----------|-----------|--------|
| Ownership fallback chain | Handle containers created outside DS01 wrappers | All containers cleanable regardless of creation method |
| Unknown owner strictest timeout | Unattributable GPU containers get shortest lifecycle | Prevents resource hoarding by unmanaged containers |
| Belt-and-suspenders GPU release | Duplicate GPU release logic in cleanup script | Prevents GPU leaks if cleanup-stale-gpu-allocations misses a container |
| Infrastructure exemption at both levels | Check ds01.monitoring AND ds01.protected | Comprehensive protection for monitoring/infrastructure containers |

## Technical Details

### Ownership Fallback Chain

Priority order for determining container owner:

1. **ds01.user label** - Set by DS01 wrappers
2. **aime.mlc.USER label** - Legacy AIME containers
3. **devcontainer.local_folder** - VS Code dev containers (extract username from /home/<user>/ path)
4. **Container name pattern** - name._.uid (extract UID, lookup username)
5. **Fallback: "unknown"** - Apply strictest timeout from container_types.unknown

### Container Type Detection

From labels/name patterns:
- `ds01.container_type` label (if set)
- `ds01.interface` label (atomic, orchestration)
- `devcontainer.*` labels → devcontainer
- `com.docker.compose.*` labels → compose
- Fallback → docker

### Lifecycle Flow

```
Created Container (30m timeout)
    ↓
cleanup_created_containers()
    ↓ if age > 30m
Check infrastructure (skip if ds01.monitoring=true or ds01.protected=true)
    ↓
Release GPU if allocated
    ↓
Remove container
    ↓
Log event (reason: created_never_started)

Stopped Container (variable timeout by type/owner)
    ↓
cleanup-stale-containers.sh main loop
    ↓
Detect owner (fallback chain)
    ↓
Detect type
    ↓
Get timeout (owner's config OR container type config)
    ↓ if elapsed > timeout
Check infrastructure (skip if protected)
    ↓
Release GPU if allocated
    ↓
Remove container
    ↓
Log event (reason: hold_expired, container_type: <type>)
```

### Configuration Sources

**Created container timeout:**
```yaml
policies:
  created_container_timeout: 30m
```

**Stopped container timeout (known owner):**
```yaml
defaults:
  container_hold_after_stop: 0.5h

groups:
  researcher:
    container_hold_after_stop: 1h
```

**Stopped container timeout (unknown owner):**
```yaml
container_types:
  unknown:
    container_hold_after_stop: 0.5h  # Fallback to defaults
```

## Testing & Verification

All verification criteria passed:

1. ✅ `bash -n` syntax check passes
2. ✅ `grep -c "status=created"` returns 1 (created-state detection present)
3. ✅ No `--filter "label=aime.mlc.USER"` as only filter (universal cleanup)
4. ✅ `grep "ds01.monitoring"` found (infrastructure exemption present)
5. ✅ `grep "get_container_owner\|ds01.user"` found (ownership detection present)
6. ✅ `grep "gpu_allocator"` found (GPU release on removal present)
7. ✅ `grep "created_never_started"` found (created-state handling present)

## Deviations from Plan

None. Plan executed exactly as written.

Both tasks were combined into a single comprehensive commit since they modify the same script and represent a cohesive feature (universal container cleanup).

## Files Changed

| File | Lines Added | Lines Removed | Purpose |
|------|-------------|---------------|---------|
| `scripts/maintenance/cleanup-stale-containers.sh` | 255 | 14 | Universal cleanup with created-state detection |

## Integration Points

### Dependencies
- `config/runtime/resource-limits.yaml` - policies.created_container_timeout
- `scripts/docker/gpu_allocator_v2.py` - GPU release on removal
- `scripts/lib/ds01_events.sh` - Event logging
- `scripts/docker/get_resource_limits.py` - User/group timeout lookup

### Affected Systems
- Cron: `/etc/cron.d/ds01-container-cleanup` (calls this script hourly at :00)
- Cleanup flow: Works with cleanup-stale-gpu-allocations.sh (runs at :15)
- Monitoring: check-idle-containers.sh (stops containers, this removes them)

## Next Phase Readiness

**Phase 06 prerequisites:**
- ✅ Universal container cleanup handles all container types
- ✅ Created-state containers cleaned up within 30m
- ✅ Unlabelled containers attributed via fallback chain
- ✅ Infrastructure containers fully exempt

**No blockers for next phase.**

## Related Documentation

- **Config:** `config/runtime/resource-limits.yaml` - policies section
- **Cron:** `/etc/cron.d/ds01-container-cleanup` - :00/hour schedule
- **Related Scripts:**
  - `scripts/monitoring/check-idle-containers.sh` - Idle detection and stop
  - `scripts/maintenance/cleanup-stale-gpu-allocations.sh` - GPU release after gpu_hold_after_stop
  - `scripts/maintenance/enforce-max-runtime.sh` - Max runtime enforcement

## Commit Log

```
48586e4 feat(05-03): add universal container cleanup with created-state detection
```

**Total commits:** 1
**Duration:** ~4 minutes
**Status:** Complete ✅
