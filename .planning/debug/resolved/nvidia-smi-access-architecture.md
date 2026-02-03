---
status: verifying
trigger: "nvidia-smi-access-architecture"
created: 2026-02-01T00:00:00Z
updated: 2026-02-01T00:30:00Z
---

## Current Focus

hypothesis: CONFIRMED - nvidia-smi wrapper violates HPC architecture. nvidia-smi is a query tool, not a compute tool. Blocking it breaks GPU allocation chain.
test: Implement fix - remove wrapper blocking, rely on device permissions + CUDA_VISIBLE_DEVICES
expecting: After removing wrapper (or making it pass-through), nvidia-smi queries work for all users. GPU compute still blocked via CUDA_VISIBLE_DEVICES="". Allocation chain works end-to-end.
next_action: Implement fix and verify

## Symptoms

expected: All users should be able to run nvidia-smi (query tool) to see GPU status. GPU COMPUTE on host should be blocked for non-exempt users. Container deploy should work end-to-end.
actual: nvidia-smi wrapper at /usr/local/bin/nvidia-smi blocks ALL access for non-video-group users. Shows "Bare Metal GPU Access Restricted" error. This breaks the GPU allocation chain, dashboard, container list, and container deploy flow.
errors: "Bare Metal GPU Access Restricted" from nvidia-wrapper.sh, then downstream "No GPUs Currently Available" from allocation chain, "Container 'test' does not exist" from container deploy
reproduction: Log in as any non-video-group user (e.g. h.baker@hertie-school.lan) and run nvidia-smi. It's blocked. Then try container deploy — it fails because the allocation chain can't enumerate GPUs.
started: Started when Phase 3.1 restricted video group to exempt users only and deployed nvidia-smi wrapper. Before that, all users were in video group so nvidia-smi worked.

## Eliminated

## Evidence

- timestamp: 2026-02-01T00:00:00Z
  checked: Initial context analysis
  found: DS01 has three-layer GPU control (CUDA_VISIBLE_DEVICES, Docker --gpus, video group). nvidia-smi wrapper blocks ALL access for non-video users including queries.
  implication: nvidia-smi is being treated as a compute tool when it's actually a query tool. This is likely not how production HPC systems handle it.

- timestamp: 2026-02-01T00:05:00Z
  checked: Web research on HPC/SLURM/K8s patterns
  found:
    - SLURM uses cgroups ConstrainDevices=yes to restrict /dev/nvidia* access per job
    - CUDA_VISIBLE_DEVICES controls what CUDA jobs can see (standard HPC approach)
    - K8s GPU Operator doesn't install nvidia-smi on host (pod-only access)
    - HPC clusters allow nvidia-smi via device file permissions (0666 or video group)
    - nvidia-smi queries require read access to /dev/nvidia* but don't do GPU compute
  implication: Production systems separate device access (for queries) from compute control (via CUDA_VISIBLE_DEVICES/cgroups). nvidia-smi access is controlled via device permissions, not wrapper scripts.

- timestamp: 2026-02-01T00:10:00Z
  checked: Current DS01 implementation (nvidia-wrapper.sh, ds01-gpu-awareness.sh)
  found:
    - nvidia-wrapper.sh blocks ALL nvidia-smi access for non-video-group users
    - ds01-gpu-awareness.sh sets CUDA_VISIBLE_DEVICES="" for non-exempt users (correct for compute blocking)
    - Video group is restricted to exempt users only (Phase 3.1 change)
    - Device files are 0660 root:video (kernel enforces this via ModifyDeviceFiles=1)
    - 0666 modprobe.d config exists but needs reboot to take effect
  implication: The wrapper is architecturally wrong. CUDA_VISIBLE_DEVICES="" already blocks GPU compute. Device permissions control nvidia-smi access, not wrapper scripts.

- timestamp: 2026-02-01T00:15:00Z
  checked: GPU allocation chain dependencies on nvidia-smi
  found:
    - gpu-availability-checker.py calls /usr/bin/nvidia-smi -L (line 41)
    - Uses GPU_INVENTORY_CACHE fallback (/var/lib/ds01/gpu-inventory.cache) when device access denied
    - gpu_allocator_v2.py calls /usr/bin/nvidia-smi -L (line 588)
    - Cache workaround is a hack — doesn't cover all nvidia-smi use cases (dashboard, monitoring)
    - Dashboard and container-list need live nvidia-smi access
  implication: The wrapper breaks the entire GPU allocation chain. Cache is insufficient. nvidia-smi MUST be accessible to all users for the system to function.

## Resolution

root_cause: TWO architectural errors introduced in Phase 3.1:

1. **nvidia-smi wrapper blocks ALL nvidia-smi access** for non-video-group users. nvidia-smi is a QUERY tool (reads GPU state), not a compute tool. It doesn't do GPU compute operations. Production HPC systems (SLURM, K8s) allow nvidia-smi queries for all users while restricting GPU compute via CUDA_VISIBLE_DEVICES and cgroups. The wrapper breaks the GPU allocation chain (gpu_allocator_v2.py), dashboard, and monitoring.

2. **deploy.sh restricts video group to exempt users only** (lines 361-416). This removes all non-exempt docker users from video group. But /dev/nvidia* devices are 0660 root:video, so non-video users can't access nvidia-smi. This contradicts add-user-to-docker.sh which adds ALL docker users to video group for nvidia-smi access (lines 54-60).

The architectural design was correct: video group for nvidia-smi device access, CUDA_VISIBLE_DEVICES="" for compute blocking. But Phase 3.1 broke it by removing users from video group AND adding a wrapper that blocks nvidia-smi.

fix: Restore the original three-layer architecture:
- **Layer 1 (Host compute deterrent)**: CUDA_VISIBLE_DEVICES="" for non-exempt users — ALREADY CORRECT
- **Layer 2 (Container security)**: Docker --gpus device=X pinning — ALREADY CORRECT
- **Layer 3 (Bare-metal GPU access)**: Video group membership + device permissions — NEEDS FIX

Changes required:
1. **Remove nvidia-smi wrapper** — Blocking nvidia-smi breaks GPU allocation chain. nvidia-smi is a query tool, not a compute tool. (scripts/system/deploy.sh lines 345-359)

2. **Restore all docker users to video group** — Video group membership is needed for /dev/nvidia* access (devices are 0660 root:video). This allows nvidia-smi to work, but CUDA_VISIBLE_DEVICES="" still blocks GPU compute on the host. (scripts/system/deploy.sh lines 361-416)

3. **Update architecture documentation** — Clarify that video group enables nvidia-smi access (device communication), NOT bare-metal GPU compute. Bare-metal compute is controlled by CUDA_VISIBLE_DEVICES="" and bare-metal-access grants.

Implementation:
1. Comment out wrapper deployment in scripts/system/deploy.sh (lines 345-359) ✓ DONE
2. Comment out video group restriction in scripts/system/deploy.sh (lines 361-416) ✓ DONE
3. Remove existing wrapper symlinks + re-add users to video group: RUN SCRIPT BELOW

**User must run:**
```bash
sudo bash /opt/ds01-infra/.planning/debug/fix-nvidia-smi-access.sh
```

This script will:
- Remove nvidia-* wrapper symlinks from /usr/local/bin
- Re-add all docker users to video group
- Verify nvidia-smi access

verification:
  status: Code changes complete. Fix script and verification script created.
  apply_fix: sudo bash /opt/ds01-infra/.planning/debug/fix-nvidia-smi-access.sh
  verify_fix: bash /opt/ds01-infra/.planning/debug/verify-nvidia-smi-access.sh
  test_user: Test container deploy as h.baker@hertie-school.lan after user re-login

  expected_results:
    - nvidia-smi accessible to all docker users
    - GPU allocation chain works (gpu_allocator_v2.py enumerates GPUs)
    - Dashboard shows GPU info
    - container deploy works end-to-end without "No GPUs Available" error
    - CUDA_VISIBLE_DEVICES="" still blocks host GPU compute for non-exempt users

files_changed:
  - scripts/system/deploy.sh (nvidia wrapper disabled lines 345-359, video restriction disabled lines 361-416)
  - .planning/debug/fix-nvidia-smi-access.sh (created - removes wrappers, restores video group)
  - .planning/debug/verify-nvidia-smi-access.sh (created - verification tests)
  - .planning/debug/APPLY-FIX-nvidia-smi-access.md (created - comprehensive fix guide)
  - /usr/local/bin/nvidia-* (symlinks to be removed by fix script)
  - /etc/group (video group memberships to be restored by fix script)
