---
status: resolved
trigger: "container-create-gpu-alloc-after-awareness-layer"
created: 2026-01-31T00:00:00Z
updated: 2026-01-31T00:10:00Z
---

## Current Focus

hypothesis: CONFIRMED - Two bugs: (1) grep -c || echo produces multi-line output causing bash integer error, (2) _is_full_gpu() misidentifies MIG UUIDs as full GPUs when nvidia-smi unavailable
test: Implementing fixes
expecting: Fixes resolve both bugs
next_action: Apply fixes to container-create, gpu-state-reader.py, and 10 other files with grep -c pattern

## Symptoms

expected: User hbaker should be able to deploy a new container via `container deploy`
actual: Two failures:
  1. `container-create: line 804: [: 0\n4: integer expression expected` - bash error from multi-line variable
  2. "You have 4 MIG partition(s) allocated" when user only has 1 stopped container (suspicious_banzai, a vscode devcontainer)
errors:
  - `/opt/ds01-infra/scripts/user/atomic/container-create: line 804: [: 0\n4: integer expression expected`
  - "Cannot allocate GPU resources."
reproduction: SSH as hbaker, run `container deploy`, select image, choose GPU mode
started: Immediately after awareness layer deployment (nvidia device permissions restricting host GPU access)

## Eliminated

## Evidence

- timestamp: 2026-01-31T00:01:00Z
  checked: container-create line 795
  found: `TOTAL_MIGS=$(nvidia-smi -L 2>/dev/null | grep -c MIG || echo "4")` - command substitution captures both grep output "0" AND echo "4", creating multi-line "0\n4"
  implication: Line 804 integer comparison fails with "0\n4"

- timestamp: 2026-01-31T00:02:00Z
  checked: gpu-state-reader.py line 74-76
  found: `_is_full_gpu()` checks `'.' not in str(gpu_slot)` - MIG UUIDs like "MIG-abc-123" have no dots
  implication: MIG UUIDs misidentified as full GPUs, counted as 4 MIG-equivalents each

- timestamp: 2026-01-31T00:03:00Z
  checked: Codebase-wide grep -c pattern
  found: 11 instances of `grep -c ... || echo` pattern across 8 files
  implication: All instances vulnerable to same multi-line bug

## Resolution

root_cause: |
  1. `grep -c PATTERN || echo "N"` anti-pattern: Command substitution captures both grep's stdout ("0") AND echo's fallback ("N"), producing multi-line values ("0\n4") that fail bash integer comparisons
  2. `_is_full_gpu()` checks only for dots: MIG UUIDs like "MIG-abc-123" have no dots, get misidentified as full GPUs, counted as 4 MIG-equivalents instead of 1

fix: |
  1. Changed all `VAR=$(grep -c ... || echo "N")` to `VAR=$(grep -c ...) || VAR=N` (separates stdout capture from exit code handling)
  2. Added MIG UUID detection to `_is_full_gpu()`: `if slot_str.startswith('MIG-'): return False`

verification: Syntax checks passed for all modified files

files_changed:
  - scripts/user/atomic/container-create
  - scripts/docker/gpu-state-reader.py
  - testing/diagnose-gid-issue.sh
  - scripts/admin/version
  - scripts/monitoring/resource-alert-checker.sh
  - scripts/monitoring/compile-daily-report.sh
  - scripts/user/helpers/ds01-login-check
  - scripts/user/orchestrators/container-retire
  - scripts/user/wizards/devcontainer-init
  - scripts/user/atomic/container-remove
