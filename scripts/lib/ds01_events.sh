#!/bin/bash
# /opt/ds01-infra/scripts/lib/ds01_events.sh
# Bash wrapper for DS01 event logging
#
# This provides a bash-friendly interface to the Python event logging library.
# Events are written in the same standardised JSON format to /var/log/ds01/events.jsonl
#
# Usage:
#   source /opt/ds01-infra/scripts/lib/ds01_events.sh
#   log_event <event_type> [user] [source] [key=value ...]
#
# Arguments:
#   event_type - Required. Dot-separated event category.action (e.g., "container.create")
#   user       - Optional. Username (use empty string "" to omit)
#   source     - Optional. Source component (defaults to calling script basename)
#   key=value  - Optional. Additional detail fields
#
# Examples:
#   log_event "container.create" "alice" "docker-wrapper" container=proj image=pytorch
#   log_event "system.startup" "" "" component=monitoring
#   log_event "gpu.allocate" "$USER" "" gpu=0:1 priority=50
#
# The function never causes the calling script to exit on failure.
# Errors are suppressed and logged to stderr only.

# ============================================================================
# Main Event Logging Function
# ============================================================================

log_event() {
    local event_type="$1"
    local user="${2:-}"
    local source="${3:-}"
    shift 3 2>/dev/null || shift $# # Remove first 3 args, or all if fewer than 3

    # If no source provided, use basename of calling script
    if [ -z "$source" ]; then
        # Use BASH_SOURCE[1] to get the script that called log_event, not this library
        if [ -n "${BASH_SOURCE[1]}" ]; then
            source=$(basename "${BASH_SOURCE[1]}")
        else
            source=$(basename "$0")
        fi
    fi

    # Build arguments for Python CLI
    local args=("$event_type")

    # Add user if provided and non-empty
    if [ -n "$user" ]; then
        args+=("user=$user")
    fi

    # Add source if provided and non-empty
    if [ -n "$source" ]; then
        args+=("source=$source")
    fi

    # Add all remaining key=value pairs
    args+=("$@")

    # Call Python event logger in subshell to prevent script exit on error
    # Suppress errors to avoid breaking calling script (even with set -e)
    (
        python3 /opt/ds01-infra/scripts/lib/ds01_events.py log "${args[@]}" 2>/dev/null
    ) || true

    # Always return success so set -e scripts don't exit
    return 0
}
