# Permanent Fix: NVIDIA Device Permissions 0666

## Summary

The NVIDIA kernel module on ds01 creates `/dev/nvidia*` devices at 0660 root:video by default. DS01's three-layer GPU access control architecture requires 0666 (world-accessible) — security is enforced at Layer 1 (CUDA_VISIBLE_DEVICES) and Layer 2 (Docker --gpus device mapping), not at the device level.

A **workaround** is in place (GPU inventory cache), but the underlying device permissions issue remains unresolved. On reboot, the modprobe.d fix *should* take effect, but this needs verification.

## Current Workaround

GPU allocation chain reads from `/var/lib/ds01/gpu-inventory.cache` instead of calling `nvidia-smi -L` directly. Cache is refreshed by:
- `deploy.sh` on each deploy
- Workload detector every 30s (systemd timer)
- `mig-configure` and `ds01-mig-partition` after topology changes

## What Needs Doing

1. **Verify modprobe.d fix on next reboot** — `config/deploy/modprobe.d/nvidia-permissions.conf` sets `NVreg_DeviceFileMode=438` (0666). Check `/proc/driver/nvidia/params` shows `DeviceFileMode: 438` and devices are created at 0666.

2. **If modprobe.d works**: the cache is still good as a performance optimisation (avoids subprocess call) but device permissions will also be correct. Clean up the udev rule + immediate chmod in deploy.sh (redundant).

3. **If modprobe.d doesn't work**: investigate further. The kernel module may not honour modprobe.d params if loaded early in boot. May need initramfs rebuild (`update-initramfs -u`).

## Bug History & References

This issue has been investigated across multiple sessions:

| File | What it covers |
|------|---------------|
| `.planning/debug/nvidia-device-permissions-persist-666.md` | First investigation — found kernel module params, created modprobe.d config (but set 0660 — WRONG direction for DS01) |
| `.planning/debug/nvidia-permissions-fix-deployment.md` | Deployment instructions for the modprobe.d fix |
| `.planning/debug/gpu-full-gpu-allocation-broken.md` | GPU allocation broken because mlc-create deployed as copy, not symlink — dependencies missing |
| `.planning/debug/gpu-alloc-silent-exit-after-awareness-layer.md` | Earlier GPU allocation silent failure |
| `.planning/phases/02.1-gpu-access-control-research/` | Phase 2.1 research — concluded SLURM/K8s use 0666, device restriction is anti-pattern |
| `.planning/phases/03.1-hardening-deployment-fixes/.continue-here.md` | Phase 3.1 checkpoint where blocker was discovered |

## Key Facts

- **NVIDIA driver default** on this system: 0660 root:video (via kernel module `NVreg_DeviceFileGID=44 NVreg_DeviceFileMode=432`)
- **DS01 requires**: 0666 (so non-video-group users can enumerate GPUs for allocation)
- **modprobe.d config**: `config/deploy/modprobe.d/nvidia-permissions.conf` — sets 0666, deployed to `/etc/modprobe.d/`
- **udev rule**: `config/deploy/udev/99-ds01-nvidia.rules` — belt-and-suspenders 0666
- **Kernel param `ModifyDeviceFiles=1`** means the kernel module actively manages device perms — chmod gets overridden
- **sysfs params not exposed** — `/sys/module/nvidia/parameters/` has no writable NVreg files

## Priority

Low — workaround is stable. Revisit on next reboot or maintenance window.
