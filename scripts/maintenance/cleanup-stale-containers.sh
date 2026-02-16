#!/bin/bash
# Cleanup stale containers that have been stopped longer than container_hold_after_stop
# /opt/ds01-infra/scripts/maintenance/cleanup-stale-containers.sh
#
# This script should be run periodically (e.g., via cron every hour)
# to remove stopped containers that have exceeded their container_hold_after_stop timeout.
# Uses Docker-native queries (no metadata files needed).

set -e

# Configuration
SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
INFRA_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"
CONFIG_FILE="$INFRA_ROOT/config/runtime/resource-limits.yaml"
LOG_DIR="/var/log/ds01"
LOG_FILE="$LOG_DIR/cleanup-stale-containers.log"

# Source shared library for colors and utilities
source "$INFRA_ROOT/scripts/lib/init.sh"

# Source event logging library
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

# Get container hold timeout for user (in hours)
get_container_hold_timeout() {
    local username="$1"
    # Use centralized get_resource_limits.py CLI instead of embedded heredoc
    python3 "$INFRA_ROOT/scripts/docker/get_resource_limits.py" "$username" --container-hold-time
}

# Parse duration string (e.g., "12h", "0.5h") to seconds
# Wrapper around centralized ds01_parse_duration from init.sh
parse_duration() {
    local duration="$1"
    ds01_parse_duration "$duration"
}

# Get container owner from labels/path/name (fallback chain)
get_container_owner() {
    local container="$1"

    # Try ds01.user label first
    local owner=$(docker inspect "$container" --format '{{index .Config.Labels "ds01.user"}}' 2>/dev/null)
    if [ -n "$owner" ] && [ "$owner" != "<no value>" ]; then
        echo "$owner"
        return
    fi

    # Legacy fallback - remove when no legacy containers remain
    # TODO: Remove aime.mlc.USER fallback when docker ps --filter label=aime.mlc.USER returns nothing
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

    echo "unknown"
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

# Get container hold timeout for specific container type (external containers)
get_container_type_hold_timeout() {
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
    timeout = type_config.get('container_hold_after_stop')

    # Fallback to defaults if not defined per container type
    if not timeout:
        defaults = config.get('defaults', {})
        timeout = defaults.get('container_hold_after_stop', '0.5h')

    print(timeout if timeout else '0.5h')
except Exception as e:
    print('0.5h', file=sys.stderr)
    print('0.5h')
PYEOF
)
    echo "$timeout"
}

# Cleanup created-but-never-started containers
cleanup_created_containers() {
    log "Checking for created-never-started containers..."

    # Get created container timeout from policies
    local created_timeout=$(python3 << PYEOF
import yaml
try:
    with open("$CONFIG_FILE") as f:
        config = yaml.safe_load(f)
    timeout = config.get('policies', {}).get('created_container_timeout', '30m')
    print(timeout)
except Exception:
    print('30m')
PYEOF
)

    local created_timeout_seconds=$(parse_duration "$created_timeout")

    # Find all containers in created state
    local created_containers
    if [ -n "$NAME_FILTER" ]; then
        created_containers=$(docker ps -a --filter "status=created" --filter "name=$NAME_FILTER" --format "{{.Names}}" 2>/dev/null || true)
    else
        created_containers=$(docker ps -a --filter "status=created" --format "{{.Names}}" 2>/dev/null || true)
    fi

    if [ -z "$created_containers" ]; then
        log "No created-state containers found"
        return 0
    fi

    local created_removed=0
    local created_skipped=0

    while IFS= read -r container; do
        [ -z "$container" ] && continue

        # Skip infrastructure containers
        local is_monitoring=$(docker inspect "$container" --format '{{index .Config.Labels "ds01.monitoring"}}' 2>/dev/null)
        local is_protected=$(docker inspect "$container" --format '{{index .Config.Labels "ds01.protected"}}' 2>/dev/null)

        if [ "$is_monitoring" = "true" ] || [ "$is_protected" = "true" ]; then
            log "Skipping infrastructure container: $container"
            ((created_skipped += 1))
            continue
        fi

        # Get creation time (use CreatedAt for created-state containers)
        local created_at=$(docker inspect "$container" --format '{{.Created}}' 2>/dev/null || echo "")

        if [ -z "$created_at" ]; then
            log "WARN: Cannot get CreatedAt for $container, skipping"
            ((created_skipped += 1))
            continue
        fi

        # Calculate age
        local created_epoch=$(date -d "$created_at" +%s 2>/dev/null || echo "0")

        if [ "$created_epoch" -eq 0 ]; then
            log "WARN: Cannot parse CreatedAt for $container, skipping"
            ((created_skipped += 1))
            continue
        fi

        local current_epoch=$(date +%s)
        local age_seconds=$((current_epoch - created_epoch))
        local age_minutes=$((age_seconds / 60))

        # Check if exceeded timeout
        if [ "$age_seconds" -gt "$created_timeout_seconds" ]; then
            # Get owner for logging
            local owner=$(get_container_owner "$container")

            log "Removing created-never-started container: $container (owner: $owner, age: ${age_minutes}m)"

            # Check if GPU was allocated (check DeviceRequests)
            local gpu_info=$(docker inspect "$container" --format '{{.HostConfig.DeviceRequests}}' 2>/dev/null)
            local had_gpu=false
            if echo "$gpu_info" | grep -qi "nvidia\|gpu"; then
                had_gpu=true
            fi

            # Release GPU if allocated
            if [ "$had_gpu" = "true" ]; then
                log "Releasing GPU for created container: $container"
                python3 "$INFRA_ROOT/scripts/docker/gpu_allocator_v2.py" release "$container" &>/dev/null || true
            fi

            # Remove container
            if docker rm "$container" &>/dev/null; then
                log "✓ Removed created-state container: $container"
                logger -t ds01-cleanup "Removed created-never-started container: $container (owner: $owner, age: ${age_seconds}s)"

                # Log event
                if command -v log_event &>/dev/null; then
                    log_event "container.remove" "$owner" "cleanup-stale-containers" \
                        container="$container" \
                        reason="created_never_started" \
                        age="${age_minutes}m" || true
                fi

                ((created_removed += 1))
            else
                log "ERROR: Failed to remove created container $container"
            fi
        else
            local time_remaining=$((created_timeout_seconds - age_seconds))
            local minutes_remaining=$((time_remaining / 60))
            log "Created container $container: age ${age_minutes}m, will remove in ${minutes_remaining}m"
        fi

    done <<< "$created_containers"

    if [ "$created_removed" -gt 0 ]; then
        log "✓ Removed $created_removed created-state container(s)"
    fi

    if [ "$created_skipped" -gt 0 ]; then
        log "INFO: Skipped $created_skipped created-state container(s)"
    fi
}

# Parse command-line arguments
NAME_FILTER=""
while [[ $# -gt 0 ]]; do
    case "$1" in
        --name-filter)
            NAME_FILTER="$2"
            shift 2
            ;;
        *)
            shift
            ;;
    esac
done

log "Starting stale container cleanup (Docker-native)..."

if [ -n "$NAME_FILTER" ]; then
    log "Filtering containers by name: $NAME_FILTER"
fi

# First, cleanup created-but-never-started containers
cleanup_created_containers

# Find ALL stopped containers (universal cleanup)
if [ -n "$NAME_FILTER" ]; then
    STOPPED_CONTAINERS=$(docker ps -a --filter "status=exited" --filter "name=$NAME_FILTER" --format "{{.Names}}" 2>/dev/null || true)
else
    STOPPED_CONTAINERS=$(docker ps -a --filter "status=exited" --format "{{.Names}}" 2>/dev/null || true)
fi

if [ -z "$STOPPED_CONTAINERS" ]; then
    log "✓ No stopped containers found"
    exit 0
fi

REMOVED_COUNT=0
SKIPPED_COUNT=0
ERROR_COUNT=0

while IFS= read -r container_tag; do
    [ -z "$container_tag" ] && continue

    # Skip infrastructure containers
    is_monitoring=$(docker inspect "$container_tag" --format '{{index .Config.Labels "ds01.monitoring"}}' 2>/dev/null)
    is_protected=$(docker inspect "$container_tag" --format '{{index .Config.Labels "ds01.protected"}}' 2>/dev/null)

    if [ "$is_monitoring" = "true" ] || [ "$is_protected" = "true" ]; then
        log "Skipping infrastructure container: $container_tag (protected)"
        ((SKIPPED_COUNT += 1))
        continue
    fi

    # Get container owner and type
    username=$(get_container_owner "$container_tag")
    container_type=$(get_container_type "$container_tag")

    if [ -z "$username" ] || [ "$username" = "unknown" ]; then
        log "WARN: Unknown owner for container: $container_tag (type: $container_type), applying strictest timeout"
        username="unknown"
    fi

    # Get container hold timeout based on type and owner
    if [ "$username" != "unknown" ]; then
        # Known owner - use their group's container_hold_after_stop
        container_hold=$(get_container_hold_timeout "$username")
    else
        # Unknown owner - use container type config or strictest timeout
        container_hold=$(get_container_type_hold_timeout "$container_type")
    fi

    hold_seconds=$(parse_duration "$container_hold")

    # If never remove, skip
    if [ "$hold_seconds" -eq -1 ]; then
        log "Container $container_tag (user: $username) has indefinite hold, skipping"
        ((SKIPPED_COUNT += 1))
        continue
    fi

    # Get FinishedAt timestamp from Docker state (automatic)
    finished_at=$(docker inspect --format '{{.State.FinishedAt}}' "$container_tag" 2>/dev/null || echo "")

    if [ -z "$finished_at" ] || [ "$finished_at" = "0001-01-01T00:00:00Z" ]; then
        log "WARN: Container $container_tag has no valid FinishedAt timestamp, skipping"
        ((SKIPPED_COUNT += 1))
        continue
    fi

    # Calculate elapsed time since stop
    stopped_epoch=$(date -d "$finished_at" +%s 2>/dev/null || echo "0")

    if [ "$stopped_epoch" -eq 0 ]; then
        log "WARN: Could not parse FinishedAt for $container_tag, skipping"
        ((SKIPPED_COUNT += 1))
        continue
    fi

    current_epoch=$(date +%s)
    elapsed_seconds=$((current_epoch - stopped_epoch))
    elapsed_hours=$((elapsed_seconds / 3600))

    # Check if exceeded timeout
    if [ "$elapsed_seconds" -gt "$hold_seconds" ]; then
        log "Removing stale container: $container_tag (user: $username, type: $container_type, stopped: ${elapsed_hours}h ago, limit: $container_hold)"

        # Check if GPU was allocated and release before removal
        gpu_info=$(docker inspect "$container_tag" --format '{{.HostConfig.DeviceRequests}}' 2>/dev/null)
        if echo "$gpu_info" | grep -qi "nvidia\|gpu"; then
            log "Releasing GPU for stopped container: $container_tag"
            python3 "$INFRA_ROOT/scripts/docker/gpu_allocator_v2.py" release "$container_tag" &>/dev/null || true
        fi

        # Remove container
        if docker rm "$container_tag" &>/dev/null; then
            log "✓ Removed: $container_tag"
            logger -t ds01-cleanup "Removed stale container: $container_tag (user: $username, type: $container_type, stopped: ${elapsed_seconds}s ago)"

            # Log container.remove event (best-effort)
            if command -v log_event &>/dev/null; then
                log_event "container.remove" "$username" "cleanup-stale-containers" \
                    container="$container_tag" \
                    reason="hold_expired" \
                    stopped_duration="${elapsed_hours}h" \
                    container_type="$container_type" || true
            fi

            ((REMOVED_COUNT += 1))
        else
            log "ERROR: Failed to remove $container_tag"
            ((ERROR_COUNT += 1))
        fi
    else
        # Still within hold period
        time_remaining=$((hold_seconds - elapsed_seconds))
        hours_remaining=$((time_remaining / 3600))
        log "Container $container_tag (user: $username, type: $container_type): ${elapsed_hours}h stopped, will remove in ${hours_remaining}h"
    fi

done <<< "$STOPPED_CONTAINERS"

# Summary
if [ "$REMOVED_COUNT" -gt 0 ]; then
    log "✓ Removed $REMOVED_COUNT stale container(s)"
fi

if [ "$SKIPPED_COUNT" -gt 0 ]; then
    log "INFO: Skipped $SKIPPED_COUNT container(s)"
fi

if [ "$ERROR_COUNT" -gt 0 ]; then
    log "WARN: Failed to remove $ERROR_COUNT container(s)"
fi

if [ "$REMOVED_COUNT" -eq 0 ] && [ "$ERROR_COUNT" -eq 0 ]; then
    log "✓ No stale containers to remove"
fi

log "Cleanup completed successfully"
