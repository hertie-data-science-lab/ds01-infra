# GPU Permissions & Access Control: Consolidated Record

## Status: Complete — architecture deployed and verified

## Current Architecture (Correct)

```
Layer 1: CUDA_VISIBLE_DEVICES=""    → profile.d deterrent, blocks host GPU compute
Layer 2: Docker --gpus device=UUID  → kernel-level security boundary (container only)
Layer 3: video group membership     → nvidia-smi query access (all docker users)

Bare-metal exemptions (bypass Layer 1):
  - Grant file: /var/lib/ds01/bare-metal-grants/<user>.json
  - Config: resource-limits.yaml bare_metal_access.exempt_users
```

## Timeline

| When | What | Outcome |
|------|------|---------|
| 2026-01-31 ~21:00 | Phase 2.1 research | SLURM/K8s use CUDA_VISIBLE_DEVICES, not device perms |
| 2026-01-31 ~22:00 | Design document | Three-layer architecture defined |
| 2026-01-31 late | deploy_cmd copy bug | Fixed: deploy_cmd uses ln -sf |
| 2026-01-31 late | modprobe.d created (0660) | WRONG direction — later corrected to 0666 in repo |
| 2026-02-01 AM | Phase 3.1-03 deployed | nvidia-wrapper.sh + video group restriction deployed |
| 2026-02-01 PM | nvidia-smi wrapper broke allocation | Wrapper disabled, video group restored for all docker users |
| 2026-02-01 PM | GPU cache workaround added | Works but vestigial — nvidia-smi now works directly |
| 2026-02-01 PM | profile.d video group check removed | CUDA_VISIBLE_DEVICES="" now correctly set for non-exempt users |
| 2026-02-01 PM | bare-metal-access status fixed | Checks grant files + config, not video group |

## Outstanding Items

### Must do (next reboot) — DONE 2026-02-01
- [x] Run `sudo deploy` to update `/etc/modprobe.d/nvidia-permissions.conf` to 0666
- [x] Reboot to apply modprobe.d changes
- [x] Verify: `cat /proc/driver/nvidia/params | grep DeviceFile` shows Mode=438, GID=0
- [x] Verify: `stat -c '%a' /dev/nvidia0` shows 666

### Should do (cleanup) — DONE 2026-02-01
- [x] Remove commented-out wrapper deployment from deploy.sh
- [x] Remove commented-out video group restriction from deploy.sh
- [x] Remove GPU cache write from deploy.sh
- [x] Remove GPU cache fallback from gpu-availability-checker.py, gpu-state-reader.py, gpu_allocator_v2.py
- [x] Remove GPU cache writes from mig-configure, ds01-mig-partition, detect-workloads.py
- [x] Archive resolved debug files
- [x] Update Phase 2.1 design doc to match implementation (grant files, not video group for exemptions)

### Known bugs
- [ ] Dashboard doesn't show GPU allocations (see todo)
- [ ] No clear error message for host GPU compute attempts (see todo)

## Design Divergence: Documented vs Implemented

Phase 2.1 design says: video group controls exemption
Implementation says: grant files + config exempt_users control exemption

**Implementation is better** — grant files are checked every shell start (no re-login needed).
Design document should be updated to match.

## Debug Files Index

| File | Status | Action |
|------|--------|--------|
| `nvidia-device-permissions-persist-666.md` | Archived | In resolved/ |
| `nvidia-permissions-fix-deployment.md` | Archived | In resolved/ |
| `gpu-full-gpu-allocation-broken.md` | Archived | In resolved/ |
| `gpu-alloc-silent-exit-after-awareness-layer.md` | Archived | In resolved/ |
| `nvidia-smi-access-architecture.md` | Archived | In resolved/ |
| `nvidia-device-permissions-0666-fix.md` | Archived | In resolved/ — verified post-reboot |
| `fix-nvidia-smi-access.sh` | Deleted | Applied and confirmed |
| `verify-nvidia-smi-access.sh` | Active | Kept for re-verification |
| `APPLY-FIX-nvidia-smi-access.md` | Archived | In resolved/ |
| `CONSOLIDATED-gpu-permissions-access-control.md` | This file | Primary reference |

## Key Files (current implementation)

| File | Role |
|------|------|
| `config/deploy/profile.d/ds01-gpu-awareness.sh` | Sets CUDA_VISIBLE_DEVICES="" for non-exempt users |
| `config/deploy/modprobe.d/nvidia-permissions.conf` | Kernel module params: 0666 (pending reboot) |
| `config/deploy/udev/99-ds01-nvidia.rules` | Belt-and-suspenders 0666 udev rule |
| `scripts/admin/bare-metal-access` | Grant/revoke/status CLI for bare-metal exemptions |
| `scripts/system/add-user-to-docker.sh` | Adds users to docker + video groups |
| `scripts/system/deploy.sh` | Deploys modprobe.d, udev, profile.d, cache |
| `scripts/docker/gpu-availability-checker.py` | GPU enumeration (cache fallback) |
| `scripts/docker/gpu-state-reader.py` | GPU state from Docker labels (cache fallback) |
| `scripts/docker/gpu_allocator_v2.py` | GPU allocation with UUID lookup (cache fallback) |
| `scripts/monitoring/detect-workloads.py` | Refreshes GPU cache every 30s |
| `scripts/admin/mig-configure` | Refreshes GPU cache after MIG changes |

## Research References

- `.planning/phases/02.1-gpu-access-control-research/02.1-RESEARCH.md` — HPC industry survey
- `.planning/phases/02.1-gpu-access-control-research/02.1-DESIGN.md` — Architecture design
- `.planning/phases/02.1-gpu-access-control-research/02.1-01-SUMMARY.md` — Research plan summary
- `.planning/phases/02.1-gpu-access-control-research/02.1-02-SUMMARY.md` — Implementation plan summary
