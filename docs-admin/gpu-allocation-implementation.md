# GPU Allocation & Cgroups Implementation Guide

## Overview

Hybrid resource management system built on **GPU-slot allocation**:
- **cgroups (systemd slices)**: CPU/RAM/task limits (kernel enforcement)
- **Dynamic GPU allocation**: Per-container, priority-aware, on-demand
- **Storage quotas**: Per-user workspace/data limits
- **Single YAML config**: Source of truth for all limits
- **MIG-ready**: Slots map to full GPUs today, or to MIG instances if partitioning is ever enabled

> **Current state:** MIG is disabled. The server runs 4 full A100-40GB GPUs; one **GPU-slot** = one full GPU. The **GPU-equivalent (gpueq)** model below is MIG-ready, but every weight is `1.0` today, so gpueq counts equal whole-GPU counts.

---

## Concepts: slots vs GPU-equivalents

- **GPU-slot** — an allocatable GPU unit. Today (MIG off) one slot = one full A100. If MIG were enabled, a slot could be a single MIG instance.
- **GPU-equivalent (gpueq)** — the fair-share *quota* unit, a floating-point compute fraction. A full GPU is `1.0`; a MIG instance is its compute fraction (`compute_slices / 7`). Weights are computed live per allocation, so the model is correct under heterogeneous or partial MIG. With MIG off, all weights are `1.0` and gpueq == slot count.

Two distinct caps per user (see `config/runtime/resource-limits.yaml`):
- `max_gpu_equivalents` — float, total fair-share quota **across all** the user's containers.
- `max_gpu_slots_per_container` — integer, max distinct GPU/MIG units in **a single** container.

---

## Key Design Decisions

### 1. **GPU-Slot Allocation for Fair GPU Sharing**

**Problem:** 4 GPUs, many users, episodic workloads.

**Solution:** allocate GPU-slots dynamically on container start, tracking each user's
GPU-equivalent usage against their quota.

```
Current hardware: 4× A100-40GB, MIG disabled
  → 4 GPU-slots (one per full GPU), each 1.0 gpueq

Optional (MIG enabled): each A100 can be partitioned into MIG instances
  → each instance is one slot, weighted by its compute fraction (slices/7)
```

The allocator auto-detects whether MIG is enabled and allocates accordingly — no code
change is needed to move between full-GPU and MIG modes.

### 2. **Dynamic Allocation with Priority**

**Priority order (highest first):**
1. **Specific overrides** — reserved resources
2. **Admins** — no limits
3. **Faculty** / **Researchers** — higher quotas (see config for exact gpueq values)
4. **Students** — base quotas

Exact numeric priorities live in `config/runtime/resource-limits.yaml`.

**Allocation happens when a container starts:**
- User launches → system finds the least-loaded GPU-slot
- Respects priority (higher-priority users get first pick)
- Container stops → slot released immediately
- Per-container (users are also capped on simultaneous containers)
- Responsive: designed for containers to be spun up and down frequently

### 3. **Directory Structure**

```
/var/lib/ds01/                  State data
├── gpu-state.json              Current allocations (slot + gpueq tracking)
└── container-metadata/         Per-container info

/var/log/ds01/                  All logs
├── gpu-allocations.log         GPU allocation events
├── metrics/                    Daily metrics
├── reports/                    Compiled reports
└── audits/                     System audits

/opt/ds01-infra/logs/          Symlink → /var/log/ds01/
```

---

## Example Scenarios

### Scenario 1: Student at Limit

**Alice (student — `max_gpu_equivalents: 2.0`, `max_gpu_slots_per_container: 2`, 32 CPUs per container):**

```bash
# 1. Launch first container with a GPU
container run training1 pytorch
# → Gets GPU-slot 0 (full GPU, 1.0 gpueq)
# → Alice usage: 1.0 / 2.0 gpueq ✓

# 2. Launch second container with a GPU
container run training2 pytorch
# → Gets GPU-slot 1 (1.0 gpueq)
# → Alice usage: 2.0 / 2.0 gpueq ✓

# 3. Try a third container with a GPU
container run training3 pytorch
# ✗ REJECTED: "USER_AT_LIMIT (2.0/2.0 gpueq)"

# 4. Try a single container requesting 3 slots
container run big pytorch --num-migs 3
# ✗ REJECTED: exceeds max_gpu_slots_per_container (2)

# 5. Launch a CPU-only container
container run preprocessing pytorch --cpu-only
# ✓ SUCCESS (does not count against the GPU quota)

# 6. A container tries to use 40 CPU cores
# cgroups throttles it to the configured CPU quota
```

### Scenario 2: Priority Allocation

```
GPU-slots:
- slot 0 (empty)
- slot 1 (bob/student container, priority low)
- slot 2 (carol/researcher container, priority high)
- slot 3 (empty)

New allocation requests arrive simultaneously:
1. Dave (admin)       → slot 0 (empty, always first choice)
2. Eve  (researcher)  → slot 3 (next empty slot)
3. Frank (student)    → least-loaded remaining slot, avoiding higher-priority users

Result: empty slots fill first; the allocator avoids displacing higher-priority users.
```

### Scenario 3: Time-Based Reservation

**Researcher John needs a dedicated GPU for thesis week:**

```yaml
# config/runtime/resource-limits.yaml
user_overrides:
  john_doe:
    max_gpu_slots_per_container: 1
    priority: 100               # Highest
    reservation_start: "2025-11-01T00:00:00"
    reservation_end: "2025-11-08T00:00:00"
    reserved_gpus: [0]          # Reserve full GPU 0
    reason: "Thesis deadline - needs dedicated GPU"
```

**Effect:**
- During reservation: GPU 0 only available to john_doe
- Others see: "✗ GPU Reserved for john_doe until 2025-11-08"
- After reservation ends: GPU 0 returns to the normal pool

---

## Implementation Steps

### **Step 1 (optional): Enable MIG**

MIG is **disabled** today and the system runs 4 full GPUs — no MIG setup is required. Enable
MIG only if you want to partition GPUs for higher user density:

```bash
# Enable MIG on the chosen A100s (requires reboot; schedule maintenance)
sudo nvidia-smi -i 0,1,2,3 -mig 1
sudo reboot

# Create MIG instances (example: 2g.20gb profile)
for gpu in 0 1 2 3; do
  sudo nvidia-smi mig -i $gpu -cgi 14,14,14 -C
done

# Verify
nvidia-smi mig -lgi
```

The allocator detects the new instances automatically and weights each slot by its compute
fraction. With MIG off, this step is skipped entirely.

### **Step 2: Set up /var directories**

```bash
cd /opt/ds01-infra
git pull
sudo ./scripts/system/setup-var-directories.sh
```

### **Step 3: Set up systemd slices**

```bash
sudo ./scripts/system/setup-resource-slices.sh

# Verify
systemctl status ds01.slice
```

### **Step 4: Initialize the GPU allocator**

```bash
sudo chmod +x scripts/docker/*.py

# Initialize (auto-detects full GPUs vs MIG instances)
python3 scripts/docker/gpu_allocator.py status
# With MIG off: shows 4 GPU-slots
```

### **Step 5: Test allocation**

```bash
# Allocate two slots to a student, then exceed the quota
python3 scripts/docker/gpu_allocator.py allocate alice test1 1 10
python3 scripts/docker/gpu_allocator.py allocate alice test2 1 10
python3 scripts/docker/gpu_allocator.py allocate alice test3 1 10
python3 scripts/docker/gpu_allocator.py allocate alice test4 1 10
# → Fourth rejected once the gpueq quota is reached

# Clean up
python3 scripts/docker/gpu_allocator.py release test1
python3 scripts/docker/gpu_allocator.py release test2
```

### **Step 6: Create user commands**

```bash
sudo ln -sf /opt/ds01-infra/scripts/monitoring/gpu-status-dashboard.py \
    /usr/local/bin/ds01-gpu-status

# Test
ds01-gpu-status
```

---

## How Priority-Aware Allocation Works

```
┌─────────────────────────────────────────────────────────────┐
│ USER: requests a GPU                                          │
└──────────────────┬──────────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ 1. Check user's current gpueq usage vs quota                 │
│ 2. Get user's priority                                       │
│ 3. Check for active reservations                             │
└──────────────────┬──────────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Find the least-allocated GPU-slot:                        │
│      slot 0 → 0 containers, max_priority=0                    │
│      slot 1 → 1 container  (researcher, high priority)        │
│      slot 2 → 1 container  (student, low priority)            │
│      slot 3 → 0 containers                                    │
│    Score = (priority_diff, container_count, memory_used)      │
│      empty slots win; avoid displacing higher-priority users  │
└──────────────────┬──────────────────────────────────────────┘
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Allocate the best slot                                    │
│    Launch: docker run --gpus "device=0" ...                  │
└─────────────────────────────────────────────────────────────┘
```

**Key insight:** users fill empty slots first, then share before displacing
higher-priority users.

---

## Resource Enforcement

| Resource | Enforcement | Tool | Scope |
|----------|-------------|------|-------|
| **CPU** | ✓ Hard limit | cgroups | Per container |
| **Memory** | ✓ Hard limit | cgroups | Per container |
| **GPU device** | ✓ GPU-slot (full GPU, or MIG instance if enabled) | Docker `--gpus` | Per container |
| **GPU quota** | ✓ Max gpueq per user | gpu_allocator.py | Per user |
| **GPU memory** | ✓ Per slot (40GB full GPU; partition size if MIG) | Hardware | Per slot |
| **Containers** | ✓ Max per user | wrapper check | Per user |
| **Priority** | ✓ Allocation order | gpu_allocator.py | Per user |
| **Reservations** | ✓ Time-based lock | gpu_allocator.py | Per GPU/slot |

---

## Full-GPU Mode (current) vs MIG Mode (optional)

| Aspect | Full-GPU mode (current) | MIG mode (optional) |
|--------|-------------------------|----------------------|
| **Slots per GPU** | 1 | up to 7 (profile-dependent) |
| **Users per GPU** | 1 | several |
| **Isolation** | Process-level | Hard memory isolation |
| **Memory per slot** | 40GB | partition size (e.g. 20GB) |
| **gpueq per slot** | 1.0 | compute_slices / 7 |

---

## Monitoring

### Real-time GPU-slot status

```bash
# DS01 dashboard
ds01-gpu-status

# Sample output:
# ======================================================================
# DS01 GPU SERVER STATUS
# ======================================================================
#
# Slot 0: 1 container
# Util: 85% | Mem: 36000/40960 MB
# - alice-training (alice, priority=low, 2h 15m)
#
# Slot 1: 0 containers — AVAILABLE
# ...

# NVIDIA status (mig list only returns instances if MIG is enabled)
nvidia-smi
nvidia-smi mig -lgi

# Cgroups
systemd-cgtop --depth=3
```

---

## Graceful Error Handling

**Configured in YAML:**

```yaml
wizard:
  error_messages:
    gpu_limit_exceeded: |
      ✗ GPU Limit Exceeded

      Your GPU quota is {max} GPU-equivalents and you currently use {current}.
      This request would exceed it.

      Options:
      1. Stop an existing container
      2. Launch as CPU-only
```

**Usage in wrapper:**
```bash
echo "$(get_error_message gpu_limit_exceeded max=2.0 current=2.0)"
```

---

## Troubleshooting

### GPU allocation not working

```bash
# Is MIG enabled? (no instances listed → full-GPU mode, which is expected today)
nvidia-smi mig -lgi

# Allocator state
python3 scripts/docker/gpu_allocator.py status
```

### Priority not respected

```bash
python3 scripts/docker/get_resource_limits.py alice --priority
tail /var/log/ds01/gpu-allocations.log | grep priority
```

### Reservation conflicts

```bash
grep -A10 user_overrides config/runtime/resource-limits.yaml
```

---

## Recent Updates (November 2025)

### Bug fixes & full-GPU / MIG compatibility

**Issue #1: False MIG instance detection**
- **Problem**: allocator assumed MIG instances per GPU when MIG mode was enabled, even with no partitions configured
- **Fix**: check `nvidia-smi mig -lgi` return code and output before adding instances
- **Result**: gracefully falls back to whole-GPU mode when no MIG partitions exist

**Issue #2: NoneType config handling**
- **Problem**: YAML with `user_overrides:` (no entries) caused a TypeError when checking reservations
- **Fix**: changed `config.get('user_overrides', {})` to `config.get('user_overrides') or {}`
- **Result**: handles empty/null config sections correctly

### Test results

**Hardware configuration:** 4× A100-40GB, MIG disabled (whole-GPU mode).

```
✓ Slot detection: correctly identified 4 full GPUs (not fake MIG instances)
✓ GPU allocation: successfully allocated a slot to a student
✓ Priority handling: admin received a different slot
✓ User limits: tracked gpueq usage per user correctly
✓ Release: slot released and usage decremented
```

**Compatibility:** the system works in both modes:
- **Without MIG partitions**: whole-GPU mode (slots `0`, `1`, `2`, `3`)
- **With MIG partitions**: tracks individual MIG instances (e.g. `1:0`, `1:1`)

### Test scripts

```bash
python3 /opt/ds01-infra/testing/unit/test_gpu_allocator_mig_detection.py
python3 /opt/ds01-infra/testing/functional/test_gpu_allocator_functional.py
```

---

## Next Steps

1. ✓ Set up /var directories
2. ✓ Create systemd slices
3. ✓ Initialize the GPU allocator
4. ✓ Test thoroughly — **complete (Nov 2025)**
5. ✓ Full-GPU / MIG compatibility — **complete (Nov 2025)**
6. Integrate the allocator into `mlc-create-wrapper.sh`
7. Set up storage quotas
8. Implement idle detection
