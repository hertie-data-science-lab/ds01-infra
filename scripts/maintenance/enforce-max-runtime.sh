#!/bin/bash
# /opt/ds01-infra/scripts/maintenance/enforce-max-runtime.sh
# Enforce max_runtime limits for containers
#
# This script checks running containers against their max_runtime limits
# and stops containers that have exceeded their maximum walltime.

set -e

# Configuration
# Resolve symlinks to get actual script location
SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
INFRA_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
CONFIG_FILE="$INFRA_ROOT/config/resource-limits.yaml"
STATE_DIR="/var/lib/ds01/container-runtime"
LOG_FILE="/var/log/ds01/runtime-enforcement.log"

# Source shared library for colors and utilities
source "$INFRA_ROOT/scripts/lib/init.sh"

# Create state and log directories
mkdir -p "$STATE_DIR"
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_color() {
    echo -e "${2}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

# Get max runtime for user (in hours)
get_max_runtime() {
    local username="$1"
    # Use centralized get_resource_limits.py CLI instead of embedded heredoc
    python3 "$INFRA_ROOT/scripts/docker/get_resource_limits.py" "$username" --max-runtime
}

# Check if container has GPU access
container_has_gpu() {
    local container="$1"
    # Check DeviceRequests for nvidia GPU
    local gpu_info=$(docker inspect "$container" --format '{{.HostConfig.DeviceRequests}}' 2>/dev/null)
    if echo "$gpu_info" | grep -qi "nvidia\|gpu"; then
        return 0
    fi
    return 1
}

# Get container type from label
get_container_type() {
    local container="$1"
    local type=$(docker inspect "$container" --format '{{index .Config.Labels "ds01.container_type"}}' 2>/dev/null)
    if [ -n "$type" ] && [ "$type" != "<no value>" ]; then
        echo "$type"
    else
        # Fallback: detect from labels/name
        local labels=$(docker inspect "$container" --format '{{json .Config.Labels}}' 2>/dev/null)
        local name=$(docker inspect "$container" --format '{{.Name}}' 2>/dev/null | tr -d '/')

        if echo "$labels" | grep -q "ds01.interface"; then
            docker inspect "$container" --format '{{index .Config.Labels "ds01.interface"}}' 2>/dev/null
        elif echo "$name" | grep -q '\._\.'; then
            echo "atomic"
        elif echo "$labels" | grep -q "devcontainer"; then
            echo "devcontainer"
        elif echo "$labels" | grep -q "com.docker.compose"; then
            echo "compose"
        else
            echo "docker"
        fi
    fi
}

# Get max runtime for container type (external containers)
get_container_type_max_runtime() {
    local container_type="$1"

    # Read from config - container_types section
    local runtime=$(python3 << PYEOF
import yaml
import sys

try:
    with open("$CONFIG_FILE") as f:
        config = yaml.safe_load(f)

    container_types = config.get('container_types', {})
    type_config = container_types.get('$container_type', {})
    runtime = type_config.get('max_runtime', '48h')

    print(runtime if runtime else '48h')
except Exception:
    print('48h')
PYEOF
)
    echo "$runtime"
}

# Get owner from container (for non-AIME containers)
get_container_owner() {
    local container="$1"

    # Try ds01.user label first
    local owner=$(docker inspect "$container" --format '{{index .Config.Labels "ds01.user"}}' 2>/dev/null)
    if [ -n "$owner" ] && [ "$owner" != "<no value>" ]; then
        echo "$owner"
        return
    fi

    # Try aime.mlc.USER label
    owner=$(docker inspect "$container" --format '{{index .Config.Labels "aime.mlc.USER"}}' 2>/dev/null)
    if [ -n "$owner" ] && [ "$owner" != "<no value>" ]; then
        echo "$owner"
        return
    fi

    # Try devcontainer.local_folder path
    local folder=$(docker inspect "$container" --format '{{index .Config.Labels "devcontainer.local_folder"}}' 2>/dev/null)
    if [[ "$folder" == /home/* ]]; then
        echo "$folder" | cut -d'/' -f3
        return
    fi

    # Fallback: extract from name._.uid pattern
    local name=$(docker inspect "$container" --format '{{.Name}}' 2>/dev/null | tr -d '/')
    if [[ "$name" == *._\.* ]]; then
        local uid=$(echo "$name" | rev | cut -d'.' -f1 | rev)
        getent passwd "$uid" 2>/dev/null | cut -d: -f1
        return
    fi

    echo ""
}

# Convert runtime string (e.g., "48h", "7d") to seconds
# Uses centralized ds01_parse_duration from init.sh
runtime_to_seconds() {
    local runtime="$1"
    local result=$(ds01_parse_duration "$runtime")
    # ds01_parse_duration returns -1 for null/never, convert to 0 for "no limit"
    if [ "$result" = "-1" ]; then
        echo "0"
    else
        echo "$result"
    fi
}

# Get container start time in epoch seconds
get_container_start_time() {
    local container="$1"

    local start_time=$(docker inspect "$container" --format='{{.State.StartedAt}}' 2>/dev/null)
    if [ -z "$start_time" ]; then
        echo "0"
        return
    fi

    date -d "$start_time" +%s 2>/dev/null || echo "0"
}

# Send warning to user
send_warning() {
    local username="$1"
    local container="$2"
    local hours_until_stop="$3"

    # Create warning message in user's home
    local user_home=$(eval echo "~$username")
    local warning_file="$user_home/.ds01-runtime-warning"

    cat > "$warning_file" << WARNEOF
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  MAX RUNTIME WARNING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Container: $container
Status: Approaching maximum runtime limit
Action: Will auto-stop in ~${hours_until_stop} hours

This container will be automatically stopped when it reaches
its maximum runtime limit. Your work in /workspace is safe
and will persist.

To save your work:
  1. Checkpoint your training/model state
  2. Ensure results are saved to /workspace
  3. Consider stopping and restarting if needed

To stop now and restart later:
  container-stop $container
  container-run $container

Questions? Check: ds01-status

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WARNEOF

    chown "$username:$username" "$warning_file" 2>/dev/null || true

    # Also send message to container if running
    if docker exec "$container" test -d /workspace 2>/dev/null; then
        docker exec "$container" bash -c "cat > /workspace/.runtime-warning.txt" < "$warning_file" 2>/dev/null || true
    fi

    log_color "Runtime warning sent to $username about container $container" "$YELLOW"
}

# Stop container that exceeded runtime
stop_runtime_exceeded() {
    local username="$1"
    local container="$2"
    local runtime_hours="$3"

    log_color "Stopping container: $container (user: $username, runtime: ${runtime_hours}h)" "$YELLOW"

    # Extract container name (remove ._.uid suffix)
    local container_name=$(echo "$container" | cut -d'.' -f1)

    # Create notification
    local user_home=$(eval echo "~$username")
    local notification_file="$user_home/.ds01-runtime-exceeded"

    cat > "$notification_file" << NOTIFEOF
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  CONTAINER STOPPED - MAX RUNTIME EXCEEDED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Container: $container_name
Stopped: $(date)
Reason: Maximum runtime limit reached (${runtime_hours}h)

Your work in /workspace is safe and persists.

To restart your container:
  container-run $container_name

Note: The container will be subject to the same runtime
limit after restart. If you need more time, please contact
the administrator.

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOTIFEOF

    chown "$username:$username" "$notification_file" 2>/dev/null || true

    # Stop container directly (designed for automation efficiency)
    # Note: Container is stopped but NOT removed - will be removed by cleanup-stale-containers
    # after container_hold_after_stop timeout. GPU will be freed after gpu_hold_after_stop timeout.

    # Stop container (10 second grace period)
    if docker stop -t 10 "$container" &>/dev/null; then
        log_color "Stopped container: $container (max runtime exceeded: ${runtime_hours}h)" "$GREEN"
        logger -t ds01-maxruntime "Stopped container: $container (user: $username, runtime: ${runtime_hours}h)"

        # Container is now stopped:
        # - GPU will be freed by cleanup-stale-gpu-allocations after gpu_hold_after_stop timeout
        # - Container will be removed by cleanup-stale-containers after container_hold_after_stop timeout
    else
        log_color "Failed to stop container: $container" "$RED"
        return 1
    fi

    # Clean up runtime state file
    rm -f "$STATE_DIR/${container}.state"
}

# Main monitoring function
monitor_containers() {
    log_color "Starting max runtime enforcement (universal)" "$BLUE"

    # Get ALL running containers (universal container management)
    local containers=$(docker ps --format "{{.Names}}")

    if [ -z "$containers" ]; then
        log "No containers running"
        return
    fi

    local monitored_count=0
    local stopped_count=0
    local warned_count=0
    local skipped_no_gpu=0

    for container in $containers; do
        # Verify container still exists (race condition protection)
        if ! docker ps --format "{{.Names}}" | grep -q "^${container}$"; then
            log "Container $container no longer exists, skipping"
            continue
        fi

        # Core principle: GPU access = ephemeral enforcement, No GPU = permanent OK
        if ! container_has_gpu "$container"; then
            ((skipped_no_gpu += 1))
            continue  # No GPU = no max_runtime limit
        fi

        # Skip monitoring infrastructure containers (they need GPU but aren't user workloads)
        local is_monitoring=$(docker inspect "$container" --format '{{index .Config.Labels "ds01.monitoring"}}' 2>/dev/null)
        if [ "$is_monitoring" = "true" ]; then
            log "Skipping monitoring container: $container (ds01.monitoring=true)"
            continue
        fi

        # Get container type and owner
        local container_type=$(get_container_type "$container")
        local username=$(get_container_owner "$container")

        if [ -z "$username" ]; then
            # Unknown owner with GPU - use strict limits
            log "Warning: GPU container $container has unknown owner, applying strict limits"
            username="unknown"
        fi

        ((monitored_count += 1))

        # Wrap in error handling to prevent one container from breaking the whole loop
        if ! process_container_runtime_universal "$container" "$username" "$container_type"; then
            log_color "Error processing container $container, continuing with next" "$RED"
            continue
        fi
    done

    log_color "Runtime enforcement complete: monitored=$monitored_count (GPU), skipped=$skipped_no_gpu (no GPU), warned=$warned_count, stopped=$stopped_count" "$BLUE"
}

# Process a single container with type-aware max_runtime (universal)
process_container_runtime_universal() {
    local container="$1"
    local username="$2"
    local container_type="$3"

    # Get max runtime based on container type
    local runtime_str
    case "$container_type" in
        orchestration|atomic)
            # DS01 native containers - use user's configured max_runtime
            runtime_str=$(get_max_runtime "$username")
            ;;
        devcontainer|compose|docker|unknown)
            # External containers - use container_types config
            runtime_str=$(get_container_type_max_runtime "$container_type")
            ;;
        *)
            # Fallback to strictest limit
            runtime_str="24h"
            ;;
    esac

    local runtime_seconds=$(runtime_to_seconds "$runtime_str")

    # Skip if no limit set (should not happen for GPU containers, but handle gracefully)
    if [ "$runtime_seconds" -eq 0 ]; then
        log "Container $container (user: $username, type: $container_type) has no runtime limit"
        return 0
    fi

    # Get container start time
    local start_time=$(get_container_start_time "$container")
    if [ "$start_time" -eq 0 ]; then
        log_color "Warning: Could not get start time for $container" "$YELLOW"
        return 0
    fi

    # Calculate runtime
    local now=$(date +%s)
    local runtime_seconds_actual=$((now - start_time))
    local runtime_hours=$((runtime_seconds_actual / 3600))

    # State file for tracking warnings
    local state_file="$STATE_DIR/${container}.state"
    if [ ! -f "$state_file" ]; then
        echo "WARNED=false" > "$state_file"
    fi

    source "$state_file"

    log "Container $container (user: $username, type: $container_type): runtime ${runtime_hours}h / limit $runtime_str"

    # Calculate warning threshold (90% of limit)
    local warning_seconds=$((runtime_seconds * 90 / 100))

    # Check if we should warn
    if [ "$runtime_seconds_actual" -ge "$warning_seconds" ] && [ "$WARNED" != "true" ]; then
        local hours_until_stop=$(( (runtime_seconds - runtime_seconds_actual) / 3600 ))
        send_warning "$username" "$container" "$hours_until_stop"
        sed -i "s/^WARNED=.*/WARNED=true/" "$state_file"
    fi

    # Check if we should stop
    if [ "$runtime_seconds_actual" -ge "$runtime_seconds" ]; then
        stop_runtime_exceeded "$username" "$container" "$runtime_hours"
        return 0
    fi

    return 0
}

# Process a single container (legacy function for backwards compatibility)
process_container_runtime() {
    local container="$1"
    local username="$2"

    # Get max runtime for this user
    local runtime_str=$(get_max_runtime "$username")
    local runtime_seconds=$(runtime_to_seconds "$runtime_str")

    # Skip if no limit set
    if [ "$runtime_seconds" -eq 0 ]; then
        log "Container $container (user: $username) has no runtime limit"
        return 0
    fi

    # Get container start time
    local start_time=$(get_container_start_time "$container")
    if [ "$start_time" -eq 0 ]; then
        log_color "Warning: Could not get start time for $container" "$YELLOW"
        return 0
    fi

    # Calculate runtime
    local now=$(date +%s)
    local runtime_seconds_actual=$((now - start_time))
    local runtime_hours=$((runtime_seconds_actual / 3600))

    # State file for tracking warnings
    local state_file="$STATE_DIR/${container}.state"
    if [ ! -f "$state_file" ]; then
        echo "WARNED=false" > "$state_file"
    fi

    source "$state_file"

    log "Container $container (user: $username): runtime ${runtime_hours}h / limit $runtime_str"

    # Calculate warning threshold (90% of limit)
    local warning_seconds=$((runtime_seconds * 90 / 100))

    # Check if we should warn
    if [ "$runtime_seconds_actual" -ge "$warning_seconds" ] && [ "$WARNED" != "true" ]; then
        local hours_until_stop=$(( (runtime_seconds - runtime_seconds_actual) / 3600 ))
        send_warning "$username" "$container" "$hours_until_stop"
        sed -i "s/^WARNED=.*/WARNED=true/" "$state_file"
    fi

    # Check if we should stop
    if [ "$runtime_seconds_actual" -ge "$runtime_seconds" ]; then
        stop_runtime_exceeded "$username" "$container" "$runtime_hours"
        return 0
    fi

    return 0
}

# Run monitoring
monitor_containers
