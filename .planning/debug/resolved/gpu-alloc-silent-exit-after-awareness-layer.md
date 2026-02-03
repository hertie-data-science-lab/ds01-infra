---
status: resolved
trigger: "Fix issue: gpu-alloc-silent-exit-after-awareness-layer - Replace device-permission-based awareness layer with CUDA_VISIBLE_DEVICES approach"
created: 2026-01-31T00:00:00Z
updated: 2026-01-31T00:45:00Z
---

## Current Focus

hypothesis: Device permission restrictions on /dev/nvidia* break nvidia-smi, which GPU allocator depends on. CUDA_VISIBLE_DEVICES="" achieves same awareness goal while keeping nvidia-smi functional.
test: Examine recent commits and system files to find all device-permission changes, then replace with CUDA_VISIBLE_DEVICES approach.
expecting: Will find nvidia permission configs in modprobe.d, udev rules, deploy script, and possibly nvidia-smi caching logic.
next_action: Examine recent commits and system configuration files

## Symptoms

expected: GPU allocation should work after awareness layer implementation. nvidia-smi should work for system tools while preventing direct PyTorch/CUDA access from host.
actual: GPU allocation silently fails because nvidia-smi cannot run with restricted device permissions (0660, group video). This breaks the entire allocation pipeline.
errors: nvidia-smi fails with permission errors when /dev/nvidia* devices are restricted.
reproduction: After awareness layer commits, run container deploy as normal user - allocator fails silently.
started: After commits c9a623c through a596b59 implementing device-permission-based awareness layer.

## Eliminated

## Evidence

- timestamp: 2026-01-31T00:05:00Z
  checked: Recent commits and system files
  found: |
    Device permission awareness layer implemented across multiple files:
    - /etc/modprobe.d/nvidia-permissions.conf: Sets NVreg_DeviceFileGID=44 NVreg_DeviceFileMode=432
    - /etc/udev/rules.d/99-ds01-nvidia.rules: Overrides nvidia devices to 0660 video group
    - /usr/sbin/ub-device-create: Wrapper that fixes permissions after device creation
    - deploy.sh lines 489-515: nvidia-smi caching and final permission enforcement
    - gpu-availability-checker.py, gpu-state-reader.py: nvidia-smi cache fallback logic
  implication: Entire device-permission infrastructure needs replacement with CUDA_VISIBLE_DEVICES

- timestamp: 2026-01-31T00:10:00Z
  checked: Recent fixes in commits 6ef0b7c and b6ca9bd
  found: |
    Good fixes to keep:
    - mlc-create-wrapper.sh: set +e/set -e around GPU allocator calls (defensive)
    - grep -c pattern fixes in 11 files (correct bug fix)
    - _is_full_gpu() MIG UUID prefix check (defensive coding)
    Bad additions to remove:
    - nvidia-smi caching infrastructure (lines 489-501 in deploy.sh)
    - Cache reading in gpu-availability-checker.py and gpu-state-reader.py
  implication: Keep defensive fixes, remove caching workaround

## Resolution

root_cause: Device permission restrictions (0660, group video) on /dev/nvidia* prevent nvidia-smi from working for regular users, breaking GPU allocation pipeline. CUDA_VISIBLE_DEVICES="" is the standard HPC approach - achieves awareness goal while keeping nvidia-smi functional.

fix: |
  Implemented architectural change from device permissions to CUDA_VISIBLE_DEVICES:

  1. Created config/deploy/profile.d/ds01-gpu-awareness.sh
     - Sets CUDA_VISIBLE_DEVICES="" for all users
     - Standard HPC approach (SLURM, etc.)
     - Makes torch.cuda.is_available() return False
     - nvidia-smi remains functional

  2. Updated scripts/system/deploy.sh
     - Removed ub-device-create wrapper deployment (lines 263-283)
     - Removed udev rules deployment (lines 286-292)
     - Removed modprobe.d deployment (lines 295-301)
     - Removed nvidia-smi caching (lines 489-501)
     - Removed final permission enforcement (lines 503-515)
     - Added ds01-gpu-awareness.sh deployment

  3. Reverted nvidia-smi cache logic
     - gpu-availability-checker.py: Removed cache file reading, direct nvidia-smi
     - gpu-state-reader.py: Removed cache file reading, direct nvidia-smi

  4. Created scripts/system/restore-nvidia-defaults.sh
     - Restores original ub-device-create
     - Removes udev rules and modprobe.d config
     - Resets device permissions to 0666 root:root
     - Removes cache file

  5. Kept defensive fixes (as instructed)
     - mlc-create-wrapper.sh: set +e/set -e around GPU allocator calls
     - grep -c pattern fixes in 11 files
     - _is_full_gpu() MIG UUID prefix check

verification: |
  User must complete these steps manually (requires sudo and logout/login):

  1. Restore NVIDIA device permissions to defaults:
     $ sudo /opt/ds01-infra/scripts/system/restore-nvidia-defaults.sh

  2. Deploy new awareness layer:
     $ sudo deploy

  3. Logout and login again (to apply CUDA_VISIBLE_DEVICES env var)

  4. Verify awareness layer:
     $ /opt/ds01-infra/scripts/system/verify-cuda-awareness.sh

  5. Test GPU allocation:
     $ container deploy test-project

  Expected results:
    • nvidia-smi -L works and lists GPUs
    • python3 -c "import torch; print(torch.cuda.is_available())" → False
    • container deploy succeeds (GPU allocation works)

files_changed:
  - config/deploy/profile.d/ds01-gpu-awareness.sh (created)
  - scripts/system/deploy.sh (modified)
  - scripts/docker/gpu-availability-checker.py (modified)
  - scripts/docker/gpu-state-reader.py (modified)
  - scripts/system/restore-nvidia-defaults.sh (created helper)
  - scripts/system/verify-cuda-awareness.sh (created helper)
