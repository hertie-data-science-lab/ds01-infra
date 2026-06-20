# DS01 Hybrid Resource Management - Quick Reference

## Summary

**GPU-slot allocation + cgroups + priority allocation**

> **Current state:** MIG is disabled. The server runs 4 full A100-40GB GPUs; one **GPU-slot** = one full GPU. Quotas are expressed in **GPU-equivalents (gpueq)** — a float where a full GPU = `1.0`. The model is MIG-ready; with MIG off, gpueq counts equal whole-GPU counts.

- GPU allocation is **dynamic** with **priority** awareness
- Today 4 users can run a full GPU each; with MIG enabled, slots subdivide for higher density
- CPU/RAM limits enforced via **cgroups**

---

## Limits

| Group | GPU quota (`max_gpu_equivalents`) | Slots/container (`max_gpu_slots_per_container`) | CPUs | Memory |
|-------|-----------------------------------|-------------------------------------------------|------|--------|
| **Student** | 2.0 | 2 | 32 | 32G |
| **Researcher** | 4.0 | 3 | 48 | 64G |
| **Faculty** | 4.0 | 4 | 64 | 128G |
| **Admin** | unlimited | unlimited | 64 | 128G |

Quota is **per user across all containers** (in gpueq); the slots/container value caps a single
container. Exact values and storage quotas live in `config/runtime/resource-limits.yaml`.
With MIG off, 1 slot = 1 full GPU = 1.0 gpueq, so e.g. a student can run up to 2 containers
each with one full GPU.

---

## GPU-slot model

```
Current (MIG off): 4× A100-40GB → 4 GPU-slots, each 1.0 gpueq
Optional (MIG on): each A100 partitions into MIG instances; each instance is one slot,
                   weighted by its compute fraction (compute_slices / 7)
```

**Device notation:**
- Full GPUs: `device=0` … `device=3` (or GPU UUIDs)
- MIG instances (if enabled): `GPU:instance`, e.g. `0:1` = GPU 0, instance 1

---

## Directory Structure

```
/var/lib/ds01/           → State (current allocations)
/var/log/ds01/          → All logs
/opt/ds01-infra/logs/    → Symlink to /var/log/ds01/
```

---

## Priority Allocation

**Order (highest first):** Overrides > Admins > Faculty > Researchers > Students
(exact numeric priorities in `resource-limits.yaml`)

**Strategy:**
1. Check reservations (highest priority)
2. Find empty GPU-slots first
3. Share a slot with same-priority users
4. Avoid displacing higher-priority users

---

## Commands

### Check GPU-slot status:
```bash
ds01-gpu-status                # Terminal
ds01-gpu-status --markdown     # Generate markdown
nvidia-smi                     # Raw GPU status
nvidia-smi mig -lgi            # MIG list (only if MIG enabled)
```

### Check your limits:
```bash
python3 /opt/ds01-infra/scripts/docker/get_resource_limits.py $USER
```

### Check your allocation:
```bash
python3 /opt/ds01-infra/scripts/docker/gpu_allocator.py user-status $USER
```

### Manual GPU operations (admin):
```bash
# Allocate (<slots> = number of GPU-slots requested)
python3 scripts/docker/gpu_allocator.py allocate <user> <container> <slots> <priority>

# Release
python3 scripts/docker/gpu_allocator.py release <container>

# Status
python3 scripts/docker/gpu_allocator.py status
```

---

## Log Files

```bash
# GPU allocations (includes priority info)
tail /var/log/ds01/gpu-allocations.log

# Format: timestamp|event|user|container|gpu_slot|priority=X|reason
```

---

## Example Scenarios

### Scenario 1: Student at quota

```bash
# Alice (student, max_gpu_equivalents 2.0, max_gpu_slots_per_container 2)

mlc-create training1 pytorch    # ✓ slot 0 allocated (1.0/2.0 gpueq)
mlc-create training2 pytorch    # ✓ slot 1 allocated (2.0/2.0 gpueq)
mlc-create training3 pytorch    # ✗ REJECTED: "USER_AT_LIMIT (2.0/2.0 gpueq)"
mlc-create preprocess pytorch --cpu-only   # ✓ (no GPU, doesn't count)
```

### Scenario 2: Priority Allocation

```bash
# 3 users request GPU-slots simultaneously
# slot 0: empty | slot 1: student | slot 2: researcher | slot 3: empty

# Admin       → slot 0 (empty, always first)
# Researcher  → slot 3 (next empty)
# Student     → least-loaded remaining slot, avoiding higher-priority users
```

### Scenario 3: Reservation

```yaml
# In config/runtime/resource-limits.yaml
user_overrides:
  john_doe:
    priority: 100
    reserved_gpus: [0]  # Reserve full GPU 0
    reservation_start: "2025-11-01T00:00:00"
    reservation_end: "2025-11-08T00:00:00"
```

**Effect:** GPU 0 only available to john_doe during that week.

---

## Optional: Enable MIG

MIG is disabled today — no setup needed. To partition GPUs for higher density:

```bash
sudo nvidia-smi -i 0,1,2,3 -mig 1
sudo reboot

# Create instances (example: 2g.20gb profile)
for gpu in 0 1 2 3; do
  sudo nvidia-smi mig -i $gpu -cgi 14,14,14 -C
done
nvidia-smi mig -lgi

# Reinitialise allocator state
sudo rm /var/lib/ds01/gpu-state.json
python3 scripts/docker/gpu_allocator.py status
```

The allocator detects the instances and weights each slot by its compute fraction.

---

## What Happens at Limits

### GPU quota (via allocator):
```
Alice at 2.0/2.0 gpueq → next GPU container rejected: "USER_AT_LIMIT"
→ Graceful error shown in wizard
```

### CPU limit (via cgroups):
```
Container exceeds its CPU quota → kernel throttles to the configured cores
```

### Memory limit (via cgroups):
```
Container exceeds its memory limit → OOM (allocation fails)
```

### GPU memory limit (hardware):
```
Process exceeds the slot's GPU memory (40GB full GPU, or the MIG partition size)
→ CUDA OOM; other slots unaffected
```

---

## Error Messages (User-Facing)

Configured in `config/runtime/resource-limits.yaml`:

**GPU quota exceeded:**
```
✗ GPU Limit Exceeded

Your GPU quota is 2.0 GPU-equivalents and you currently use 2.0.

Options:
1. Stop an existing container to free a slot
2. Launch this container without GPU (CPU-only)

Check your allocations: ds01-gpu-status
```

**No GPU available:**
```
No GPU-slots Available

All GPU-slots are currently allocated.

Options:
1. Wait for a slot to become available
2. Launch as CPU-only container
3. Check status: ds01-gpu-status
```

**Reservation conflict:**
```
✗ GPU Reserved

GPU 0 is reserved for john_doe until 2025-11-08.
Reason: Thesis deadline

Please use a different GPU or wait.
```

---

## Monitoring

### Check GPU-slot utilisation:
```bash
ds01-gpu-status
# Shows: slots, containers per slot, per-user gpueq summary, priorities, reservations
```

### Check cgroups:
```bash
systemctl status ds01.slice
systemd-cgtop --depth=3
```

---

## Troubleshooting

```bash
# Is MIG enabled? (no instances → full-GPU mode, expected today)
nvidia-smi mig -lgi

# GPU allocator broken?
sudo rm /var/lib/ds01/gpu-state.json
python3 scripts/docker/gpu_allocator.py status

# User stuck at quota?
python3 scripts/docker/gpu_allocator.py user-status <user>
python3 scripts/docker/gpu_allocator.py release <container>  # If needed

# Priority not working?
python3 scripts/docker/get_resource_limits.py <user> --priority
tail /var/log/ds01/gpu-allocations.log | grep priority
```

---

## Key Differences from Old System

| Aspect | Old | New |
|--------|-----|-----|
| Allocation | Manual | Dynamic + priority |
| Quota unit | Whole GPUs | GPU-equivalents (gpueq, float) |
| Per-container cap | — | `max_gpu_slots_per_container` |
| MIG-ready | No | Yes (slots weight by compute fraction) |

---

## Files Reference

- `scripts/docker/gpu_allocator.py` — slot + priority aware allocator
- `scripts/monitoring/gpu-status-dashboard.py` — status dashboard
- `scripts/system/setup-var-directories.sh` — state/log directories
- `config/runtime/resource-limits.yaml` — priorities, reservations, gpueq quotas
- `scripts/docker/get_resource_limits.py` — per-user limit lookup

**Full docs:** `/opt/ds01-infra/docs/admin/`
