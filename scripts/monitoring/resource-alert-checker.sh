#!/bin/bash
# /opt/ds01-infra/scripts/monitoring/resource-alert-checker.sh
# DS01 Resource Alert Checker
#
# Checks resource usage for all users and generates alerts when approaching limits.
# Delivers alerts to user terminals with 4-hour cooldown. Clears alerts when
# usage drops below threshold.
#
# Usage:
#   resource-alert-checker.sh              # Check all users
#   resource-alert-checker.sh <username>   # Check specific user
#   resource-alert-checker.sh --clean      # Remove old alerts

set -e

INFRA_ROOT="/opt/ds01-infra"
SCRIPT_DIR="$INFRA_ROOT/scripts"
ALERTS_DIR="/var/lib/ds01/alerts"
RESOURCE_PARSER="$SCRIPT_DIR/docker/get_resource_limits.py"
GPU_STATE_READER="$SCRIPT_DIR/docker/gpu-state-reader.py"
EVENT_LOGGER="$SCRIPT_DIR/docker/event-logger.py"

# Source notification library for terminal delivery
# shellcheck source=../lib/ds01_notify.sh
source "$INFRA_ROOT/scripts/lib/ds01_notify.sh"

# Soft limit threshold (80%)
SOFT_LIMIT_THRESHOLD=80

# Alert retention (hours)
ALERT_RETENTION_HOURS=24

# Terminal notification cooldown (hours) — avoids spamming users
NOTIFY_COOLDOWN_HOURS=4

# Ensure alerts directory exists
mkdir -p "$ALERTS_DIR"
chmod 755 "$ALERTS_DIR"

# Log to event system
log_event() {
    local event_type="$1"
    local username="$2"
    local message="$3"

    if [ -f "$EVENT_LOGGER" ]; then
        python3 "$EVENT_LOGGER" "$event_type" \
            --user "$username" \
            --message "$message" 2>/dev/null || true
    fi
}

# Get list of DS01 users (users with containers or in groups)
get_ds01_users() {
    # Get users from container labels
    docker ps -a --filter "label=ds01.managed=true" --format '{{.Label "ds01.user"}}' 2>/dev/null | sort -u
}

# ── deliver_alert_to_terminal ─────────────────────────────────────────────────
# Deliver a quota alert to the user's terminal with 4-hour cooldown.
# Only delivers if the cooldown period has elapsed since last notification.
#
# Usage: deliver_alert_to_terminal <username> <alert_type> <message_body>
deliver_alert_to_terminal() {
    local username="$1"
    local alert_type="$2"
    local message_body="$3"
    local alerts_file="$ALERTS_DIR/${username}.json"

    [ -f "$alerts_file" ] || return 0

    # Check cooldown: has this alert type been notified recently?
    local last_notified
    last_notified=$(python3 -c "
import json, sys
try:
    alerts = json.load(open('$alerts_file'))
    for a in alerts:
        if a.get('type') == '$alert_type':
            print(a.get('last_notified_at', ''))
            sys.exit(0)
    print('')
except:
    print('')
" 2>/dev/null || echo "")

    if [ -n "$last_notified" ]; then
        local now_epoch; now_epoch=$(date +%s)
        local notified_epoch; notified_epoch=$(date -d "$last_notified" +%s 2>/dev/null || echo "0")
        local elapsed=$(( (now_epoch - notified_epoch) / 3600 ))
        if [ "$elapsed" -lt "$NOTIFY_COOLDOWN_HOURS" ]; then
            return 0  # Within cooldown — skip terminal delivery
        fi
    fi

    # Determine severity from alert type name
    local severity="WARNING"
    [[ "$alert_type" == *"reached"* ]] && severity="ALERT"

    # Format and deliver via notification library
    local msg
    msg=$(ds01_format_message "$severity" "RESOURCE QUOTA ALERT" "$message_body" "$username")

    # Deliver to terminal (no container fallback — quota alerts are user-level)
    ds01_notify "$username" "" "$msg"

    # Update last_notified_at in the alert JSON entry
    python3 -c "
import json, datetime
ts = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
try:
    with open('$alerts_file') as f:
        alerts = json.load(f)
    for a in alerts:
        if a.get('type') == '$alert_type':
            a['last_notified_at'] = ts
    with open('$alerts_file', 'w') as f:
        json.dump(alerts, f, indent=2)
except:
    pass
" 2>/dev/null || true
}

# ── check_gpu_alerts ──────────────────────────────────────────────────────────
# Check GPU usage for a user and fire/clear alerts as needed.
check_gpu_alerts() {
    local username="$1"

    # Get user's GPU limit
    local max_gpus
    max_gpus=$(python3 "$RESOURCE_PARSER" "$username" --max-gpus 2>/dev/null || echo "")

    # Handle unlimited / unset
    if [ "$max_gpus" = "unlimited" ] || [ "$max_gpus" = "null" ] || [ -z "$max_gpus" ]; then
        return 0
    fi

    # Get current GPU count
    local current_gpus
    current_gpus=$(python3 "$GPU_STATE_READER" user "$username" 2>/dev/null | grep -c "gpu_slot") || current_gpus=0

    # Calculate percentage
    local percent=0
    if [ "$max_gpus" -gt 0 ] 2>/dev/null; then
        percent=$((current_gpus * 100 / max_gpus))
    fi

    # Fire or clear alerts based on threshold
    if [ "$percent" -ge 100 ]; then
        local msg="GPU limit reached: $current_gpus/$max_gpus GPUs allocated"
        add_alert "$username" "gpu_limit_reached" "$msg"
        deliver_alert_to_terminal "$username" "gpu_limit_reached" "$msg"
        log_event "alert.gpu_limit" "$username" "GPU limit reached: $current_gpus/$max_gpus"
    elif [ "$percent" -ge "$SOFT_LIMIT_THRESHOLD" ]; then
        local msg="GPU usage high: $current_gpus/$max_gpus GPUs (${percent}%)"
        add_alert "$username" "gpu_usage_high" "$msg"
        deliver_alert_to_terminal "$username" "gpu_usage_high" "$msg"
        log_event "alert.gpu_warning" "$username" "GPU usage at ${percent}%"
    else
        # Clear GPU alerts when usage drops below threshold
        clear_alert "$username" "gpu_usage_high"
        clear_alert "$username" "gpu_limit_reached"
    fi
}

# ── check_container_alerts ────────────────────────────────────────────────────
# Check container count for a user and fire/clear alerts as needed.
check_container_alerts() {
    local username="$1"

    # Get user's container limit using the correct flag
    local max_containers
    max_containers=$(python3 "$RESOURCE_PARSER" "$username" --max-containers 2>/dev/null || echo "")

    # Handle unlimited / unset
    if [ "$max_containers" = "unlimited" ] || [ "$max_containers" = "null" ] || [ -z "$max_containers" ]; then
        return 0
    fi

    # Get current container count (running only for active quota check)
    local current_containers
    current_containers=$(docker ps -a --filter "label=ds01.user=$username" --format "{{.Names}}" 2>/dev/null | wc -l)
    current_containers=$(echo "$current_containers" | tr -d '[:space:]')

    # Calculate percentage
    local percent=0
    if [ "$max_containers" -gt 0 ] 2>/dev/null; then
        percent=$((current_containers * 100 / max_containers))
    fi

    # Fire or clear alerts based on threshold
    if [ "$percent" -ge 100 ]; then
        local msg="Container limit reached: $current_containers/$max_containers"
        add_alert "$username" "container_limit_reached" "$msg"
        deliver_alert_to_terminal "$username" "container_limit_reached" "$msg"
        log_event "alert.container_limit" "$username" "Container limit reached: $current_containers/$max_containers"
    elif [ "$percent" -ge "$SOFT_LIMIT_THRESHOLD" ]; then
        local msg="Container usage high: $current_containers/$max_containers (${percent}%)"
        add_alert "$username" "container_usage_high" "$msg"
        deliver_alert_to_terminal "$username" "container_usage_high" "$msg"
        log_event "alert.container_warning" "$username" "Container usage at ${percent}%"
    else
        clear_alert "$username" "container_usage_high"
        clear_alert "$username" "container_limit_reached"
    fi
}

# ── check_memory_alerts ───────────────────────────────────────────────────────
# Check memory usage for a user against their cgroup slice and fire/clear alerts.
# Skips users with no memory limit (admin/unlimited).
check_memory_alerts() {
    local username="$1"

    # Get aggregate limits — contains memory_max
    local aggregate_json
    aggregate_json=$(python3 "$RESOURCE_PARSER" "$username" --aggregate 2>/dev/null || echo "")

    # Skip users with no limits configured
    if [ -z "$aggregate_json" ] || [ "$aggregate_json" = "null" ]; then
        return 0
    fi

    # Extract memory_max in bytes from aggregate JSON
    local memory_max_bytes
    memory_max_bytes=$(echo "$aggregate_json" | python3 -c "
import json, sys
d = json.load(sys.stdin)
mem = d.get('memory_max', '')
if not mem or mem in ('None', 'null', 'unlimited', ''):
    print('')
    sys.exit(0)
# Handle values like '16G', '16g', or raw bytes
mem_str = str(mem).strip()
if mem_str.lower().endswith('g'):
    print(int(float(mem_str[:-1]) * 1073741824))
elif mem_str.lower().endswith('m'):
    print(int(float(mem_str[:-1]) * 1048576))
else:
    # Assume raw bytes
    print(int(mem_str))
" 2>/dev/null || echo "")

    # Skip if no memory limit set
    if [ -z "$memory_max_bytes" ] || [ "$memory_max_bytes" = "0" ]; then
        return 0
    fi

    # Get user's group and sanitised username for cgroup path construction
    local user_group
    user_group=$(python3 "$RESOURCE_PARSER" "$username" --group 2>/dev/null || echo "")

    if [ -z "$user_group" ] || [ "$user_group" = "null" ]; then
        return 0
    fi

    local sanitized_user
    sanitized_user=$(python3 -c "
import sys
sys.path.insert(0, '${SCRIPT_DIR}/lib')
from username_utils import sanitize_username_for_slice
print(sanitize_username_for_slice('$username'))
" 2>/dev/null || echo "")

    if [ -z "$sanitized_user" ]; then
        return 0
    fi

    # Read current memory usage from cgroup slice
    local cgroup_path="/sys/fs/cgroup/ds01.slice/ds01-${user_group}.slice/ds01-${user_group}-${sanitized_user}.slice/memory.current"
    if [ ! -f "$cgroup_path" ]; then
        # User slice not active (no running containers) — skip but don't clear alerts
        return 0
    fi

    local current_bytes
    current_bytes=$(cat "$cgroup_path" 2>/dev/null || echo "0")
    current_bytes=$(echo "$current_bytes" | tr -d '[:space:]')

    # Guard against empty or non-numeric reads
    if [ -z "$current_bytes" ] || ! [[ "$current_bytes" =~ ^[0-9]+$ ]]; then
        return 0
    fi

    # Calculate percentage
    local percent
    percent=$(python3 -c "
current = int('$current_bytes')
limit = int('$memory_max_bytes')
if limit > 0:
    print(int(current * 100 / limit))
else:
    print(0)
" 2>/dev/null || echo "0")

    # Human-readable current and max for alert message
    local mem_display
    mem_display=$(python3 -c "
current = int('$current_bytes')
limit = int('$memory_max_bytes')
current_gb = current / (1024**3)
limit_gb = limit / (1024**3)
print(f'{current_gb:.1f}/{limit_gb:.0f} GB')
" 2>/dev/null || echo "${current_bytes}B/${memory_max_bytes}B")

    # Fire or clear alerts based on threshold
    if [ "$percent" -ge 100 ]; then
        local msg="Memory limit reached: ${mem_display} (${percent}%)"
        add_alert "$username" "memory_limit_reached" "$msg"
        deliver_alert_to_terminal "$username" "memory_limit_reached" "$msg"
        log_event "alert.memory_limit" "$username" "Memory limit reached: $mem_display"
    elif [ "$percent" -ge "$SOFT_LIMIT_THRESHOLD" ]; then
        local msg="Memory usage high: ${mem_display} (${percent}%)"
        add_alert "$username" "memory_usage_high" "$msg"
        deliver_alert_to_terminal "$username" "memory_usage_high" "$msg"
        log_event "alert.memory_warning" "$username" "Memory usage at ${percent}%"
    else
        # Clear memory alerts when usage drops below threshold
        clear_alert "$username" "memory_usage_high"
        clear_alert "$username" "memory_limit_reached"
    fi
}

# ── add_alert ─────────────────────────────────────────────────────────────────
# Add or update an alert entry in the user's JSON alert file.
add_alert() {
    local username="$1"
    local alert_type="$2"
    local message="$3"
    local alerts_file="$ALERTS_DIR/${username}.json"
    local timestamp
    timestamp=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

    # Create or update alerts file
    if [ -f "$alerts_file" ]; then
        # Check if this alert type already exists
        if python3 -c "import json; alerts=json.load(open('$alerts_file')); exit(0 if any(a['type']=='$alert_type' for a in alerts) else 1)" 2>/dev/null; then
            # Update existing alert (preserve last_notified_at)
            python3 -c "
import json
with open('$alerts_file', 'r') as f:
    alerts = json.load(f)
for a in alerts:
    if a['type'] == '$alert_type':
        a['message'] = '$message'
        a['updated_at'] = '$timestamp'
        break
with open('$alerts_file', 'w') as f:
    json.dump(alerts, f, indent=2)
" 2>/dev/null
        else
            # Add new alert entry
            python3 -c "
import json
with open('$alerts_file', 'r') as f:
    alerts = json.load(f)
alerts.append({'type': '$alert_type', 'message': '$message', 'created_at': '$timestamp', 'updated_at': '$timestamp'})
with open('$alerts_file', 'w') as f:
    json.dump(alerts, f, indent=2)
" 2>/dev/null
        fi
    else
        # Create new alerts file
        echo "[{\"type\": \"$alert_type\", \"message\": \"$message\", \"created_at\": \"$timestamp\", \"updated_at\": \"$timestamp\"}]" > "$alerts_file"
    fi

    chmod 644 "$alerts_file"
}

# ── clear_alert ───────────────────────────────────────────────────────────────
# Remove a specific alert type from the user's JSON alert file.
clear_alert() {
    local username="$1"
    local alert_type="$2"
    local alerts_file="$ALERTS_DIR/${username}.json"

    if [ -f "$alerts_file" ]; then
        python3 -c "
import json
with open('$alerts_file', 'r') as f:
    alerts = json.load(f)
alerts = [a for a in alerts if a['type'] != '$alert_type']
with open('$alerts_file', 'w') as f:
    json.dump(alerts, f, indent=2)
" 2>/dev/null || true
    fi
}

# ── clean_old_alerts ──────────────────────────────────────────────────────────
# Remove alerts older than ALERT_RETENTION_HOURS from all user files.
clean_old_alerts() {
    local cutoff
    cutoff=$(date -d "-${ALERT_RETENTION_HOURS} hours" +%s 2>/dev/null || date -v-${ALERT_RETENTION_HOURS}H +%s)

    for alerts_file in "$ALERTS_DIR"/*.json; do
        [ -f "$alerts_file" ] || continue

        python3 -c "
import json
import datetime
cutoff = datetime.datetime.utcfromtimestamp($cutoff)
with open('$alerts_file', 'r') as f:
    alerts = json.load(f)
alerts = [a for a in alerts if datetime.datetime.fromisoformat(a['updated_at'].replace('Z', '+00:00').replace('+00:00', '')) > cutoff]
with open('$alerts_file', 'w') as f:
    json.dump(alerts, f, indent=2)
" 2>/dev/null || true

        # Remove empty alert files
        if [ "$(cat "$alerts_file" 2>/dev/null)" = "[]" ]; then
            rm -f "$alerts_file"
        fi
    done
}

# ── check_user ────────────────────────────────────────────────────────────────
# Check all resource quota alerts for a specific user.
# Skips admin/unlimited users who have no limits configured.
check_user() {
    local username="$1"

    # Skip users with no resource limits (admin/unlimited) — check group first
    local user_group
    user_group=$(python3 "$RESOURCE_PARSER" "$username" --group 2>/dev/null || echo "")

    local aggregate_json
    aggregate_json=$(python3 "$RESOURCE_PARSER" "$username" --aggregate 2>/dev/null || echo "")

    # If group is admin or aggregate is null, no limits to check
    if [ "$user_group" = "admin" ] || [ -z "$aggregate_json" ] || [ "$aggregate_json" = "null" ]; then
        # Still check GPU since it uses --max-gpus separately
        check_gpu_alerts "$username"
        return 0
    fi

    check_gpu_alerts "$username"
    check_memory_alerts "$username"
    check_container_alerts "$username"
}

# ── main ──────────────────────────────────────────────────────────────────────
main() {
    case "${1:-}" in
        --clean)
            log_event "maintenance.alert_clean" "system" "Cleaning old alerts"
            clean_old_alerts
            ;;
        --help|-h)
            echo "Usage: $0 [username|--clean]"
            echo ""
            echo "Options:"
            echo "  <username>  Check alerts for specific user"
            echo "  --clean     Remove alerts older than ${ALERT_RETENTION_HOURS}h"
            echo "  (no args)   Check all DS01 users"
            ;;
        "")
            # Check all users
            log_event "maintenance.alert_check_start" "system" "Starting resource alert check for all users"
            clean_old_alerts

            local user_count=0
            for username in $(get_ds01_users); do
                [ -n "$username" ] || continue
                check_user "$username"
                ((user_count++)) || true
            done

            log_event "maintenance.alert_check_done" "system" "Completed resource alert check: $user_count user(s)"
            ;;
        *)
            # Check specific user
            log_event "maintenance.alert_check_user" "$1" "Checking resource alerts for user: $1"
            check_user "$1"

            local alerts_file="$ALERTS_DIR/${1}.json"
            if [ -f "$alerts_file" ]; then
                local alert_count
                alert_count=$(python3 -c "import json; print(len(json.load(open('$alerts_file'))))" 2>/dev/null || echo "0")
                if [ "$alert_count" -gt 0 ]; then
                    echo "Created $alert_count alert(s) for $1"
                    echo "Alerts file: $alerts_file"
                else
                    echo "No alerts needed for $1 (usage below threshold)"
                fi
            else
                echo "No alerts needed for $1 (usage below threshold)"
            fi
            ;;
    esac
}

main "$@"
