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
CONFIG_FILE="$INFRA_ROOT/config/runtime/resource-limits.yaml"
STATE_DIR="/var/lib/ds01/container-runtime"
LOG_FILE="/var/log/ds01/runtime-enforcement.log"

# Source shared library for colors and utilities
source "$INFRA_ROOT/scripts/lib/init.sh"

# Source event logging library
EVENTS_LIB="$INFRA_ROOT/scripts/lib/ds01_events.sh"
if [ -f "$EVENTS_LIB" ]; then
    source "$EVENTS_LIB"
fi

# Create state and log directories
mkdir -p "$STATE_DIR"
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_color() {
    echo -e "${2}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

# Send message to a specific user's terminals (not wall broadcast)
notify_user() {
    local username="$1"
    local message="$2"
    local sent=false
    while IFS= read -r tty; do
        [ -z "$tty" ] && continue
        echo "$message" > "/dev/$tty" 2>/dev/null && sent=true
    done < <(who | awk -v user="$username" '$1 == user {print $2}')
    if [ "$sent" = false ]; then
        log "User $username has no active terminals — notification not delivered"
    fi
}

# Get max runtime for user (in hours)
get_max_runtime() {
    local username="$1"
    # Use centralized get_resource_limits.py CLI instead of embedded heredoc
    python3 "$INFRA_ROOT/scripts/docker/get_resource_limits.py" "$username" --max-runtime
}

# Check if user is exempt from enforcement
check_exemption() {
    local username="$1"
    local enforcement_type="$2"
    python3 "$INFRA_ROOT/scripts/docker/get_resource_limits.py" "$username" --check-exemption "$enforcement_type"
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

    # Broadcast warning via wall (all users see it in their terminals)
    local message="DS01 MAX RUNTIME WARNING

Container: $container
Status: Will auto-stop in ~${hours_until_stop} hours
Reason: Maximum runtime limit approaching

Save your work now:
  - Checkpoint your training/model state
  - Ensure results are saved to /workspace

Your /workspace data persists after stop."

    notify_user "$username" "$message"

    log_color "Runtime warning sent to $username for container $container" "$YELLOW"
}

# Stop container that exceeded runtime
stop_runtime_exceeded() {
    local username="$1"
    local container="$2"
    local runtime_hours="$3"

    log_color "Stopping container: $container (user: $username, runtime: ${runtime_hours}h)" "$YELLOW"

    # Extract container name (remove ._.uid suffix)
    local container_name=$(echo "$container" | cut -d'.' -f1)

    # Stop container directly (designed for automation efficiency)
    # Note: Container is stopped but NOT removed - will be removed by cleanup-stale-containers
    # after container_hold_after_stop timeout. GPU will be freed after gpu_hold_after_stop timeout.

    # Get container type for logging (already available from caller, but re-get if needed)
    if [ -z "$container_type" ]; then
        container_type=$(get_container_type "$container")
    fi

    # Get SIGTERM grace period from config with container-type-specific override
    local grace_seconds=$(python3 -c "
import yaml
import sys
try:
    with open('$CONFIG_FILE') as f:
        config = yaml.safe_load(f)
    ct_config = config.get('container_types', {}).get('$container_type', {})
    grace = ct_config.get('sigterm_grace_seconds')
    if grace is not None:
        print(grace)
    else:
        print(config.get('policies', {}).get('sigterm_grace_seconds', 60))
except Exception:
    print(60)
" 2>/dev/null || echo 60)

    # Stop container with SIGTERM grace period
    if docker stop -t "$grace_seconds" "$container" &>/dev/null; then
        log_color "Stopped container: $container (max runtime exceeded: ${runtime_hours}h)" "$GREEN"
        logger -t ds01-maxruntime "Stopped container: $container (user: $username, runtime: ${runtime_hours}h)"

        # Log maintenance.runtime_kill event (best-effort)
        if command -v log_event &>/dev/null; then
            log_event "maintenance.runtime_kill" "$username" "enforce-max-runtime" \
                container="$container" \
                runtime="${runtime_hours}h" \
                max_runtime="configured_limit" \
                container_type="$container_type" || true
        fi

        # Container is now stopped:
        # - GPU will be freed by cleanup-stale-gpu-allocations after gpu_hold_after_stop timeout
        # - Container will be removed by cleanup-stale-containers after container_hold_after_stop timeout

        # Broadcast stop notification via wall
        local stop_message="DS01 CONTAINER STOPPED - MAX RUNTIME EXCEEDED

Container: $container_name
Stopped: $(date)
Reason: Maximum runtime limit reached (${runtime_hours}h)

Your /workspace data is safe.
To restart: container-run $container_name"

        notify_user "$username" "$stop_message"
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

    # Check exemption before enforcement
    local exemption_status=$(check_exemption "$username" "max_runtime")
    if [[ "$exemption_status" == exempt:* ]]; then
        local exempt_reason="${exemption_status#exempt: }"
        log "Container $container (user: $username) is EXEMPT from max runtime: $exempt_reason"

        # Log exemption for audit
        if command -v log_event &>/dev/null; then
            log_event "maintenance.runtime_exempt" "$username" "enforce-max-runtime" \
                container="$container" \
                reason="$exempt_reason" || true
        fi

        return 0
    fi

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

# Run monitoring (only when executed directly, not sourced)
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    monitor_containers
fi
