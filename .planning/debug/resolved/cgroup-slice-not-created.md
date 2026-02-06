---
status: resolved
trigger: "cgroup-slice-not-created"
created: 2026-02-05T00:00:00Z
updated: 2026-02-05T00:00:00Z
---

## Current Focus

hypothesis: CONFIRMED - check-limits uses wrong cgroup path (missing controller prefix)
test: Fix cgroup path to use controller-specific paths for v1 system
expecting: memory.usage_in_bytes and pids.current will be readable
next_action: Fix check-limits to use cgroup v1 paths

## Symptoms

expected: After deploying containers, `check-limits` should show actual aggregate resource usage (memory, tasks) read from the user's cgroup slice
actual: Shows "(No active containers - cgroup not yet created)" permanently, even with running containers
errors: No error messages — the cgroup directory simply doesn't exist at the expected path
reproduction: Login as h.baker, run `container deploy` successfully, then run `check-limits` — aggregate section shows "cgroup not yet created"
started: First noticed today. This is Phase 4 code (aggregate resource enforcement) — may never have worked correctly.

## Eliminated

## Evidence

- timestamp: 2026-02-05T00:01:00Z
  checked: check-limits script line 224
  found: Looks for path `/sys/fs/cgroup/ds01.slice/ds01-${group}-${sanitized_user}.slice`
  implication: Path includes ds01.slice/ parent directory

- timestamp: 2026-02-05T00:02:00Z
  checked: docker-wrapper.sh line 1049, 1136
  found: Injects `--cgroup-parent=ds01-${group}-${user}.slice` (no parent prefix)
  implication: Docker uses flat slice name, not nested path

- timestamp: 2026-02-05T00:03:00Z
  checked: systemctl show -p ControlGroup ds01.slice
  found: ControlGroup=/ds01.slice (not /system.slice/ds01.slice)
  implication: ds01.slice is at cgroup root, not under system.slice

- timestamp: 2026-02-05T00:04:00Z
  checked: /sys/fs/cgroup filesystem structure
  found: Hybrid cgroup v1/v2 system with controllers in separate dirs (memory/, pids/, unified/)
  implication: This is cgroup v1, not pure v2

- timestamp: 2026-02-05T00:05:00Z
  checked: /sys/fs/cgroup/memory/ds01.slice/ds01-researcher.slice/ds01-researcher-h_baker.slice/
  found: Cgroup exists with memory.usage_in_bytes (v1 format), NOT memory.current (v2 format)
  implication: check-limits is looking for v2 files that don't exist

- timestamp: 2026-02-05T00:06:00Z
  checked: check-limits line 224 vs actual cgroup structure
  found: check-limits looks for `/sys/fs/cgroup/ds01.slice/...` but actual path is `/sys/fs/cgroup/memory/ds01.slice/...` or `/sys/fs/cgroup/unified/ds01.slice/...`
  implication: Path is missing the controller subdirectory (memory, pids, etc.)

## Evidence

## Resolution

root_cause: check-limits uses cgroup v2 path format (`/sys/fs/cgroup/ds01.slice/...`) on a cgroup v1 system. Actual paths are `/sys/fs/cgroup/memory/ds01.slice/...` (v1) or `/sys/fs/cgroup/unified/ds01.slice/...` (v2 unified hierarchy). The cgroup v2 files (memory.current, pids.current) don't exist at the expected path because this system uses cgroup v1 with separate controller hierarchies.

fix: Updated check-limits to detect cgroup version by probing for memory.current file existence, then fall back to cgroup v1 paths with memory.usage_in_bytes. Handles three scenarios: pure v2, hybrid v2 with unified controllers, and v1 with separate hierarchies. For v1, reads pids from separate pids controller hierarchy.

verification: Tested with h.baker (researcher group). Script now correctly detects cgroup v1 system, constructs path `/sys/fs/cgroup/memory/ds01.slice/ds01-researcher.slice/ds01-researcher-h_baker.slice`, reads memory.usage_in_bytes (589590528 bytes), and reads pids.current from separate pids controller hierarchy. The "(No active containers - cgroup not yet created)" message will only appear when cgroup genuinely doesn't exist, not due to incorrect path.

files_changed:
  - scripts/user/helpers/check-limits
