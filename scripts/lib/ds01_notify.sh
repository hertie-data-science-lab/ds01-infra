#!/bin/bash
# /opt/ds01-infra/scripts/lib/ds01_notify.sh
# DS01 Shared Notification Library
#
# Centralised notification primitives for all Phase 8 scripts.
# Provides TTY delivery, container-file fallback, unified message
# formatting with bordered box, and per-user quota summary.
#
# Usage:
#   source /opt/ds01-infra/scripts/lib/ds01_notify.sh
#
# Public functions:
#   ds01_notify           <username> <container_name> <message>
#   ds01_notify_container <container_name> <message>
#   ds01_format_message   <severity> <title> <body> <username>
#   ds01_quota_summary    <username>

# Idempotent guard — safe to source multiple times
[ -n "${_DS01_NOTIFY_LOADED:-}" ] && return 0
_DS01_NOTIFY_LOADED=1

# ── Bootstrap: source init.sh for standard paths and colours ─────────────────

_DS01_NOTIFY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ -z "${DS01_ROOT:-}" ]; then
    source "${_DS01_NOTIFY_DIR}/init.sh"
fi

# ── Internal helpers ──────────────────────────────────────────────────────────

_ds01_notify_log() {
    # Diagnostic messages go to stderr, never stdout
    echo "[ds01_notify] $*" >&2
}

# ── ds01_notify ───────────────────────────────────────────────────────────────
# Send message to a specific user's active terminal(s).
# Falls back to container-file write if no terminals and container is known.
#
# Usage: ds01_notify <username> <container_name> <message>
#   container_name  Name of container for fallback; pass "" if no container context
ds01_notify() {
    local username="$1"
    local container_name="$2"
    local message="$3"
    local delivered=false

    # Primary: write to each TTY the user has open via who | awk
    while IFS= read -r tty; do
        [ -z "$tty" ] && continue
        echo "$message" > "/dev/$tty" 2>/dev/null && delivered=true
    done < <(who | awk -v user="$username" '$1 == user {print $2}')

    if [ "$delivered" = false ]; then
        if [ -n "$container_name" ]; then
            # Fallback: write to container alert file
            ds01_notify_container "$container_name" "$message"
        else
            _ds01_notify_log "User $username has no active terminals — notification not delivered"
        fi
    fi
}

# ── ds01_notify_container ─────────────────────────────────────────────────────
# Write alert as plain text to /workspace/.ds01-alerts inside container.
# Best-effort only — always succeeds even if container is stopping.
#
# Usage: ds01_notify_container <container_name> <message>
ds01_notify_container() {
    local container_name="$1"
    local message="$2"
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    # Append separator, message, and blank line to alert file inside container.
    # Pass message via -e to avoid shell quoting issues with arbitrary content.
    docker exec -e "DS01_MSG=${message}" "$container_name" bash -c \
        'printf "%s\n%s\n\n" "--- Alert: '"${timestamp}"' ---" "$DS01_MSG" \
         >> /workspace/.ds01-alerts' \
        2>/dev/null || true
}

# ── ds01_quota_summary ────────────────────────────────────────────────────────
# Build a multi-line quota summary for a user.
# Results are cached per-process in _DS01_QUOTA_CACHE_<sanitized_user>
# to avoid repeated Python calls when notifying multiple containers.
#
# Usage:  ds01_quota_summary <username>
# Output: multi-line text, e.g.
#           GPUs: 1/3 | Memory: 4.2/16 GB | Containers: 1/3
#         Returns empty string on any failure (never fatal).
ds01_quota_summary() {
    local username="$1"
    # Sanitise for use as shell variable name (strip domain, replace non-alnum)
    local safe_user
    safe_user=$(echo "$username" | sed 's/@.*//;s/[^a-zA-Z0-9]/_/g')
    local cache_var="_DS01_QUOTA_CACHE_${safe_user}"

    # Return cached value if already computed this run
    if [ -n "${!cache_var+x}" ]; then
        echo "${!cache_var}"
        return 0
    fi

    local resource_parser="${DS01_SCRIPTS}/docker/get_resource_limits.py"

    # ── GPU ──────────────────────────────────────────────────────────────────
    local max_gpus current_gpus gpu_display
    max_gpus=$(python3 "$resource_parser" "$username" --max-gpus 2>/dev/null || echo "")

    if [ -n "$max_gpus" ] && [ "$max_gpus" != "null" ]; then
        # Count currently allocated GPUs from docker ps label filter
        current_gpus=$(docker ps --filter "label=ds01.user=$username" \
            --format '{{.Names}}' 2>/dev/null | wc -l)
        current_gpus=$(echo "$current_gpus" | tr -d '[:space:]')

        if [ "$max_gpus" = "unlimited" ]; then
            gpu_display="GPUs: ${current_gpus}/unlimited"
        else
            gpu_display="GPUs: ${current_gpus}/${max_gpus}"
        fi
    else
        gpu_display=""
    fi

    # ── Memory ───────────────────────────────────────────────────────────────
    local memory_display=""
    local aggregate_json
    aggregate_json=$(python3 "$resource_parser" "$username" --aggregate 2>/dev/null || echo "")

    if [ -n "$aggregate_json" ] && [ "$aggregate_json" != "null" ]; then
        local memory_max_bytes current_memory_bytes
        memory_max_bytes=$(echo "$aggregate_json" | python3 -c \
            "import json,sys; d=json.load(sys.stdin); print(d.get('memory_max',''))" \
            2>/dev/null || echo "")

        if [ -n "$memory_max_bytes" ] && [ "$memory_max_bytes" != "None" ] && [ "$memory_max_bytes" != "null" ]; then
            # Get user's group for slice name, then read cgroup memory.current
            local user_group sanitized_user cgroup_path current_memory_bytes_raw
            user_group=$(python3 "$resource_parser" "$username" --group 2>/dev/null || echo "")
            sanitized_user=$(python3 -c \
                "import sys; sys.path.insert(0,'${DS01_SCRIPTS}/lib'); \
                 from username_utils import sanitize_username_for_slice; \
                 print(sanitize_username_for_slice('$username'))" \
                2>/dev/null || echo "$safe_user")

            if [ -n "$user_group" ] && [ "$user_group" != "null" ]; then
                cgroup_path="/sys/fs/cgroup/ds01.slice/ds01-${user_group}.slice/ds01-${user_group}-${sanitized_user}.slice/memory.current"
                current_memory_bytes_raw=$(cat "$cgroup_path" 2>/dev/null || echo "0")
            else
                current_memory_bytes_raw="0"
            fi

            memory_display=$(python3 -c "
current = int('${current_memory_bytes_raw}' or 0)
limit = int('${memory_max_bytes}' or 0)
if limit > 0:
    current_gb = current / (1024**3)
    limit_gb = limit / (1024**3)
    print(f'Memory: {current_gb:.1f}/{limit_gb:.0f} GB')
" 2>/dev/null || echo "")
        fi
    fi

    # ── Containers ────────────────────────────────────────────────────────────
    local container_display=""
    local max_containers current_containers
    max_containers=$(python3 "$resource_parser" "$username" --max-containers 2>/dev/null || echo "")

    if [ -n "$max_containers" ] && [ "$max_containers" != "null" ]; then
        current_containers=$(docker ps \
            --filter "label=ds01.user=$username" \
            --format '{{.Names}}' 2>/dev/null | wc -l || echo "0")
        current_containers=$(echo "$current_containers" | tr -d '[:space:]')

        if [ "$max_containers" = "unlimited" ]; then
            container_display="Containers: ${current_containers}/unlimited"
        else
            container_display="Containers: ${current_containers}/${max_containers}"
        fi
    fi

    # ── Assemble summary ──────────────────────────────────────────────────────
    local parts=()
    [ -n "$gpu_display" ]       && parts+=("$gpu_display")
    [ -n "$memory_display" ]    && parts+=("$memory_display")
    [ -n "$container_display" ] && parts+=("$container_display")

    local summary=""
    if [ "${#parts[@]}" -gt 0 ]; then
        summary="  $(IFS=' | '; echo "${parts[*]}")"
    fi

    # Cache and return
    printf -v "$cache_var" '%s' "$summary"
    echo "$summary"
}

# ── ds01_format_message ───────────────────────────────────────────────────────
# Format a notification message with a bordered box, severity header,
# and quota summary appended.
#
# Usage: ds01_format_message <severity> <title> <body> <username>
#
# Severity labels:
#   WARNING  — approaching a limit (recoverable)
#   ALERT    — at limit or blocked
#   STOPPED  — container was just stopped
#   NOTICE   — informational / exempt user
#
# Output is a plain-text string suitable for writing to a TTY or file.
ds01_format_message() {
    local severity="$1"
    local title="$2"
    local body="$3"
    local username="$4"

    local border="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

    # Quota summary — omit block if empty (avoids blank section)
    local quota_summary
    quota_summary=$(ds01_quota_summary "$username" 2>/dev/null || echo "")

    local quota_section=""
    if [ -n "$quota_summary" ]; then
        quota_section="
Your resource quotas:
${quota_summary}"
    fi

    cat <<EOF
${border}
[${severity}] ${title}

${body}
${quota_section}
${border}
EOF
}
