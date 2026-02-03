# nvidia-smi Access Architecture Fix

## Summary

**Problem:** nvidia-smi wrapper blocks ALL nvidia-smi access for non-video-group users. This breaks GPU allocation chain, dashboard, container deploy, and monitoring.

**Root Cause:** Two architectural errors in Phase 3.1:
1. nvidia-smi wrapper treats nvidia-smi as a compute tool when it's a query tool
2. deploy.sh removes all non-exempt users from video group, preventing /dev/nvidia* device access

**Solution:** Restore the original three-layer architecture where:
- nvidia-smi queries work for all docker users (need video group for device access)
- GPU compute is blocked via CUDA_VISIBLE_DEVICES="" (already working correctly)
- Container GPU access controlled via Docker --gpus device=X (already working correctly)

## Research Foundation

Production HPC systems (SLURM, Kubernetes) separate nvidia-smi query access from GPU compute:
- **SLURM**: Uses cgroups ConstrainDevices=yes to restrict GPU devices per job, CUDA_VISIBLE_DEVICES for visibility
- **Kubernetes**: GPU Operator manages device access; nvidia-smi accessible in appropriate contexts
- **HPC Clusters**: Device permissions (0666 or video group) allow nvidia-smi, CUDA_VISIBLE_DEVICES blocks compute

nvidia-smi only READS GPU state via /dev/nvidia* devices. It doesn't perform compute operations.

## Fix Applied (Code Changes)

### 1. scripts/system/deploy.sh

**Lines 345-359:** Disabled nvidia-smi wrapper deployment
```bash
# --- Deploy nvidia-* wrappers (DISABLED — breaks GPU allocation chain) ---
# nvidia-smi is a QUERY tool (reads GPU state), not a compute tool.
# ... commented out wrapper deployment loop
```

**Lines 361-416:** Disabled video group restriction
```bash
# --- Video group management (DISABLED — all docker users need video for nvidia-smi) ---
# Video group membership enables nvidia-smi access via /dev/nvidia* devices (0660 root:video).
# This does NOT grant bare-metal GPU compute — that's controlled by CUDA_VISIBLE_DEVICES=""
# ... commented out video group restriction logic
```

## Apply Fix (Run These Commands)

### Step 1: Run Fix Script (Requires sudo)

```bash
sudo bash /opt/ds01-infra/.planning/debug/fix-nvidia-smi-access.sh
```

This will:
- Remove nvidia-* wrapper symlinks from /usr/local/bin
- Re-add all docker users to video group
- Verify nvidia-smi access

### Step 2: Users Must Re-login

**IMPORTANT:** Users must log out and log back in for group changes to take effect.

### Step 3: Verify Fix

```bash
# As root or admin
bash /opt/ds01-infra/.planning/debug/verify-nvidia-smi-access.sh

# Or test specific user
bash /opt/ds01-infra/.planning/debug/verify-nvidia-smi-access.sh h.baker@hertie-school.lan
```

### Step 4: Test Container Deploy End-to-End

```bash
# As a non-exempt user (e.g., h.baker@hertie-school.lan)
container deploy test-fix
```

Should work without "No GPUs Currently Available" error.

## Verification Checklist

After applying fix:

- [ ] nvidia-smi works for all docker users (not just exempt users)
- [ ] GPU allocation chain works (gpu_allocator_v2.py can enumerate GPUs)
- [ ] Dashboard shows GPU information
- [ ] container deploy works end-to-end
- [ ] CUDA_VISIBLE_DEVICES="" still blocks host GPU compute for non-exempt users
- [ ] Bare-metal GPU access still controlled by exempt_users + grants

## Architecture After Fix

```
┌─────────────────────────────────────────────────────────────┐
│ Layer 1: CUDA_VISIBLE_DEVICES="" (Host Compute Deterrent)   │
│ • Blocks PyTorch, TensorFlow, CUDA apps on host             │
│ • Set for all non-exempt users via ds01-gpu-awareness.sh    │
│ • Does NOT block nvidia-smi (query tool)                    │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 2: Docker --gpus device=X (Container Security)        │
│ • Pinned GPU access per container                           │
│ • Managed by gpu_allocator_v2.py                            │
│ • Prevents cross-user GPU access                            │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│ Layer 3: Video Group + Device Permissions (Query Access)    │
│ • /dev/nvidia* devices are 0660 root:video                  │
│ • All docker users in video group → nvidia-smi works        │
│ • Bare-metal compute controlled by Layer 1, not video group │
└─────────────────────────────────────────────────────────────┘
```

## What Changed vs. Original Design

**Original (Correct):**
- All docker users in video group → nvidia-smi works for everyone
- CUDA_VISIBLE_DEVICES="" blocks compute for non-exempt users

**Phase 3.1 (Broken):**
- Only exempt users in video group → nvidia-smi broken for most users
- Added nvidia-smi wrapper → blocked even for video group users without wrapper exemption

**After Fix (Restored):**
- All docker users in video group → nvidia-smi works for everyone
- CUDA_VISIBLE_DEVICES="" blocks compute for non-exempt users
- nvidia-smi wrapper removed → no artificial blocking

## Files Modified

```
scripts/system/deploy.sh
  • Lines 345-359: nvidia-smi wrapper deployment disabled
  • Lines 361-416: video group restriction disabled

.planning/debug/fix-nvidia-smi-access.sh (created)
  • Removes wrapper symlinks
  • Re-adds docker users to video group

.planning/debug/verify-nvidia-smi-access.sh (created)
  • Tests nvidia-smi access end-to-end
  • Verifies GPU allocation chain
```

## Next Steps

1. Apply fix: `sudo bash /opt/ds01-infra/.planning/debug/fix-nvidia-smi-access.sh`
2. Notify users to re-login
3. Verify: `bash /opt/ds01-infra/.planning/debug/verify-nvidia-smi-access.sh`
4. Test container deploy as non-exempt user
5. Commit fix if verification passes

## References

- Debug session: `.planning/debug/nvidia-smi-access-architecture.md`
- HPC research: SLURM cgroups, K8s GPU Operator, CUDA_VISIBLE_DEVICES best practices
- Related files: `scripts/admin/nvidia-wrapper.sh`, `config/deploy/profile.d/ds01-gpu-awareness.sh`

---

**Debug Session:** `.planning/debug/nvidia-smi-access-architecture.md`
**Created:** 2026-02-01
**Status:** Ready to apply (code changes complete, awaiting script execution)
