#!/bin/bash
# /opt/ds01-infra/scripts/monitoring/check-idle-containers.sh
# Monitor container activity and handle idle cleanup with warnings
#
# This script must be run as root (via cron or sudo)

# Check if running as root when executed directly
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    if [ "$EUID" -ne 0 ]; then
        echo "Error: This script must be run as root (for log/state access)"
        echo "Usage: sudo $0"
        exit 1
    fi
fi

set -e

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
INFRA_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
CONFIG_FILE="$INFRA_ROOT/config/runtime/resource-limits.yaml"
STATE_DIR="/var/lib/ds01/container-states"
LOG_FILE="/var/log/ds01/idle-cleanup.log"

# Source shared library for colors and utilities
source "$INFRA_ROOT/scripts/lib/init.sh"

# Source event logging library
EVENTS_LIB="$INFRA_ROOT/scripts/lib/ds01_events.sh"
if [ -f "$EVENTS_LIB" ]; then
    source "$EVENTS_LIB"
fi

# Create state directory
mkdir -p "$STATE_DIR"
mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

log_color() {
    echo -e "${2}[$(date '+%Y-%m-%d %H:%M:%S')]${NC} $1" | tee -a "$LOG_FILE"
}

# Check if system is in high demand mode (>80% GPU allocation)
is_high_demand() {
    local threshold="${1:-0.8}"

    # Get total GPU count
    local total_gpus=$(nvidia-smi -L 2>/dev/null | wc -l)
    if [ "$total_gpus" -eq 0 ]; then
        echo "false"
        return
    fi

    # Count allocated GPUs (containers with GPU labels)
    local allocated_containers=$(docker ps --filter "label=ds01.gpu.allocated" --format "{{.Names}}" 2>/dev/null | wc -l)

    # Calculate allocation percentage
    local allocation_percent
    allocation_percent=$(echo "scale=2; $allocated_containers / $total_gpus" | bc)

    # Compare with threshold
    if (( $(echo "$allocation_percent >= $threshold" | bc -l) )); then
        echo "true"
    else
        echo "false"
    fi
}

# Get high demand settings from config
get_high_demand_settings() {
    # Use centralized get_resource_limits.py CLI instead of embedded heredoc
    local threshold=$(python3 "$INFRA_ROOT/scripts/docker/get_resource_limits.py" - --high-demand-threshold)
    local reduction=$(python3 "$INFRA_ROOT/scripts/docker/get_resource_limits.py" - --high-demand-reduction)
    echo "$threshold $reduction"
}

# Get idle timeout for user (in hours)
get_idle_timeout() {
    local username="$1"
    # Use centralized get_resource_limits.py CLI instead of embedded heredoc
    python3 "$INFRA_ROOT/scripts/docker/get_resource_limits.py" "$username" --idle-timeout
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

# Get idle timeout for container type (external containers)
get_container_type_idle_timeout() {
    local container_type="$1"

    # Read from config - container_types section
    local timeout=$(python3 << PYEOF
import yaml
import sys

try:
    with open("$CONFIG_FILE") as f:
        config = yaml.safe_load(f)

    container_types = config.get('container_types', {})
    type_config = container_types.get('$container_type', {})
    timeout = type_config.get('idle_timeout', '30m')

    print(timeout if timeout else '30m')
except Exception:
    print('30m')
PYEOF
)
    echo "$timeout"
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

# Convert timeout string (e.g., "48h", "7d") to seconds
# Uses centralized ds01_parse_duration from init.sh
timeout_to_seconds() {
    local timeout="$1"
    local result=$(ds01_parse_duration "$timeout")
    # ds01_parse_duration returns -1 for null/never, convert to 0 for "no timeout"
    if [ "$result" = "-1" ]; then
        echo "0"
    else
        echo "$result"
    fi
}

# Get last activity time for container
get_last_activity() {
    local container="$1"
    
    # Check multiple activity indicators
    local last_exec=$(docker inspect "$container" --format='{{.State.StartedAt}}' 2>/dev/null || echo "")
    local last_cpu=$(docker stats "$container" --no-stream --format "{{.CPUPerc}}" 2>/dev/null | sed 's/%//' || echo "0")
    local last_mem=$(docker stats "$container" --no-stream --format "{{.MemPerc}}" 2>/dev/null | sed 's/%//' || echo "0")
    
    # Get current timestamp
    local now=$(date +%s)
    
    # Get container start time
    local start_time=$(docker inspect "$container" --format='{{.State.StartedAt}}' 2>/dev/null)
    local start_epoch=$(date -d "$start_time" +%s 2>/dev/null || echo "$now")
    
    # Check state file for last known activity
    local state_file="$STATE_DIR/${container}.state"
    
    if [ -f "$state_file" ]; then
        source "$state_file"
        echo "${LAST_ACTIVITY:-$start_epoch}"
    else
        # Initialize state file
        echo "LAST_ACTIVITY=$start_epoch" > "$state_file"
        echo "LAST_CPU=0.0" >> "$state_file"
        echo "WARNED=false" >> "$state_file"
        echo "$start_epoch"
    fi
}

# Update activity state
update_activity() {
    local container="$1"
    local is_active="$2"
    local state_file="$STATE_DIR/${container}.state"
    
    if [ ! -f "$state_file" ]; then
        return
    fi
    
    source "$state_file"
    
    if [ "$is_active" = "true" ]; then
        # Reset activity timestamp
        sed -i "s/^LAST_ACTIVITY=.*/LAST_ACTIVITY=$(date +%s)/" "$state_file"
        sed -i "s/^WARNED=.*/WARNED=false/" "$state_file"
    fi
}

# Check if container is active
is_container_active() {
    local container="$1"
    
    # Check CPU usage
    local cpu=$(docker stats "$container" --no-stream --format "{{.CPUPerc}}" 2>/dev/null | sed 's/%//' || echo "0")
    
    # Consider active if CPU > 1%
    if (( $(echo "$cpu > 1.0" | bc -l) )); then
        echo "true"
        return
    fi
    
    # Check for active processes (excluding bash/sleep)
    local procs=$(docker exec "$container" ps aux 2>/dev/null | grep -v "ps aux" | grep -v "bash" | grep -v "sleep" | wc -l)
    if [ "$procs" -gt 2 ]; then
        echo "true"
        return
    fi
    
    # Check network activity (bytes transmitted in last interval)
    # Docker returns "0B / 0B" format - strip trailing B and handle edge cases
    local net_raw=$(docker stats "$container" --no-stream --format "{{.NetIO}}" 2>/dev/null | cut -d'/' -f1 | tr -d ' ')
    # Handle "0B" specially (numfmt doesn't like bare "0B")
    local net_rx=0
    if [ -n "$net_raw" ] && [ "$net_raw" != "0B" ]; then
        net_rx=$(echo "$net_raw" | numfmt --from=iec 2>/dev/null || echo "0")
    fi
    if [ "$net_rx" -gt 1000000 ]; then  # > 1MB
        echo "true"
        return
    fi
    
    echo "false"
}

# Send warning to user
send_warning() {
    local username="$1"
    local container="$2"
    local hours_until_stop="$3"
    
    # Create warning message in user's home
    local user_home=$(eval echo "~$username")
    local warning_file="$user_home/.ds01-idle-warning"
    
    local high_demand_notice=""
    if [ "$HIGH_DEMAND_MODE" = "true" ]; then
        high_demand_notice="
⚡ HIGH DEMAND MODE ACTIVE
   GPU allocation is >80%. Idle timeouts reduced.
   Container will stop sooner than normal."
    fi

    cat > "$warning_file" << WARNEOF
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
⚠️  IDLE CONTAINER WARNING
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Container: $container
Status: IDLE (no activity detected)
Action: Will auto-stop in ~${hours_until_stop} hours
${high_demand_notice}
This container will be automatically stopped to free
resources for other users. Your work in /workspace
is safe and will persist.

To keep your container running:
  1. Run any command in the container
  2. Or restart your training/script

To disable this warning (if actively training):
  touch /workspace/.keep-alive

To stop and retire now (frees GPU immediately):
  container-retire $(echo $container | cut -d'.' -f1)

Questions? Run 'check-limits' or contact admin.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
WARNEOF
    
    chown "$username:$username" "$warning_file" 2>/dev/null || true
    
    # Also send message to container if running
    if docker exec "$container" test -d /workspace 2>/dev/null; then
        docker exec "$container" bash -c "cat > /workspace/.idle-warning.txt" < "$warning_file" 2>/dev/null || true
    fi
    
    log_color "Warning sent to $username about container $container" "$YELLOW"
}

# Stop idle container
stop_idle_container() {
    local username="$1"
    local container="$2"

    log_color "Stopping idle container: $container (user: $username)" "$YELLOW"

    # Check for .keep-alive file
    if docker exec "$container" test -f /workspace/.keep-alive 2>/dev/null; then
        log_color "Container $container has .keep-alive file - skipping" "$GREEN"
        return
    fi

    # Create notification
    local user_home=$(eval echo "~$username")
    local notification_file="$user_home/.ds01-stopped-notification"

    cat > "$notification_file" << NOTIFEOF
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ℹ️  CONTAINER AUTO-STOPPED
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

Container: $container
Stopped: $(date)
Reason: Idle timeout reached

Your work in /workspace is safe and persists.

To restart your container:
  container-run $(echo $container | cut -d'.' -f1)

To prevent auto-stop in future:
  1. Keep training/scripts running, OR
  2. Create file: touch /workspace/.keep-alive

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
NOTIFEOF

    chown "$username:$username" "$notification_file" 2>/dev/null || true

     # Stop and remove container directly (designed for automation efficiency)
    # GPU freed automatically when container removed (Docker labels gone = GPU freed)
    # This enforces the "running or removed" principle without user command overhead

    # Get idle duration in human-readable format
    local idle_minutes=$((idle_seconds / 60))
    local idle_hours=$((idle_seconds / 3600))
    local idle_display
    if [ "$idle_hours" -gt 0 ]; then
        idle_display="${idle_hours}h"
    else
        idle_display="${idle_minutes}m"
    fi

    # Stop container (10 second grace period)
    if docker stop -t 10 "$container" &>/dev/null; then
        log_color "Stopped idle container: $container" "$GREEN"

        # Log maintenance.idle_kill event (best-effort)
        if command -v log_event &>/dev/null; then
            log_event "maintenance.idle_kill" "$username" "check-idle-containers" \
                container="$container" \
                idle_duration="$idle_display" \
                container_type="$(get_container_type "$container")" || true
        fi

        # Remove container immediately (frees GPU automatically)
        if docker rm "$container" &>/dev/null; then
            log_color "Removed idle container: $container (GPU freed automatically)" "$GREEN"
            logger -t ds01-idle "Retired idle container: $container (user: $username, idle: ${idle_seconds}s)"
        else
            log_color "Warning: Stopped but failed to remove: $container" "$YELLOW"
            # Container is stopped - GPU will be freed by cleanup-stale-gpu-allocations cron
            return 1
        fi
    else
        log_color "Failed to stop idle container: $container" "$RED"
        return 1
    fi

    # Clean up idle monitoring state file
    rm -f "$STATE_DIR/${container}.state"
}

# Main monitoring loop
monitor_containers() {
    log_color "Starting idle container monitoring (universal)" "$BLUE"

    # Check for high demand mode
    local high_demand_settings=$(get_high_demand_settings)
    local hd_threshold=$(echo "$high_demand_settings" | cut -d' ' -f1)
    local hd_reduction=$(echo "$high_demand_settings" | cut -d' ' -f2)

    HIGH_DEMAND_MODE=$(is_high_demand "$hd_threshold")
    HIGH_DEMAND_REDUCTION="$hd_reduction"

    if [ "$HIGH_DEMAND_MODE" = "true" ]; then
        log_color "HIGH DEMAND MODE: GPU allocation above ${hd_threshold}. Idle timeouts reduced by ${hd_reduction}." "$YELLOW"

        # Log event
        if [ -f "$INFRA_ROOT/scripts/docker/event-logger.py" ]; then
            python3 "$INFRA_ROOT/scripts/docker/event-logger.py" "system.high_demand" \
                --message "High demand mode active - idle timeouts reduced" 2>/dev/null || true
        fi
    fi

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
    local skipped_monitoring=0

    for container in $containers; do
        # Verify container still exists (race condition protection)
        if ! docker ps --format "{{.Names}}" | grep -q "^${container}$"; then
            log "Container $container no longer exists, skipping"
            continue
        fi

        # Core principle: GPU access = ephemeral enforcement, No GPU = permanent OK
        if ! container_has_gpu "$container"; then
            ((skipped_no_gpu += 1))
            continue  # No GPU = no idle timeout
        fi

        # Skip monitoring infrastructure containers (they need GPU but aren't user workloads)
        local is_monitoring=$(docker inspect "$container" --format '{{index .Config.Labels "ds01.monitoring"}}' 2>/dev/null)
        if [ "$is_monitoring" = "true" ]; then
            log "Skipping monitoring container: $container (ds01.monitoring=true)"
            ((skipped_monitoring += 1))
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
        if ! process_container_universal "$container" "$username" "$container_type"; then
            log_color "Error processing container $container, continuing with next" "$RED"
            continue
        fi
    done

    log_color "Idle monitoring complete: monitored=$monitored_count (GPU), skipped_no_gpu=$skipped_no_gpu, skipped_monitoring=$skipped_monitoring, warned=$warned_count, stopped=$stopped_count" "$BLUE"
}

# Process a single container with type-aware timeout (universal)
process_container_universal() {
    local container="$1"
    local username="$2"
    local container_type="$3"

    # Get timeout based on container type
    local timeout_str
    case "$container_type" in
        orchestration|atomic)
            # DS01 native containers - use user's configured idle_timeout
            timeout_str=$(get_idle_timeout "$username")
            ;;
        devcontainer|compose|docker|unknown)
            # External containers - use container_types config
            timeout_str=$(get_container_type_idle_timeout "$container_type")
            ;;
        *)
            # Fallback to strictest timeout
            timeout_str="15m"
            ;;
    esac

    local timeout_seconds=$(timeout_to_seconds "$timeout_str")

    # Skip if no timeout set (should not happen for GPU containers, but handle gracefully)
    if [ "$timeout_seconds" -eq 0 ]; then
        log "Container $container (user: $username, type: $container_type) has no idle timeout"
        return 0
    fi

    # Apply high-demand reduction if active
    local original_timeout_seconds="$timeout_seconds"
    if [ "$HIGH_DEMAND_MODE" = "true" ]; then
        # Reduce timeout by the configured factor (e.g., 0.5 = 50% of normal)
        timeout_seconds=$(echo "scale=0; $timeout_seconds * $HIGH_DEMAND_REDUCTION / 1" | bc)
        log "High demand: Reduced timeout for $container from ${original_timeout_seconds}s to ${timeout_seconds}s"
    fi

    # Check if container is active
    local active=$(is_container_active "$container")

    if [ "$active" = "true" ]; then
        update_activity "$container" "true"
        log "Container $container (user: $username, type: $container_type) is active"
        return 0
    fi

    # Get last activity time
    local last_activity=$(get_last_activity "$container")
    local now=$(date +%s)
    local idle_seconds=$((now - last_activity))
    local idle_hours=$((idle_seconds / 3600))
    local idle_minutes=$((idle_seconds / 60))

    # Calculate warning threshold (80% of timeout)
    local warning_seconds=$((timeout_seconds * 80 / 100))

    local state_file="$STATE_DIR/${container}.state"

    # Initialize state file if missing
    if [ ! -f "$state_file" ]; then
        log "Initializing state file for $container"
        echo "LAST_ACTIVITY=$last_activity" > "$state_file"
        echo "LAST_CPU=0.0" >> "$state_file"
        echo "WARNED=false" >> "$state_file"
    fi

    source "$state_file"

    log "Container $container (user: $username, type: $container_type): idle for ${idle_minutes}m (timeout: $timeout_str)"

    # Check if we should warn
    if [ "$idle_seconds" -ge "$warning_seconds" ] && [ "$WARNED" != "true" ]; then
        local minutes_until_stop=$(( (timeout_seconds - idle_seconds) / 60 ))
        send_warning "$username" "$container" "$minutes_until_stop"
        sed -i "s/^WARNED=.*/WARNED=true/" "$state_file"
    fi

    # Check if we should stop
    if [ "$idle_seconds" -ge "$timeout_seconds" ]; then
        stop_idle_container "$username" "$container"
        return 0
    fi

    return 0
}

# Process a single container (legacy function for backwards compatibility)
process_container() {
    local container="$1"
    local username="$2"

    # Get timeout for this user
    local timeout_str=$(get_idle_timeout "$username")
    local timeout_seconds=$(timeout_to_seconds "$timeout_str")

    # Skip if no timeout set
    if [ "$timeout_seconds" -eq 0 ]; then
        log "Container $container (user: $username) has no idle timeout"
        return 0
    fi

    # Apply high-demand reduction if active
    local original_timeout_seconds="$timeout_seconds"
    if [ "$HIGH_DEMAND_MODE" = "true" ]; then
        # Reduce timeout by the configured factor (e.g., 0.5 = 50% of normal)
        timeout_seconds=$(echo "scale=0; $timeout_seconds * $HIGH_DEMAND_REDUCTION / 1" | bc)
        log "High demand: Reduced timeout for $container from ${original_timeout_seconds}s to ${timeout_seconds}s"
    fi

    # Check if container is active
    local active=$(is_container_active "$container")

    if [ "$active" = "true" ]; then
        update_activity "$container" "true"
        log "Container $container (user: $username) is active"
        return 0
    fi

    # Get last activity time
    local last_activity=$(get_last_activity "$container")
    local now=$(date +%s)
    local idle_seconds=$((now - last_activity))
    local idle_hours=$((idle_seconds / 3600))

    # Calculate warning threshold (80% of timeout)
    local warning_seconds=$((timeout_seconds * 80 / 100))

    local state_file="$STATE_DIR/${container}.state"

    # Initialize state file if missing
    if [ ! -f "$state_file" ]; then
        log "Initializing state file for $container"
        echo "LAST_ACTIVITY=$last_activity" > "$state_file"
        echo "LAST_CPU=0.0" >> "$state_file"
        echo "WARNED=false" >> "$state_file"
    fi

    source "$state_file"

    log "Container $container (user: $username): idle for ${idle_hours}h (timeout: $timeout_str)"

    # Check if we should warn
    if [ "$idle_seconds" -ge "$warning_seconds" ] && [ "$WARNED" != "true" ]; then
        local hours_until_stop=$(( (timeout_seconds - idle_seconds) / 3600 ))
        send_warning "$username" "$container" "$hours_until_stop"
        sed -i "s/^WARNED=.*/WARNED=true/" "$state_file"
    fi

    # Check if we should stop
    if [ "$idle_seconds" -ge "$timeout_seconds" ]; then
        stop_idle_container "$username" "$container"
        return 0
    fi

    return 0
}

# Only run when executed, not sourced
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    monitor_containers
fi