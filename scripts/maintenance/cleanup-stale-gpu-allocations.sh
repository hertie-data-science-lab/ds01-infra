#!/bin/bash
# Cleanup stale GPU allocations for stopped containers that exceeded hold timeout
# /opt/ds01-infra/scripts/maintenance/cleanup-stale-gpu-allocations.sh
#
# This script should be run periodically (e.g., via cron every hour)
# to release GPU allocations from stopped containers that have exceeded
# their gpu_hold_after_stop timeout.

set -e

# Configuration
# Resolve symlinks to get actual script location
SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
INFRA_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
GPU_ALLOCATOR="$INFRA_ROOT/scripts/docker/gpu_allocator_v2.py"
LOG_DIR="/var/log/ds01"
LOG_FILE="$LOG_DIR/gpu-stale-cleanup.log"

# Source libraries
INIT_LIB="$INFRA_ROOT/scripts/lib/init.sh"
if [ -f "$INIT_LIB" ]; then
    source "$INIT_LIB"
fi

EVENTS_LIB="$INFRA_ROOT/scripts/lib/ds01_events.sh"
if [ -f "$EVENTS_LIB" ]; then
    source "$EVENTS_LIB"
fi

# Ensure log directory exists
mkdir -p "$LOG_DIR"

# Logging function
log() {
    local timestamp=$(date '+%Y-%m-%d %H:%M:%S')
    echo "[$timestamp] $1" | tee -a "$LOG_FILE"
}

# ============================================================================
# GPU Health Verification (SLURM epilog pattern)
# ============================================================================

# Verify GPU health after allocation release
# Detects orphaned processes, kills them, and optionally resets GPU
verify_gpu_health() {
    local gpu_uuid="$1"

    if [ -z "$gpu_uuid" ]; then
        log "WARNING: verify_gpu_health called without GPU UUID"
        return 0
    fi

    log "Checking GPU health: $gpu_uuid"

    # Query orphaned processes on this GPU
    # Format: pid, process_name, used_memory
    local orphan_output
    orphan_output=$(nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv,noheader --id="$gpu_uuid" 2>/dev/null || true)

    if [ -z "$orphan_output" ]; then
        log "✓ GPU $gpu_uuid clean (no orphaned processes)"
        return 0
    fi

    # Orphaned processes detected
    log "WARNING: Orphaned processes detected on GPU $gpu_uuid:"
    echo "$orphan_output" | while IFS= read -r line; do
        log "  $line"
    done

    # Extract PIDs and kill them
    local killed_count=0
    while IFS=, read -r pid process_name used_memory; do
        # Trim whitespace
        pid=$(echo "$pid" | xargs)
        process_name=$(echo "$process_name" | xargs)

        if [ -n "$pid" ] && [ "$pid" != "pid" ]; then
            log "Killing orphaned process: PID=$pid, name=$process_name"
            if kill -9 "$pid" 2>/dev/null; then
                log "✓ Killed PID $pid"
                ((killed_count++))
            else
                log "WARNING: Failed to kill PID $pid (may have already exited)"
            fi
        fi
    done <<< "$orphan_output"

    # Check if GPU is shared (other containers using it)
    local shared_containers
    shared_containers=$(docker ps --filter "label=ds01.gpu.uuid=$gpu_uuid" --format "{{.Names}}" 2>/dev/null || true)

    if [ -n "$shared_containers" ]; then
        # GPU is shared - DO NOT reset
        log "ERROR: GPU $gpu_uuid is shared by other containers. Manual intervention required."
        log "Active containers: $shared_containers"

        # Log event for admin alerting
        if command -v log_event &>/dev/null; then
            log_event "gpu.health_check" "" "cleanup-stale-gpu" \
                gpu_uuid="$gpu_uuid" \
                status="orphaned_shared" \
                killed_processes="$killed_count" \
                active_containers="$shared_containers" || true
        fi

        return 1
    fi

    # GPU not shared - safe to reset
    log "Resetting GPU $gpu_uuid (no active containers)"
    if nvidia-smi -r -i "$gpu_uuid" 2>/dev/null; then
        log "✓ GPU $gpu_uuid reset successful"

        # Log successful cleanup
        if command -v log_event &>/dev/null; then
            log_event "gpu.health_check" "" "cleanup-stale-gpu" \
                gpu_uuid="$gpu_uuid" \
                status="cleaned" \
                killed_processes="$killed_count" \
                reset="true" || true
        fi
    else
        log "WARNING: GPU reset failed for $gpu_uuid (may require manual intervention)"

        # Log reset failure
        if command -v log_event &>/dev/null; then
            log_event "gpu.health_check" "" "cleanup-stale-gpu" \
                gpu_uuid="$gpu_uuid" \
                status="reset_failed" \
                killed_processes="$killed_count" || true
        fi

        return 1
    fi

    return 0
}

# Run health check on all GPUs (standalone mode)
verify_all_gpus() {
    log "Running health check on all GPUs..."

    # Get all GPU UUIDs
    local all_gpus
    all_gpus=$(nvidia-smi --query-gpu=uuid --format=csv,noheader 2>/dev/null || true)

    if [ -z "$all_gpus" ]; then
        log "WARNING: No GPUs found or nvidia-smi failed"
        return 0
    fi

    local checked=0
    local failed=0

    while IFS= read -r gpu_uuid; do
        # Trim whitespace
        gpu_uuid=$(echo "$gpu_uuid" | xargs)

        if [ -n "$gpu_uuid" ]; then
            if ! verify_gpu_health "$gpu_uuid"; then
                ((failed++))
            fi
            ((checked++))
        fi
    done <<< "$all_gpus"

    log "Health check complete: $checked GPUs checked, $failed issues"
    return 0
}

# Parse command line arguments
HEALTH_CHECK_ONLY=false
if [ "${1:-}" = "--health-check" ]; then
    HEALTH_CHECK_ONLY=true
fi

# Check if GPU allocator exists
if [ ! -f "$GPU_ALLOCATOR" ]; then
    log "ERROR: GPU allocator not found at $GPU_ALLOCATOR"
    exit 1
fi

# ============================================================================
# Main Execution
# ============================================================================

if [ "$HEALTH_CHECK_ONLY" = true ]; then
    # Standalone health check mode
    log "Running standalone GPU health check..."
    verify_all_gpus
    log "Health check completed"
    exit 0
fi

# Normal mode: release stale allocations + health check
log "Starting stale GPU allocation cleanup..."

# Release stale allocations
OUTPUT=$(python3 "$GPU_ALLOCATOR" release-stale 2>&1)
EXITCODE=$?

if [ $EXITCODE -eq 0 ]; then
    # Log the output
    echo "$OUTPUT" | while IFS= read -r line; do
        log "$line"
    done

    # Count releases from output
    RELEASE_COUNT=$(echo "$OUTPUT" | grep -E "Removed|Released" | wc -l)

    # Default to 0 if empty
    if [ -z "$RELEASE_COUNT" ]; then
        RELEASE_COUNT=0
    fi

    # Collect released GPU UUIDs for health verification
    declare -a released_gpu_uuids=()

    if [ "$RELEASE_COUNT" -gt 0 ]; then
        log "✓ Released $RELEASE_COUNT stale GPU allocation(s)"

        # Parse container details from output and log each one
        echo "$OUTPUT" | grep "✓ Removed" | while IFS= read -r line; do
            # Extract container name (format: "✓ Removed container_name: reason")
            container=$(echo "$line" | sed -n 's/^✓ Removed \([^:]*\):.*/\1/p')
            if [ -n "$container" ] && command -v log_event &>/dev/null; then
                # Try to get user from container metadata (via docker if still exists, or unknown)
                username=$(docker inspect "$container" --format '{{index .Config.Labels "ds01.user"}}' 2>/dev/null || echo "unknown")
                [ "$username" = "<no value>" ] && username="unknown"

                # Get GPU UUID from output if present
                gpu_uuid=$(echo "$line" | grep -oP 'GPU-[a-f0-9-]+|MIG-[a-f0-9-]+' || echo "unknown")

                log_event "gpu.release" "$username" "cleanup-stale-gpu" \
                    container="$container" \
                    gpu_uuid="$gpu_uuid" \
                    reason="hold_expired" || true
            fi
        done

        # Extract GPU UUIDs for health verification
        log "Extracting GPU UUIDs for health verification..."
        while IFS= read -r line; do
            gpu_uuid=$(echo "$line" | grep -oP 'GPU-[a-f0-9-]+|MIG-[a-f0-9-]+' || true)
            if [ -n "$gpu_uuid" ]; then
                released_gpu_uuids+=("$gpu_uuid")
            fi
        done < <(echo "$OUTPUT" | grep "✓ Removed")

        # Run health checks on released GPUs
        if [ ${#released_gpu_uuids[@]} -gt 0 ]; then
            log "Running post-removal health checks on ${#released_gpu_uuids[@]} GPU(s)..."
            for gpu_uuid in "${released_gpu_uuids[@]}"; do
                verify_gpu_health "$gpu_uuid" || true
            done
        else
            # Fallback: run health check on all GPUs if UUIDs not extractable
            log "Could not extract specific GPU UUIDs, running general health check..."
            verify_all_gpus
        fi
    else
        log "✓ No stale allocations found"
    fi
else
    log "ERROR: GPU allocator failed with exit code $EXITCODE"
    log "$OUTPUT"
    exit 1
fi

log "Cleanup completed successfully"
