# Phase 5: Lifecycle Bug Fixes - Research

**Researched:** 2026-02-11
**Domain:** Container lifecycle management, GPU resource cleanup, idle detection
**Confidence:** HIGH

## Summary

Phase 5 fixes container retirement, cleanup, and GPU release to work reliably across all container types (DS01-managed, devcontainers, compose, direct docker run, unmanaged). Research reveals proven patterns from SLURM/HPC (epilog cleanup scripts), DCGM GPU metrics infrastructure, and Docker lifecycle state management. The existing codebase already implements universal container monitoring via `check-idle-containers.sh` and `enforce-max-runtime.sh`, but lacks GPU utilization detection (relies on CPU only), has no created-state cleanup, and needs post-removal GPU health verification.

Key findings:
1. **GPU idle detection**: DCGM exporter already deployed exposes `DCGM_FI_DEV_GPU_UTIL` metric, nvidia-smi provides per-GPU utilization via `--query-gpu=utilization.gpu`, standard HPC threshold is <5-10% over rolling window
2. **SLURM epilog pattern**: Check for orphaned processes post-removal, kill if found, reset GPU if safe and not shared
3. **Docker created state**: Containers stuck in "created" (never started) detected via `docker ps -a --filter "status=created"`, cleanup via `docker rm` after timeout
4. **Wall notifications**: Linux `wall` command broadcasts to all terminal sessions, requires root, skipped by GUI-only users

The existing cleanup pipeline (hourly cron: idle check :30, runtime enforce :45, GPU cleanup :15, container removal :00) provides the foundation. GPU utilization monitoring is the missing piece.

**Primary recommendation:** Add GPU utilization sampling to idle detection using DCGM metrics or nvidia-smi, implement post-removal GPU health checks with orphaned process cleanup, add created-state container detection to cleanup pipeline, and switch from file-based warnings to `wall` messages.

## Standard Stack

### Core Tools (Already Deployed)

| Tool | Version | Purpose | Already Present |
|------|---------|---------|-----------------|
| Docker API | Client 27.3.1 | Container state inspection, lifecycle control | ✓ Yes |
| nvidia-smi | NVIDIA Driver | GPU utilization queries, process detection, GPU reset | ✓ Yes |
| DCGM Exporter | Latest | GPU metrics via Prometheus (DCGM_FI_DEV_GPU_UTIL) | ✓ Yes (deployed) |
| systemd | System | Cron job scheduling, cgroup enforcement | ✓ Yes |
| bash/python3 | System | Scripting lifecycle enforcement | ✓ Yes |

### Supporting Tools

| Tool | Version | Purpose | When to Use |
|------|---------|---------|-------------|
| `wall` | coreutils | Broadcast terminal messages to logged-in users | Warning notifications |
| `bc` | 1.07+ | Floating point arithmetic for thresholds | GPU util % comparisons |
| `jq` | 1.6+ | JSON parsing for Docker inspect output | Container metadata extraction |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| nvidia-smi polling | DCGM Prometheus query | DCGM adds dependency on Prometheus stack, nvidia-smi is simpler for cron scripts |
| `wall` notifications | File in $HOME or container | Files require cleanup and polling, `wall` is instant but requires active terminal |
| Cron-based cleanup | systemd timers | Timers are more flexible but cron is simpler and already deployed |

**Installation:**
Already deployed. No additional packages needed. DCGM exporter runs at port 9400.

## Architecture Patterns

### Recommended Cleanup Pipeline Structure

```
Cron Schedule (hourly):
├── :15 — GPU health check + cleanup stale allocations
│   ├── Release GPUs after gpu_hold_after_stop
│   └── Check for orphaned processes (NEW)
│       └── nvidia-smi --query-compute-apps=pid,gpu_uuid
├── :30 — Idle detection + created-state cleanup (NEW)
│   ├── GPU utilization check (NEW: nvidia-smi or DCGM)
│   ├── CPU/network/process checks (existing)
│   ├── Stop idle containers
│   └── Clean created-never-started containers (NEW)
├── :45 — Max runtime enforcement
│   └── Stop containers exceeding max_runtime
└── :00 — Container removal
    ├── Remove stopped containers after container_hold_after_stop
    └── Post-removal GPU health verification (NEW)
```

### Pattern 1: GPU Utilization Sampling (Multi-Signal Idle Detection)

**What:** Combine GPU, CPU, network, and process activity to determine if a container is idle
**When to use:** When container has GPU access (core principle: GPU access = ephemeral enforcement)

**Example (nvidia-smi approach):**
```bash
# Get GPU UUID for container (from docker labels or DeviceRequests)
gpu_uuid=$(docker inspect "$container" --format '{{index .Config.Labels "ds01.gpu.uuid"}}')

# Query GPU utilization for that specific GPU
gpu_util=$(nvidia-smi --query-gpu=utilization.gpu --format=csv,noheader,nounits --id="$gpu_uuid")

# Check if GPU is idle (<5% threshold)
if (( $(echo "$gpu_util < 5" | bc -l) )); then
    # GPU idle, check secondary signals (CPU, network)
    cpu_util=$(docker stats "$container" --no-stream --format "{{.CPUPerc}}" | sed 's/%//')
    if (( $(echo "$cpu_util < 1.0" | bc -l) )); then
        # Both GPU and CPU idle → container is idle
        echo "idle"
    else
        # CPU active (data loading/preprocessing) → not idle
        echo "active"
    fi
else
    echo "active"
fi
```

**30-minute grace period:**
```bash
# Check container start time
start_time=$(docker inspect "$container" --format '{{.State.StartedAt}}')
start_epoch=$(date -d "$start_time" +%s)
now=$(date +%s)
age_seconds=$((now - start_epoch))

# Skip idle detection if younger than 30 minutes
if [ "$age_seconds" -lt 1800 ]; then
    echo "grace_period"
    return
fi
```

### Pattern 2: SLURM Epilog-Style GPU Health Check

**What:** Post-removal verification that GPU is clean (no orphaned processes)
**When to use:** After container removal, if container had GPU allocation

**Example:**
```bash
#!/bin/bash
# Post-removal GPU health check (SLURM epilog pattern)
# Source: NVIDIA DeepOps, SLURM prolog_epilog.html

check_gpu_health_after_removal() {
    local gpu_uuid="$1"
    local container_name="$2"

    # Check for orphaned processes on this GPU
    orphaned=$(nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader --id="$gpu_uuid" 2>/dev/null)

    if [ -n "$orphaned" ]; then
        log "WARNING: Orphaned processes detected on GPU $gpu_uuid after $container_name removal"
        log "$orphaned"

        # Extract PIDs and kill
        echo "$orphaned" | awk -F',' '{print $1}' | while read pid; do
            if [ -n "$pid" ] && [ "$pid" != "0" ]; then
                log "Killing orphaned process: $pid"
                kill -9 "$pid" 2>/dev/null || true
            fi
        done

        # Check if GPU is exclusively used by this container (not MIG shared)
        other_containers=$(docker ps --filter "label=ds01.gpu.uuid=$gpu_uuid" --format "{{.Names}}")
        if [ -z "$other_containers" ]; then
            # No other containers using this GPU, safe to reset
            log "Resetting GPU $gpu_uuid (no other containers)"
            nvidia-smi -r -i "$gpu_uuid" 2>/dev/null || log "GPU reset failed (may require reboot)"
        else
            # GPU is shared (MIG), don't reset - alert admin
            log "ERROR: GPU $gpu_uuid has orphaned processes but is shared (MIG). Manual intervention required."
            # Could send admin alert here
        fi
    fi
}
```

### Pattern 3: Created-State Container Cleanup

**What:** Detect and remove containers that were created but never started
**When to use:** Periodic cleanup (e.g., in idle detection cron, not separate job)

**Example:**
```bash
#!/bin/bash
# Clean up containers stuck in "created" state

CREATED_TIMEOUT_MINUTES=30

# Find containers in "created" state
created_containers=$(docker ps -a --filter "status=created" --format "{{.Names}}\t{{.CreatedAt}}")

if [ -z "$created_containers" ]; then
    log "No containers in created state"
    return
fi

while IFS=$'\t' read -r container_name created_at; do
    # Parse creation time
    created_epoch=$(date -d "$created_at" +%s 2>/dev/null)
    now=$(date +%s)
    age_minutes=$(( (now - created_epoch) / 60 ))

    if [ "$age_minutes" -gt "$CREATED_TIMEOUT_MINUTES" ]; then
        log "Removing created-never-started container: $container_name (age: ${age_minutes}m)"

        # Get owner for logging
        owner=$(docker inspect "$container_name" --format '{{index .Config.Labels "ds01.user"}}' 2>/dev/null || echo "unknown")

        # Check if GPU was allocated
        gpu_allocated=$(docker inspect "$container_name" --format '{{.HostConfig.DeviceRequests}}' 2>/dev/null | grep -qi "nvidia" && echo "yes" || echo "no")

        # Remove container
        if docker rm -f "$container_name" &>/dev/null; then
            log "✓ Removed created-state container: $container_name (owner: $owner, gpu: $gpu_allocated)"

            # If GPU was allocated, release it
            if [ "$gpu_allocated" = "yes" ]; then
                python3 "$INFRA_ROOT/scripts/docker/gpu_allocator_v2.py" release "$owner" "$container_name" || true
            fi
        else
            log "ERROR: Failed to remove created-state container: $container_name"
        fi
    fi
done <<< "$created_containers"
```

### Pattern 4: Wall-Based Notifications

**What:** Broadcast warnings to user's active terminal sessions
**When to use:** Idle warnings, runtime warnings (replaces file-based notifications)

**Example:**
```bash
send_wall_warning() {
    local username="$1"
    local container="$2"
    local minutes_until_stop="$3"
    local warning_type="$4"  # "idle" or "runtime"

    # Get user's terminal sessions (pts devices)
    user_ttys=$(who | grep "^$username " | awk '{print $2}')

    if [ -z "$user_ttys" ]; then
        log "No active terminals for $username, skipping wall notification"
        return
    fi

    # Create message
    local message="
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  DS01 GPU CONTAINER WARNING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Container: $container
Status: Will auto-stop in ~${minutes_until_stop} minutes
Reason: ${warning_type} timeout approaching

Your work in /workspace is safe and will persist.

To keep running:
  • Resume activity in the container, OR
  • touch /workspace/.keep-alive (24h max)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
"

    # Send wall message to specific user's terminals only
    # Note: wall requires root, which cron jobs have
    echo "$message" | wall -n -t "$username"

    log "Wall warning sent to $username (terminals: $(echo $user_ttys | tr '\n' ' '))"
}
```

### Anti-Patterns to Avoid

- **File-based notifications in $HOME**: Require cleanup, ignored if user doesn't check, pollute home directory
- **Per-container idle detection without grace period**: Triggers false positives during model loading, dataset download, package installation
- **Fixed thresholds without secondary signals**: GPU idle but CPU active = data preprocessing, don't stop
- **GPU reset without checking shared usage**: MIG-partitioned GPUs serve multiple containers, reset breaks all
- **Synchronous GPU health checks during container removal**: Slows down user operations, do health checks in background cron job

## Don't Hand-Roll

Problems that look simple but have existing solutions:

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| GPU metrics collection | Custom nvidia-smi polling daemon | DCGM Exporter (already deployed) | DCGM handles metric buffering, Prometheus integration, standardised schema |
| Rolling window averages | In-memory arrays + manual averaging | Simple last-N-samples with state file | Complexity not justified for hourly cron, state file survives restarts |
| Terminal broadcasting | Loop over `who` + `write` to each tty | `wall` command | wall handles multi-terminal, broadcast atomicity, proper permissions |
| Docker state queries | Parse `docker ps` text output | `docker inspect` JSON + jq/python | JSON is stable API, text parsing breaks on format changes |
| Container ownership attribution | Custom heuristics everywhere | Centralized `get_container_owner()` function (already exists) | Fallback chain already implemented: ds01.user → aime.mlc.USER → devcontainer.local_folder → name pattern |

**Key insight:** DS01 already has ownership attribution (`get_container_owner()` in check-idle-containers.sh), container type detection (`get_container_type()`), and cleanup cron schedule. The missing pieces are GPU utilization sampling and post-removal health checks, not the overall architecture.

## Common Pitfalls

### Pitfall 1: Dev Containers Treated Like Batch Jobs

**What goes wrong:** Applying aggressive idle timeouts to dev containers destroys interactive development workflow
**Why it happens:** Dev containers have bursty usage (code, test, think, code) but appear "idle" during thinking phase
**How to avoid:** Exempt dev containers from idle timeout (only enforce max_runtime)
**Warning signs:** Users complaining that VS Code dev containers get killed while they're actively coding

**Phase 5 decision:** Dev containers exempt from idle_timeout, only subject to max_runtime (168h = 1 week)

### Pitfall 2: Created-State Containers with GPU Allocations Leak Resources

**What goes wrong:** `docker create` allocates GPU via wrapper, but container never starts → GPU allocation never released
**Why it happens:** Cleanup scripts only check "exited" state, not "created" state
**How to avoid:** Add created-state detection to cleanup, release GPU allocations before container removal
**Warning signs:** `gpu_allocator.py status` shows allocations for non-existent containers

**Detection:**
```bash
# Check if GPU allocator shows allocations but containers don't exist
python3 gpu_allocator_v2.py status --json | jq -r '.allocations[].container' | while read container; do
    if ! docker inspect "$container" &>/dev/null; then
        echo "LEAKED: $container (allocation exists but container gone)"
    fi
done
```

### Pitfall 3: Grace Period Not Per-Container-Start

**What goes wrong:** Grace period tracked globally or never reset → container can restart and immediately get idle-killed
**Why it happens:** State file tracks "LAST_ACTIVITY" but doesn't reset on container restart
**How to avoid:** Check container StartedAt timestamp directly, not state file age
**Warning signs:** Users report container killed immediately after restart

**Correct implementation:**
```bash
# Always check container start time from Docker API
start_time=$(docker inspect "$container" --format '{{.State.StartedAt}}')
start_epoch=$(date -d "$start_time" +%s)
age_since_start=$(($(date +%s) - start_epoch))

# Grace period is always relative to StartedAt
if [ "$age_since_start" -lt 1800 ]; then  # 30 minutes
    return  # Still in grace period
fi
```

### Pitfall 4: GPU Reset Breaks MIG Partitions

**What goes wrong:** `nvidia-smi -r` resets entire GPU, breaking all MIG instances on that GPU
**Why it happens:** MIG instances share physical GPU, reset destroys partition configuration
**How to avoid:** Only reset GPU if no other containers are using it (check docker ps for matching GPU labels)
**Warning signs:** Multiple containers suddenly lose GPU access after one container cleanup

**Safe reset logic:**
```bash
# Check if GPU is shared before resetting
other_containers=$(docker ps --filter "label=ds01.gpu.uuid=$gpu_uuid" --format "{{.Names}}")
if [ -z "$other_containers" ]; then
    nvidia-smi -r -i "$gpu_uuid"  # Safe: no other containers
else
    # Shared GPU (MIG), alert admin instead of resetting
    log "ERROR: GPU $gpu_uuid needs reset but is shared by: $other_containers"
fi
```

### Pitfall 5: Wall Messages Not Reaching Users

**What goes wrong:** Users never see wall notifications
**Why it happens:** User is in GUI-only session (no terminal), or SSH session without active shell
**How to avoid:** Accept that wall is best-effort; users working in GUI won't see messages (design constraint)
**Warning signs:** Users claim they never received warnings before container stopped

**Mitigation:**
- Document wall limitation in user guide
- Log all warnings to event system (events.jsonl) for audit trail
- Consider Phase 8 (email/Slack notifications) for reliability

## Code Examples

Verified patterns from official sources and existing DS01 codebase:

### GPU Utilization Check (nvidia-smi)

```bash
#!/bin/bash
# Check if GPU is idle for a specific container
# Combines GPU util + CPU util for accurate idle detection

check_gpu_idle() {
    local container="$1"
    local gpu_uuid="$2"
    local gpu_threshold="${3:-5}"  # Default 5%

    # Query GPU utilization for this specific GPU
    local gpu_util=$(nvidia-smi --query-gpu=utilization.gpu \
        --format=csv,noheader,nounits \
        --id="$gpu_uuid" 2>/dev/null || echo "0")

    # Check if GPU is below threshold
    if (( $(echo "$gpu_util < $gpu_threshold" | bc -l) )); then
        # GPU idle, check CPU as secondary signal
        local cpu_util=$(docker stats "$container" --no-stream \
            --format "{{.CPUPerc}}" 2>/dev/null | sed 's/%//')

        if (( $(echo "$cpu_util < 1.0" | bc -l) )); then
            # Both GPU and CPU idle
            echo "idle"
            return 0
        else
            # CPU active (data loading, preprocessing)
            echo "active_cpu"
            return 1
        fi
    else
        # GPU active
        echo "active_gpu"
        return 1
    fi
}
```

**Source:** [nvidia-smi manual](https://docs.nvidia.com/deploy/nvidia-smi/), HPC idle detection thresholds <5-10% from [GPU Utilization Monitoring 2026](https://dasroot.net/posts/2026/02/gpu-utilization-monitoring-tools-metrics-2026/)

### Post-Removal GPU Health Check

```bash
#!/bin/bash
# SLURM epilog-style GPU cleanup after container removal
# Checks for orphaned processes, kills them, resets GPU if safe

cleanup_gpu_after_container() {
    local gpu_uuid="$1"
    local container_name="$2"

    # Check for orphaned GPU processes
    local orphaned=$(nvidia-smi --query-compute-apps=pid,process_name \
        --format=csv,noheader --id="$gpu_uuid" 2>/dev/null)

    if [ -z "$orphaned" ]; then
        log "GPU $gpu_uuid clean after $container_name removal"
        return 0
    fi

    log "WARNING: Orphaned processes on GPU $gpu_uuid: $orphaned"

    # Kill orphaned processes
    echo "$orphaned" | awk -F',' '{print $1}' | while read pid; do
        [ -n "$pid" ] && kill -9 "$pid" 2>/dev/null
    done

    # Check if GPU is exclusively used by removed container
    local other_containers=$(docker ps \
        --filter "label=ds01.gpu.uuid=$gpu_uuid" \
        --format "{{.Names}}")

    if [ -z "$other_containers" ]; then
        # Safe to reset (no other containers on this GPU)
        log "Resetting GPU $gpu_uuid (exclusive use, now clean)"
        nvidia-smi -r -i "$gpu_uuid" 2>/dev/null || \
            log "ERROR: GPU reset failed, may require manual intervention"
    else
        # GPU shared (MIG), alert admin
        log "ERROR: GPU $gpu_uuid has orphaned processes but shared by: $other_containers"
        log "ACTION REQUIRED: Manual cleanup needed"
        # Could trigger admin alert here
    fi
}
```

**Source:** [SLURM Prolog/Epilog Guide](https://slurm.schedmd.com/prolog_epilog.html), [NVIDIA DeepOps epilog script](https://github.com/NVIDIA/deepops/blob/master/docs/slurm-cluster/slurm-prolog-epilog/README.md)

### Created-State Container Detection

```bash
#!/bin/bash
# Detect and clean containers stuck in "created" state (never started)

cleanup_created_containers() {
    local timeout_minutes="${1:-30}"

    # Find containers in created state (never started)
    local created=$(docker ps -a --filter "status=created" \
        --format "{{.Names}}\t{{.CreatedAt}}")

    [ -z "$created" ] && return 0

    local now=$(date +%s)
    local removed=0

    while IFS=$'\t' read -r container created_at; do
        local created_epoch=$(date -d "$created_at" +%s 2>/dev/null)
        local age_minutes=$(( (now - created_epoch) / 60 ))

        if [ "$age_minutes" -gt "$timeout_minutes" ]; then
            log "Removing created-never-started: $container (age: ${age_minutes}m)"

            # Get owner and GPU status before removal
            local owner=$(docker inspect "$container" \
                --format '{{index .Config.Labels "ds01.user"}}' 2>/dev/null || echo "unknown")
            local has_gpu=$(docker inspect "$container" \
                --format '{{.HostConfig.DeviceRequests}}' | grep -qi "nvidia" && echo "yes" || echo "no")

            # Remove container
            if docker rm -f "$container" &>/dev/null; then
                ((removed++))

                # Release GPU allocation if present
                if [ "$has_gpu" = "yes" ] && [ "$owner" != "unknown" ]; then
                    python3 "$INFRA_ROOT/scripts/docker/gpu_allocator_v2.py" \
                        release "$owner" "$container" 2>/dev/null || true
                fi

                # Log event
                log_event "container.cleanup" "$owner" "cleanup-created-state" \
                    container="$container" \
                    reason="created_never_started" \
                    age_minutes="$age_minutes" || true
            fi
        fi
    done <<< "$created"

    log "Cleaned $removed created-state container(s)"
}
```

**Source:** [Docker Container Lifecycle](https://last9.io/blog/docker-container-lifecycle/), [Docker container states](https://www.baeldung.com/ops/docker-container-states)

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| CPU-only idle detection | Multi-signal (GPU + CPU + network) | 2024-2025 HPC | Prevents false positives during data loading |
| Fixed thresholds | Rolling windows with configurable periods | K8s CNCF 2025 | Adapts to workload variance |
| Manual GPU cleanup | SLURM epilog pattern (automated post-job) | HPC standard | Prevents GPU leaks |
| File-based notifications | Terminal-based (`wall`, k8s events) | Cloud-native shift | Real-time delivery, no cleanup needed |
| Separate cleanup jobs | Unified lifecycle pipeline (detect → enforce → cleanup) | Kubernetes pattern | Reduces race conditions |

**Deprecated/outdated:**
- **CPU-only idle detection**: GPU workloads can have 0% CPU but 100% GPU (pure compute), misleading
- **Per-container state files for activity tracking**: Docker API provides StartedAt, FinishedAt natively
- **Fixed 10-second SIGTERM timeout**: GPU workloads need 60s for checkpoint saves (NVIDIA recommendation)

**Emerging (not for Phase 5):**
- **CRIU checkpoint/restore for GPU containers**: Kubernetes GPU working group developing this (Jan 2026), still experimental
- **eBPF-based process tracking**: Fine-grained container activity monitoring, overkill for hourly cron

## Open Questions

Things that couldn't be fully resolved:

1. **DCGM vs nvidia-smi for GPU utilization sampling**
   - What we know: DCGM exporter deployed and running at port 9400, exposes `DCGM_FI_DEV_GPU_UTIL` metric
   - What's unclear: Whether cron scripts should query Prometheus (HTTP) or use nvidia-smi (CLI)
   - Recommendation: Use nvidia-smi in cron scripts (simpler, no Prometheus dependency), keep DCGM for Grafana dashboards

2. **Sampling frequency for GPU utilization rolling window**
   - What we know: Hourly cron job checks all containers, 30-minute grace period after start
   - What's unclear: Should we sample GPU util once per cron run, or multiple times with averaging?
   - Recommendation: Single sample per cron run (hourly) with <5% threshold is sufficient given 30min grace period

3. **Keep-alive file 24-hour limit enforcement**
   - What we know: User can create `/workspace/.keep-alive` to prevent idle stop
   - What's unclear: How to track when .keep-alive was created (file mtime? state file?)
   - Recommendation: Check file mtime, if >24 hours old, ignore it and proceed with idle check

4. **Orphaned process detection reliability**
   - What we know: `nvidia-smi --query-compute-apps` lists GPU processes
   - What's unclear: Can orphaned processes hide from nvidia-smi (zombie processes, crashed driver state)?
   - Recommendation: Best-effort detection with logging; accept that some edge cases may require manual intervention

5. **MIG instance cleanup safety**
   - What we know: `nvidia-smi -r` resets entire GPU, MIG instances share physical GPU
   - What's unclear: Is there a way to reset individual MIG instance without affecting others?
   - Recommendation: No per-MIG-instance reset in NVIDIA driver. Only reset if no other containers using that physical GPU, otherwise alert admin.

## Sources

### Primary (HIGH confidence)

- [NVIDIA nvidia-smi Manual](https://docs.nvidia.com/deploy/nvidia-smi/) - GPU utilization queries, process detection, GPU reset
- [SLURM Prolog and Epilog Guide](https://slurm.schedmd.com/prolog_epilog.html) - HPC job cleanup patterns, epilog script structure
- [NVIDIA DeepOps SLURM epilog scripts](https://github.com/NVIDIA/deepops/blob/master/docs/slurm-cluster/slurm-prolog-epilog/README.md) - Production GPU cleanup implementation
- [Docker Container Lifecycle (Last9)](https://last9.io/blog/docker-container-lifecycle/) - Container state transitions, created/exited/running
- [Docker container states (Baeldung)](https://www.baeldung.com/ops/docker-container-states) - Complete state machine documentation
- [DCGM Exporter Documentation (NVIDIA)](https://docs.nvidia.com/datacenter/dcgm/latest/gpu-telemetry/dcgm-exporter.html) - Prometheus GPU metrics, DCGM_FI_DEV_GPU_UTIL

### Secondary (MEDIUM confidence)

- [Linux wall command manual](https://man7.org/linux/man-pages/man1/wall.1.html) - Terminal broadcast functionality
- [GPU Utilization Monitoring Tools 2026](https://dasroot.net/posts/2026/02/gpu-utilization-monitoring-tools-metrics-2026/) - Industry thresholds (<5-10%)
- [Making GPU Clusters More Efficient (NVIDIA Blog)](https://developer.nvidia.com/blog/making-gpu-clusters-more-efficient-with-nvidia-data-center-monitoring/) - Idle GPU waste reduction patterns

### Existing DS01 Codebase (HIGH confidence)

- `scripts/monitoring/check-idle-containers.sh` - Existing idle detection (CPU-only), container type detection, ownership attribution
- `scripts/maintenance/enforce-max-runtime.sh` - Max runtime enforcement, container type classification
- `scripts/maintenance/cleanup-stale-gpu-allocations.sh` - GPU release after timeout (no health check)
- `scripts/maintenance/cleanup-stale-containers.sh` - Container removal after timeout (no created-state handling)
- `scripts/docker/gpu_allocator_v2.py` - GPU allocation state management, Docker label-based truth
- `config/runtime/resource-limits.yaml` - Container type-specific timeouts (devcontainer, compose, docker, unknown)

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - All tools already deployed, no new dependencies
- Architecture: HIGH - SLURM epilog pattern is industry standard, existing cleanup pipeline proven
- Pitfalls: HIGH - Derived from DS01 audit findings (Phase 3.2) and HPC production experience
- GPU utilization sampling: MEDIUM - Implementation choice (DCGM vs nvidia-smi) needs validation
- MIG cleanup safety: MEDIUM - Driver limitations documented but edge cases exist

**Research date:** 2026-02-11
**Valid until:** 60 days (stable HPC patterns, GPU driver APIs mature)

**Key assumptions:**
- DCGM exporter remains deployed and functional at port 9400
- Cron schedule remains hourly (can adjust if needed)
- 30-minute grace period sufficient for model loading, dataset download, package installation
- Users working in GUI-only sessions accept wall message limitation (Phase 8 addresses with email)
- MIG dynamic partitioning means scripts cannot assume fixed MIG profile
