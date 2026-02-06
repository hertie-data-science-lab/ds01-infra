#!/bin/bash
# /opt/ds01-infra/scripts/monitoring/collect-resource-stats.sh
# Collect resource usage and PSI metrics per user slice
#
# This script must be run as root (via cron or sudo)

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root (for cgroup access)"
    echo "Usage: sudo $0 [--verbose]"
    exit 1
fi

set -e

SCRIPT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd)"
INFRA_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

# Source shared library for logging
source "$INFRA_ROOT/scripts/lib/init.sh"

# Source event logging library
EVENTS_LIB="$INFRA_ROOT/scripts/lib/ds01_events.sh"
if [ -f "$EVENTS_LIB" ]; then
    source "$EVENTS_LIB"
fi

# Configuration
CGROUP_ROOT="/sys/fs/cgroup/ds01.slice"
STATS_LOG="/var/log/ds01/resource-stats.log"
STATE_DIR="/var/lib/ds01/resource-stats"
OOM_STATE_FILE="$STATE_DIR/oom-counts.json"

# Parse arguments
VERBOSE=false
if [[ "$1" == "--verbose" ]]; then
    VERBOSE=true
fi

# Create required directories
mkdir -p "$(dirname "$STATS_LOG")"
mkdir -p "$STATE_DIR"

# Initialize OOM state file if missing
if [ ! -f "$OOM_STATE_FILE" ]; then
    echo "{}" > "$OOM_STATE_FILE"
    chmod 644 "$OOM_STATE_FILE"
fi

log_verbose() {
    if $VERBOSE; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
    fi
}

# Extract username and group from slice name: ds01-{group}-{user}.slice
parse_slice_name() {
    local slice="$1"
    local basename="${slice%.slice}"

    # Remove ds01- prefix
    local trimmed="${basename#ds01-}"

    # Extract group (first component)
    local group="${trimmed%%-*}"

    # Extract user (remaining after first hyphen)
    local user="${trimmed#*-}"

    echo "$group:$user"
}

# Read cgroup file safely
read_cgroup_file() {
    local file="$1"
    if [ -f "$file" ]; then
        cat "$file" 2>/dev/null || echo ""
    else
        echo ""
    fi
}

# Parse PSI metric (format: "some avg10=12.34 avg60=23.45 ... full avg10=5.67 ...")
# Returns avg10 value for specified type (some/full)
parse_psi_avg10() {
    local psi_content="$1"
    local type="$2"  # "some" or "full"

    # Extract the line starting with the type
    local line=$(echo "$psi_content" | grep "^${type} " || echo "")
    if [ -z "$line" ]; then
        echo "0"
        return
    fi

    # Extract avg10 value
    local avg10=$(echo "$line" | sed -n 's/.*avg10=\([0-9.]*\).*/\1/p')
    if [ -z "$avg10" ]; then
        echo "0"
    else
        echo "$avg10"
    fi
}

# Parse memory.events for OOM counters
parse_memory_events() {
    local events_content="$1"
    local counter="$2"  # "oom" or "oom_kill"

    local value=$(echo "$events_content" | grep "^${counter} " | awk '{print $2}')
    if [ -z "$value" ]; then
        echo "0"
    else
        echo "$value"
    fi
}

# Check OOM kill counter and log event if increased
check_oom_kill() {
    local user="$1"
    local group="$2"
    local current_count="$3"

    # Read previous count from state file
    local prev_count=$(python3 -c "
import json
import sys
try:
    with open('$OOM_STATE_FILE', 'r') as f:
        state = json.load(f)
    print(state.get('${user}', 0))
except Exception:
    print(0)
" 2>/dev/null || echo "0")

    # Check if count increased
    if [ "$current_count" -gt "$prev_count" ]; then
        local oom_events=$((current_count - prev_count))
        log_verbose "OOM kill detected for user $user (count: $prev_count -> $current_count)"

        # Log OOM event (best-effort, never blocks)
        if command -v log_event &>/dev/null; then
            log_event "resource.oom_kill" "$user" "collect-resource-stats" \
                group="$group" \
                oom_count="$oom_events" \
                total_oom_kills="$current_count" || true
        fi

        # Update state file
        python3 -c "
import json
try:
    with open('$OOM_STATE_FILE', 'r') as f:
        state = json.load(f)
except Exception:
    state = {}

state['${user}'] = ${current_count}

with open('$OOM_STATE_FILE', 'w') as f:
    json.dump(state, f, indent=2)
" 2>/dev/null || true
    fi
}

# Collect stats for a single user slice
collect_slice_stats() {
    local slice_dir="$1"
    local slice_name="$(basename "$slice_dir")"

    # Parse slice name to extract group and user
    local parsed=$(parse_slice_name "$slice_name")
    local group="${parsed%%:*}"
    local user="${parsed##*:}"

    if [ -z "$user" ] || [ -z "$group" ]; then
        log_verbose "Skipping invalid slice name: $slice_name"
        return
    fi

    log_verbose "Collecting stats for $slice_name (group=$group, user=$user)"

    # Initialize metrics
    local timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")
    local memory_current=0
    local memory_max=0
    local memory_pct=0
    local pids_current=0
    local pids_max=0
    local psi_memory_some_avg10=0
    local psi_memory_full_avg10=0
    local psi_cpu_some_avg10=0
    local psi_cpu_full_avg10=0
    local oom_count=0
    local oom_kill_count=0

    # Read memory metrics
    memory_current=$(read_cgroup_file "$slice_dir/memory.current")
    memory_max=$(read_cgroup_file "$slice_dir/memory.max")

    # Calculate memory percentage
    if [ -n "$memory_current" ] && [ -n "$memory_max" ] && [ "$memory_max" != "max" ]; then
        if [ "$memory_max" -gt 0 ]; then
            memory_pct=$(echo "scale=2; ($memory_current * 100) / $memory_max" | bc)
        fi
    fi

    # Read pids metrics
    pids_current=$(read_cgroup_file "$slice_dir/pids.current")
    pids_max=$(read_cgroup_file "$slice_dir/pids.max")

    # Read PSI metrics (only if files exist - older kernels may not have PSI)
    if [ -f "$slice_dir/memory.pressure" ]; then
        local memory_pressure=$(read_cgroup_file "$slice_dir/memory.pressure")
        psi_memory_some_avg10=$(parse_psi_avg10 "$memory_pressure" "some")
        psi_memory_full_avg10=$(parse_psi_avg10 "$memory_pressure" "full")
    fi

    if [ -f "$slice_dir/cpu.pressure" ]; then
        local cpu_pressure=$(read_cgroup_file "$slice_dir/cpu.pressure")
        psi_cpu_some_avg10=$(parse_psi_avg10 "$cpu_pressure" "some")
        psi_cpu_full_avg10=$(parse_psi_avg10 "$cpu_pressure" "full")
    fi

    # Read memory.events for OOM detection
    if [ -f "$slice_dir/memory.events" ]; then
        local memory_events=$(read_cgroup_file "$slice_dir/memory.events")
        oom_count=$(parse_memory_events "$memory_events" "oom")
        oom_kill_count=$(parse_memory_events "$memory_events" "oom_kill")

        # Check for OOM kill events and log if increased
        if [ "$oom_kill_count" -gt 0 ]; then
            check_oom_kill "$user" "$group" "$oom_kill_count"
        fi
    fi

    # Build JSON log entry
    local json_entry=$(cat <<JSONEOF
{"timestamp":"$timestamp","user":"$user","group":"$group","memory_current_bytes":${memory_current:-0},"memory_max_bytes":"${memory_max:-max}","memory_pct":${memory_pct:-0},"pids_current":${pids_current:-0},"pids_max":"${pids_max:-max}","psi_memory_some_avg10":${psi_memory_some_avg10},"psi_memory_full_avg10":${psi_memory_full_avg10},"psi_cpu_some_avg10":${psi_cpu_some_avg10},"psi_cpu_full_avg10":${psi_cpu_full_avg10},"oom_count":${oom_count},"oom_kill_count":${oom_kill_count}}
JSONEOF
)

    # Append to log file (best-effort, never fails)
    echo "$json_entry" >> "$STATS_LOG" 2>/dev/null || true

    log_verbose "  memory: ${memory_current}/${memory_max} (${memory_pct}%)"
    log_verbose "  pids: ${pids_current}/${pids_max}"
    log_verbose "  PSI memory: some=${psi_memory_some_avg10}% full=${psi_memory_full_avg10}%"
    log_verbose "  PSI cpu: some=${psi_cpu_some_avg10}% full=${psi_cpu_full_avg10}%"
    log_verbose "  OOM: count=${oom_count} kills=${oom_kill_count}"
}

# Main collection loop
main() {
    log_verbose "Starting resource stats collection"

    # Check if cgroup root exists
    if [ ! -d "$CGROUP_ROOT" ]; then
        log_verbose "Cgroup root $CGROUP_ROOT does not exist, nothing to collect"
        exit 0
    fi

    # Iterate over all user slices
    local slice_count=0
    for slice_dir in "$CGROUP_ROOT"/ds01-*-*.slice; do
        # Check if glob matched anything
        if [ ! -d "$slice_dir" ]; then
            continue
        fi

        # Skip the parent ds01.slice itself
        if [ "$(basename "$slice_dir")" = "ds01.slice" ]; then
            continue
        fi

        # Collect stats for this slice
        collect_slice_stats "$slice_dir"
        ((slice_count++))
    done

    log_verbose "Collection complete: $slice_count user slices processed"
}

# Only run when executed, not sourced
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main
fi
