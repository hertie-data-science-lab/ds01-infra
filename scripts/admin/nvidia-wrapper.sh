#!/bin/bash
# /opt/ds01-infra/scripts/admin/nvidia-wrapper.sh
# DS01 NVIDIA Command Wrapper - Bare Metal GPU Access Control
#
# This wrapper intercepts all nvidia-* commands and enforces video group membership.
# Deployed to /usr/local/bin/nvidia-smi, nvidia-settings, etc. (higher precedence than /usr/bin)
#
# Usage:
#   Automatically invoked when user runs: nvidia-smi, nvidia-settings, nvidia-debugdump, etc.
#   Checks if user is in 'video' group:
#     - If YES: passes through to real command in /usr/bin
#     - If NO: shows helpful error message and exits 1
#
# Installation:
#   For each nvidia command: cp nvidia-wrapper.sh /usr/local/bin/nvidia-<cmd>
#   deploy.sh handles this automatically.

set -euo pipefail

# ============================================================================
# Configuration
# ============================================================================

INFRA_ROOT="/opt/ds01-infra"
EVENTS_LIB="$INFRA_ROOT/scripts/lib/ds01_events.sh"
RATE_LIMIT_DIR="/var/lib/ds01/rate-limits"
RATE_LIMIT_WINDOW=3600  # 1 hour in seconds
RATE_LIMIT_MAX=10       # Max 10 denials per user per hour

# Determine the real binary path from our name
REAL_CMD="/usr/bin/$(basename "$0")"

# Get current user
CURRENT_USER=$(whoami)
CURRENT_UID=$(id -u)

# Source event logging library (best-effort)
if [ -f "$EVENTS_LIB" ]; then
    source "$EVENTS_LIB" 2>/dev/null || true
fi

# ============================================================================
# Rate Limiting for Denial Logs
# ============================================================================

check_rate_limit() {
    local user="$1"

    # Create rate limit directory if needed
    mkdir -p "$RATE_LIMIT_DIR" 2>/dev/null || return 0

    local state_file="$RATE_LIMIT_DIR/nvidia-denials-${user}.state"
    local now=$(date +%s)
    local window_start=$((now - RATE_LIMIT_WINDOW))
    local count=0

    # Read existing state if available
    if [ -f "$state_file" ]; then
        # Filter out old entries and count recent ones
        while IFS= read -r timestamp; do
            if [ "$timestamp" -ge "$window_start" ]; then
                count=$((count + 1))
            fi
        done < "$state_file"

        # Prune old entries
        (awk -v cutoff="$window_start" '$1 >= cutoff' "$state_file" > "${state_file}.tmp") 2>/dev/null || true
        mv "${state_file}.tmp" "$state_file" 2>/dev/null || true
    fi

    # Check if under limit
    if [ "$count" -lt "$RATE_LIMIT_MAX" ]; then
        # Record this denial (subshell suppresses shell redirection errors)
        (echo "$now" >> "$state_file") 2>/dev/null || true
        return 0  # Allow logging
    else
        return 1  # Suppress logging (rate limit exceeded)
    fi
}

# ============================================================================
# Access Control Check
# ============================================================================

# Check if user is admin (root or ds01-admin group)
is_admin() {
    # Root always passes
    [ "$CURRENT_UID" -eq 0 ] && return 0

    # Check ds01-admin group membership
    groups "$CURRENT_USER" 2>/dev/null | grep -qE '\bds01-admin\b'
}

# Check if user is in video group
is_in_video_group() {
    groups "$CURRENT_USER" 2>/dev/null | grep -q '\bvideo\b'
}

# Show contextual error message
show_access_denied() {
    local cmd_name
    cmd_name=$(basename "$0")

    echo "" >&2
    echo -e "\033[0;31m+------------------------------------------------------------+\033[0m" >&2
    echo -e "\033[0;31m|\033[0m  \033[1mBare Metal GPU Access Restricted\033[0m                         \033[0;31m|\033[0m" >&2
    echo -e "\033[0;31m+------------------------------------------------------------+\033[0m" >&2
    echo "" >&2
    echo "  This server uses container-only GPU access by default." >&2
    echo "" >&2
    echo -e "  \033[1mTo use GPUs, create a container:\033[0m" >&2
    echo "    container deploy my-project" >&2
    echo "" >&2
    echo -e "  \033[1mCheck your access status:\033[0m" >&2
    echo "    bare-metal-access status" >&2
    echo "" >&2
    echo "  Need temporary access? Raise a ticket:" >&2
    echo "    https://github.com/hertie-data-science-lab/ds01-hub/issues" >&2
    echo "" >&2
    echo "  Note: Access changes require a new SSH session to take effect." >&2
    echo "" >&2
}

# ============================================================================
# Main Logic
# ============================================================================

# Admins always pass through
if is_admin; then
    exec "$REAL_CMD" "$@"
fi

# Check video group membership
if ! is_in_video_group; then
    # Access denied - show error
    show_access_denied

    # Log denial event (rate-limited, best-effort)
    if check_rate_limit "$CURRENT_USER"; then
        # Log to syslog at auth.warning level
        logger -p auth.warning -t "ds01-nvidia-wrapper" \
            "Bare metal GPU access denied for user $CURRENT_USER (command: $(basename "$0"))" 2>/dev/null || true

        # Log to DS01 events (best-effort)
        if command -v log_event &>/dev/null; then
            log_event "auth.denied" "$CURRENT_USER" "nvidia-wrapper" \
                command="$(basename "$0")" \
                reason="not_in_video_group" || true
        fi
    fi

    exit 1
fi

# User is in video group - pass through to real command
exec "$REAL_CMD" "$@"
