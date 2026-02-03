---
created: 2026-01-31T22:58
title: Verify GPU/MIG allocation end-to-end via container deploy
area: tooling
files:
  - scripts/docker/gpu_allocator_v2.py
  - scripts/docker/gpu-availability-checker.py
  - scripts/docker/gpu-state-reader.py
  - scripts/docker/mlc-create-wrapper.sh:400-490
  - scripts/user/orchestrators/container-deploy
---

## Problem

The GPU availability checker was only looking for MIG instances and ignoring full GPUs when MIG is not enabled. A fix was applied (2026-01-31) to include full GPUs in `get_available_gpus()` and `get_allocation_summary()`. However, a thorough end-to-end verification is needed to confirm:

1. **Full GPU allocation path**: `container deploy` → `mlc-create-wrapper.sh` → `gpu_allocator_v2.py allocate` → `gpu-availability-checker.py suggest_gpu_for_user()` correctly allocates a full GPU and passes the GPU UUID through to `--gpus device=<UUID>` in the container creation.

2. **MIG allocation path**: When MIG is re-enabled, the same flow works with MIG instances (slot IDs like "0.1" mapped to MIG UUIDs).

3. **Multi-GPU allocation**: `allocate-multi` works for both full GPUs and MIG instances.

4. **External allocation**: `allocate-external` (docker-wrapper.sh path) works for devcontainers/compose with both modes.

5. **Stale cleanup**: `release-stale` correctly handles containers with full GPU vs MIG allocations.

6. **Status display**: `gpu_allocator_v2.py status` and `dashboard` correctly report full GPU vs MIG allocations.

This should include a real `container deploy` test with an actual user to verify the full chain works on the live system.

## Solution

TBD — run manual `container deploy` as a test user (or hbaker), verify GPU is allocated and container starts with correct `--gpus device=` flag. Check Docker inspect labels match. Also consider adding integration tests to `/testing/` that cover both MIG and full-GPU allocation paths.
