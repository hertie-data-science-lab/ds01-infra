---
created: 2026-01-31T23:05
title: "URGENT: Fix GPU allocation (full GPU support + permissions)"
area: tooling
files:
  - scripts/docker/gpu-availability-checker.py:154-177
  - scripts/docker/gpu-availability-checker.py:349-366
  - scripts/docker/gpu_allocator_v2.py:97-103
  - scripts/docker/get_resource_limits.py:66-88
  - config/groups/*.members
---

## Problem

Three interrelated bugs prevent GPU allocation for all users:

### 1. Availability checker only sees MIG instances (code bug)
`gpu-availability-checker.py` → `get_available_gpus()` only queries MIG instances via nvidia-smi. When MIG is not enabled (current state: 4x A100 full GPUs, no MIG partitions), it reports 0 total GPUs. The `_get_full_gpus_available()` method exists and works but is only called when `require_full_gpu=True`, which the normal allocation path never sets.

**Fix needed:** `get_available_gpus()` and `get_allocation_summary()` must include full GPUs (those without MIG partitions) in the available pool. The `suggest_gpu_for_user()` filtering for `allow_full_gpu` already handles access control.

### 2. Allocator never reads .members files (code bug)
`gpu_allocator_v2.py` → `_load_config()` only reads YAML. The YAML `groups:` section has no inline `members:` lists — membership is in `config/groups/*.members` files. So `_get_user_limits()` finds no members in any group and EVERY user falls back to `default_group: student`.

`get_resource_limits.py` has `_load_external_files()` which correctly merges `.members` files. The allocator needs the same logic.

**Fix needed:** `_load_config()` must read and merge `config/groups/{group}.members` files into the groups config, same pattern as `get_resource_limits.py._load_external_files()`.

### 3. File permissions block non-admin users (deployment bug)
Scripts and config files had owner-only permissions:
- `gpu-availability-checker.py` was `700` (fixed to `755`)
- `gpu_allocator_v2.py` was `700` (fixed to `755`)
- `config/groups/*.members` were `600` (fixed to `644`)

Even after code fixes, users couldn't read the files. The `get_resource_limits.py` silently fell back to empty members on PermissionError, masking the issue.

**Permissions fixed in this session** but need a systematic check — likely caused by git checkout or file creation without umask consideration.

## Attempted Fix (Rolled Back)

Changes were made and tested as datasciencelab (admin) — worked correctly:
- `get_available_gpus()` included full GPUs → 4 GPUs visible
- `_load_config()` merged `.members` files → hbaker resolved as researcher
- `allocate_gpu()` successfully returned GPU-0 for researcher

BUT when hbaker ran `container deploy`:
1. First hit PermissionError on `gpu-availability-checker.py` (file was 700)
2. After chmod, hit PermissionError on `config/groups/student.members` (files were 600)

Changes rolled back to avoid half-working state. Permissions fixed separately.

## What Works Now (After Rollback + Permission Fix)

- Scripts are readable (755)
- Config/members files are readable (644)
- `get_resource_limits.py` correctly resolves groups (members files now readable)
- BUT allocator still can't allocate GPUs (no MIG instances, code still only checks MIG)
- Stale container `suspicious_banzai` was removed (was holding phantom MIG allocation)

## Solution (For Tomorrow)

1. Apply the two code fixes (already tested, just need permission-safe implementation):
   - `gpu-availability-checker.py`: include full GPUs in `get_available_gpus()` and `get_allocation_summary()`
   - `gpu_allocator_v2.py`: merge `.members` files in `_load_config()` with PermissionError handling
2. Test as a non-admin user (su to hbaker or similar) BEFORE declaring done
3. Run full `container deploy` E2E test
4. Add umask/permission check to deploy.sh to prevent recurrence
5. Consider whether `allow_full_gpu: false` students should be able to get ANY GPU when MIG is disabled (policy decision)

## Related Todos

- Investigate wrapper group detection mismatch (same root cause: .members not read)
- Verify GPU/MIG allocation E2E via container deploy
