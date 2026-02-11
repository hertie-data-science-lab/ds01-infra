#!/bin/bash
# /opt/ds01-infra/scripts/docker/docker-wrapper.sh
# DS01 Docker Wrapper - Universal Container Management
#
# Phase A+B+C: Cgroup injection + Owner labels + GPU allocation (Jan 2026)
# Phase 03-02: Container isolation enforcement (Jan 2026)
#
# This wrapper intercepts Docker commands and:
# - Injects per-user cgroup-parent for resource limits
# - Injects owner labels (ds01.user, ds01.managed, ds01.container_type)
# - Intercepts GPU requests and routes through ds01 allocation
# - Rewrites --gpus all to specific allocated device
# - Enforces user GPU quotas
# - Filters container lists (docker ps) to show only own containers
# - Verifies ownership for all container-targeting operations
# - Prevents cross-user container access
#
# Installation: Copy to /usr/local/bin/docker (takes precedence over /usr/bin/docker)
#
# GPU ACCESS RULES:
# - GPU containers are EPHEMERAL (idle timeout + max runtime enforced)
# - Non-GPU containers can be PERMANENT (no restrictions)
# - All containers are tracked regardless of launch method
#
# ACCESS CONTROL:
# - Non-admin users can only see and manage their own containers
# - Admin (root, datasciencelab, ds01-admin group) has full access
# - Cross-user operations denied with helpful error message
# - Unowned containers allowed (fail-open) with warning log
# - Rate-limited denial logging (max 10/hour per user)
#
# FAIL-OPEN MODES:
# - DS01_WRAPPER_BYPASS=1: Skip all wrapper logic (emergency)
# - DS01_ISOLATION_MODE=disabled: No isolation enforcement
# - DS01_ISOLATION_MODE=monitoring: Log denials but allow operations
# - Unowned containers: Allow with warning (prevent blocking legacy containers)
#
# DEBUG MODES:
# - DS01_WRAPPER_DEBUG=1: Log interceptions (denials, filtering, ownership checks)
# - DS01_WRAPPER_DEBUG=2: Log all docker invocations
#
# How it works:
# 1. Intercepts 'docker run' and 'docker create' commands
# 2. Detects if container requests GPU access (--gpus flag)
# 3. If GPU requested: allocates from pool, rewrites --gpus to specific device
# 4. Extracts user's group from resource-limits.yaml
# 5. Ensures user's slice exists (ds01-{group}-{user}.slice)
# 6. Injects --cgroup-parent if not already specified
# 7. Injects ownership and type labels
# 8. Filters container lists for non-admins
# 9. Verifies ownership for container-targeting operations
# 10. Passes through to real Docker binary

# Real Docker binary
REAL_DOCKER="/usr/bin/docker"

# DS01 paths
INFRA_ROOT="/opt/ds01-infra"
CONFIG_FILE="$INFRA_ROOT/config/runtime/resource-limits.yaml"
RESOURCE_PARSER="$INFRA_ROOT/scripts/docker/get_resource_limits.py"
GPU_ALLOCATOR="$INFRA_ROOT/scripts/docker/gpu_allocator_v2.py"
CREATE_SLICE="$INFRA_ROOT/scripts/system/create-user-slice.sh"
USERNAME_UTILS="$INFRA_ROOT/scripts/lib/username-utils.sh"
LOG_FILE="/var/log/ds01/docker-wrapper.log"

# GPU allocation settings
GPU_ALLOCATION_TIMEOUT=180  # 3 minutes
GPU_ALLOCATION_RETRY_INTERVAL=10  # seconds

# Source username sanitization library (fail silently if not available)
if [ -f "$USERNAME_UTILS" ]; then
    source "$USERNAME_UTILS"
else
    # Fallback: simple sanitization if library not available
    sanitize_username_for_slice() {
        echo "$1" | sed 's/@/-at-/g; s/\./-/g; s/[^a-zA-Z0-9_:-]/-/g; s/--*/-/g; s/^-//; s/-$//'
    }
fi

# Source event logging library
EVENTS_LIB="$INFRA_ROOT/scripts/lib/ds01_events.sh"
if [ -f "$EVENTS_LIB" ]; then
    source "$EVENTS_LIB"
fi

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true

# Log function (silent unless DS01_WRAPPER_DEBUG=1 or DEBUG_DS01_WRAPPER=1)
log_debug() {
    local level="${DS01_WRAPPER_DEBUG:-${DEBUG_DS01_WRAPPER:-0}}"
    # Level 1: Log interceptions (denials, filter injections, ownership checks)
    # Level 2: Log all invocations (every docker command)
    if [ "$level" -ge "1" ]; then
        echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" >> "$LOG_FILE" 2>/dev/null || true
    fi
}

# Get current user info
CURRENT_USER=$(whoami)
CURRENT_UID=$(id -u)

# Check if this is a 'run' or 'create' command that needs cgroup injection
needs_cgroup_injection() {
    local cmd="$1"
    # Only inject for 'run' and 'create' subcommands
    [[ "$cmd" == "run" ]] || [[ "$cmd" == "create" ]]
}

# Check if --cgroup-parent is already specified
has_cgroup_parent() {
    for arg in "$@"; do
        case "$arg" in
            --cgroup-parent=*|--cgroup-parent)
                return 0
                ;;
        esac
    done
    return 1
}

# Check if ds01.user label is already specified in args
has_owner_label() {
    local prev_arg=""
    for arg in "$@"; do
        # Check for --label=ds01.user=*
        if [[ "$arg" == "--label=ds01.user="* ]]; then
            return 0
        fi
        # Check for --label ds01.user=* (two separate args)
        if [[ "$prev_arg" == "--label" ]] && [[ "$arg" == "ds01.user="* ]]; then
            return 0
        fi
        prev_arg="$arg"
    done
    return 1
}

# Extract owner from devcontainer.local_folder label if present
# VS Code dev containers set this label to the project path: /home/USER/...
get_devcontainer_owner() {
    local prev_arg=""
    for arg in "$@"; do
        # Check for --label=devcontainer.local_folder=/home/USER/...
        if [[ "$arg" == "--label=devcontainer.local_folder=/home/"* ]]; then
            local path="${arg#--label=devcontainer.local_folder=}"
            echo "$path" | cut -d/ -f3
            return 0
        fi
        # Check for --label devcontainer.local_folder=/home/USER/... (two separate args)
        if [[ "$prev_arg" == "--label" ]] && [[ "$arg" == "devcontainer.local_folder=/home/"* ]]; then
            local path="${arg#devcontainer.local_folder=}"
            echo "$path" | cut -d/ -f3
            return 0
        fi
        prev_arg="$arg"
    done
    return 1
}

# ============================================================================
# PHASE 1: GPU AND CONTAINER TYPE DETECTION
# ============================================================================

# Check if container requests GPU access
has_gpu_request() {
    for arg in "$@"; do
        case "$arg" in
            --gpus|--gpus=*|--runtime=nvidia|--device=*nvidia*)
                return 0
                ;;
        esac
    done
    return 1
}

# Check for a specific label pattern in args
has_label_pattern() {
    local pattern="$1"
    shift
    local prev_arg=""
    for arg in "$@"; do
        # Check for --label=pattern
        if [[ "$arg" == "--label=$pattern"* ]] || [[ "$arg" == "--label="*"$pattern"* ]]; then
            return 0
        fi
        # Check for --label pattern (two separate args)
        if [[ "$prev_arg" == "--label" ]] && [[ "$arg" == "$pattern"* || "$arg" == *"$pattern"* ]]; then
            return 0
        fi
        prev_arg="$arg"
    done
    return 1
}

# Detect container type from docker args
# Returns: orchestration, atomic, devcontainer, compose, docker
detect_container_type() {
    # Check for explicit ds01.interface label (highest priority)
    local prev_arg=""
    for arg in "$@"; do
        if [[ "$arg" == "--label=ds01.interface="* ]]; then
            echo "${arg#--label=ds01.interface=}"
            return
        fi
        if [[ "$prev_arg" == "--label" ]] && [[ "$arg" == "ds01.interface="* ]]; then
            echo "${arg#ds01.interface=}"
            return
        fi
        prev_arg="$arg"
    done

    # Check for devcontainer labels
    if has_label_pattern "devcontainer." "$@"; then
        echo "devcontainer"
        return
    fi

    # Check for compose labels
    if has_label_pattern "com.docker.compose" "$@"; then
        echo "compose"
        return
    fi

    # Check for ds01.managed label (atomic interface)
    if has_label_pattern "ds01.managed" "$@"; then
        echo "atomic"
        return
    fi

    # Default: direct docker command
    echo "docker"
}

# Extract the GPU request value (e.g., "all", "1", "device=GPU-xxx")
get_gpu_request_value() {
    local prev_arg=""
    for arg in "$@"; do
        case "$arg" in
            --gpus=*)
                echo "${arg#--gpus=}"
                return 0
                ;;
            --gpus)
                # Next arg is the value
                prev_arg="--gpus"
                continue
                ;;
        esac
        if [[ "$prev_arg" == "--gpus" ]]; then
            echo "$arg"
            return 0
        fi
        prev_arg="$arg"
    done
    echo ""
    return 1
}

# ============================================================================
# PHASE 2: GPU ALLOCATION AND ARGUMENT REWRITING
# ============================================================================

# Display GPU container notice to user
show_gpu_notice() {
    local gpu_device="$1"
    local container_type="$2"
    local idle_timeout="$3"
    local max_runtime="$4"

    # Only show in interactive mode (TTY attached)
    if [ -t 1 ]; then
        echo "" >&2
        echo "┌─────────────────────────────────────────────────────────────────┐" >&2
        echo "│  DS01 GPU Container Notice                                       │" >&2
        echo "├─────────────────────────────────────────────────────────────────┤" >&2
        echo "│                                                                  │" >&2
        printf "│  Allocated GPU: %-46s │\n" "$gpu_device" >&2
        echo "│                                                                  │" >&2
        echo "│  IMPORTANT: GPU containers are ephemeral:                        │" >&2
        printf "│  • Idle timeout: %-44s │\n" "$idle_timeout of GPU inactivity → auto-stop" >&2
        printf "│  • Max runtime: %-45s │\n" "$max_runtime → auto-stop" >&2
        echo "│                                                                  │" >&2
        echo "│  Save work to mounted volumes (/home/\$USER/).                   │" >&2
        echo "│                                                                  │" >&2
        echo "└─────────────────────────────────────────────────────────────────┘" >&2
        echo "" >&2
    fi
}

# Show GPU allocation error
show_gpu_error() {
    local error_type="$1"
    local details="$2"

    echo "" >&2
    echo "┌─────────────────────────────────────────────────────────────────┐" >&2
    echo "│  DS01 GPU Allocation Failed                                      │" >&2
    echo "├─────────────────────────────────────────────────────────────────┤" >&2

    case "$error_type" in
        QUOTA_EXCEEDED)
            echo "│                                                                  │" >&2
            echo "│  You have reached your GPU quota limit.                          │" >&2
            echo "│                                                                  │" >&2
            printf "│  %-64s │\n" "$details" >&2
            echo "│                                                                  │" >&2
            echo "│  To free up quota:                                               │" >&2
            echo "│    • Stop an existing container: docker stop <name>              │" >&2
            echo "│    • Check your containers: docker ps                            │" >&2
            ;;
        TIMEOUT)
            echo "│                                                                  │" >&2
            echo "│  No GPU available after waiting 3 minutes.                       │" >&2
            echo "│                                                                  │" >&2
            echo "│  All GPUs are currently allocated to other users.                │" >&2
            echo "│                                                                  │" >&2
            echo "│  Suggestions:                                                    │" >&2
            echo "│    • Try again later                                             │" >&2
            echo "│    • Check GPU status: gpu-status                                │" >&2
            echo "│    • System cleanup runs every 30 minutes                        │" >&2
            ;;
        *)
            printf "│  Error: %-56s │\n" "$error_type" >&2
            if [ -n "$details" ]; then
                printf "│  %-64s │\n" "$details" >&2
            fi
            ;;
    esac

    echo "│                                                                  │" >&2
    echo "└─────────────────────────────────────────────────────────────────┘" >&2
    echo "" >&2
}

# Attempt GPU allocation with blocking retry
# Returns: GPU device UUID on success, empty on failure
# Sets: GPU_ALLOC_ERROR with error type if failed
allocate_gpu_for_container() {
    local user="$1"
    local container_type="$2"

    local start_time=$(date +%s)
    local attempt=0
    local max_attempts=$((GPU_ALLOCATION_TIMEOUT / GPU_ALLOCATION_RETRY_INTERVAL))

    log_debug "Starting GPU allocation for user=$user type=$container_type"

    while true; do
        attempt=$((attempt + 1))
        local elapsed=$(($(date +%s) - start_time))

        # Check timeout
        if [ $elapsed -ge $GPU_ALLOCATION_TIMEOUT ]; then
            GPU_ALLOC_ERROR="TIMEOUT"
            log_debug "GPU allocation timeout after ${elapsed}s"
            return 1
        fi

        # Call the allocator
        local result
        result=$(python3 "$GPU_ALLOCATOR" allocate-external "$user" "$container_type" 2>&1)
        local exit_code=$?

        log_debug "Allocation attempt $attempt: exit=$exit_code result=$result"

        # Parse result
        if [ $exit_code -eq 0 ]; then
            # Success - extract GPU UUID
            local gpu_uuid
            gpu_uuid=$(echo "$result" | grep -oP 'DOCKER_ID=\K[^\s]+' || echo "$result" | grep -oP 'GPU-[a-f0-9-]+|MIG-[a-f0-9-]+')
            if [ -n "$gpu_uuid" ]; then
                log_debug "GPU allocated: $gpu_uuid"
                echo "$gpu_uuid"
                return 0
            fi
        fi

        # Check for quota exceeded (immediate fail, no retry)
        if echo "$result" | grep -q "QUOTA_EXCEEDED\|USER_AT_LIMIT"; then
            GPU_ALLOC_ERROR="QUOTA_EXCEEDED"
            GPU_ALLOC_DETAILS=$(echo "$result" | grep -oP '\(\K[^)]+' | head -1)
            log_debug "Quota exceeded: $GPU_ALLOC_DETAILS"
            return 1
        fi

        # Show waiting message (only first time and every 30 seconds)
        if [ $attempt -eq 1 ] || [ $((elapsed % 30)) -lt $GPU_ALLOCATION_RETRY_INTERVAL ]; then
            local remaining=$((GPU_ALLOCATION_TIMEOUT - elapsed))
            echo "Waiting for GPU availability... (${remaining}s remaining, attempt $attempt)" >&2
        fi

        # Wait before retry
        sleep $GPU_ALLOCATION_RETRY_INTERVAL
    done
}

# Rewrite docker args to replace --gpus with allocated device
rewrite_gpu_args() {
    local gpu_uuid="$1"
    shift

    local args=()
    local skip_next=false

    for arg in "$@"; do
        if $skip_next; then
            skip_next=false
            continue
        fi

        case "$arg" in
            --gpus=*)
                # Replace with specific device
                args+=("--gpus" "\"device=$gpu_uuid\"")
                ;;
            --gpus)
                # Skip this and the next arg (the value)
                skip_next=true
                args+=("--gpus" "\"device=$gpu_uuid\"")
                ;;
            *)
                args+=("$arg")
                ;;
        esac
    done

    echo "${args[@]}"
}

# Get idle timeout for container type
get_container_type_timeout() {
    local container_type="$1"

    case "$container_type" in
        orchestration|atomic)
            # Use user's configured timeout
            echo "30m"
            ;;
        devcontainer)
            echo "30m"
            ;;
        compose)
            echo "30m"
            ;;
        docker)
            echo "30m"
            ;;
        *)
            echo "15m"
            ;;
    esac
}

# Get max runtime for container type
get_container_type_max_runtime() {
    local container_type="$1"

    case "$container_type" in
        orchestration|atomic)
            echo "24h"
            ;;
        devcontainer)
            echo "168h"
            ;;
        compose)
            echo "72h"
            ;;
        docker)
            echo "48h"
            ;;
        *)
            echo "24h"
            ;;
    esac
}

# Get user's group from resource-limits.yaml
get_user_group() {
    local user="$1"

    if [ -f "$RESOURCE_PARSER" ] && [ -f "$CONFIG_FILE" ]; then
        python3 "$RESOURCE_PARSER" "$user" --group 2>/dev/null || echo "student"
    else
        echo "student"
    fi
}

# Ensure user slice exists
ensure_user_slice() {
    local group="$1"
    local user="$2"

    if [ -f "$CREATE_SLICE" ]; then
        # Try to create slice (requires sudo, will fail silently if not root)
        # The slice creation is idempotent - exits 0 if already exists
        sudo "$CREATE_SLICE" "$group" "$user" 2>/dev/null || true
    fi
}

# Check aggregate resource quota before container creation
# Returns 0 (allow) or 1 (deny)
# FAIL-OPEN: Infrastructure errors never block container creation
check_aggregate_quota() {
    local user="$1"

    # Admin bypass - check early
    if is_admin; then
        log_debug "Admin bypass: no aggregate quota check for $user"
        return 0
    fi

    # Get aggregate limits for this user
    local aggregate_limits
    aggregate_limits=$(python3 "$RESOURCE_PARSER" "$user" --aggregate 2>/dev/null)
    local limits_exit=$?

    # FAIL-OPEN: If we can't read limits, allow (infrastructure issue)
    if [ $limits_exit -ne 0 ]; then
        log_debug "FAIL-OPEN: Could not read aggregate limits for $user (allowing)"
        return 0
    fi

    # Check if limits are null (admin/unconfigured)
    if [ "$aggregate_limits" = "null" ] || [ -z "$aggregate_limits" ]; then
        log_debug "No aggregate limits for $user (unlimited or admin)"
        return 0
    fi

    # Parse aggregate limits JSON
    local memory_max cpu_quota tasks_max
    memory_max=$(echo "$aggregate_limits" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('memory_max', ''))" 2>/dev/null)
    cpu_quota=$(echo "$aggregate_limits" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('cpu_quota', ''))" 2>/dev/null)
    tasks_max=$(echo "$aggregate_limits" | python3 -c "import sys, json; data=json.load(sys.stdin); print(data.get('tasks_max', ''))" 2>/dev/null)

    # Get sanitized username for cgroup path
    local sanitized_user
    sanitized_user=$(sanitize_username_for_slice "$user")
    local group
    group=$(get_user_group "$user")

    # Build cgroup path — detect v2, unified, or v1 memory hierarchy
    local slice_name="ds01-${group}-${sanitized_user}.slice"
    local cgroup_path=""
    local cgroup_version="v2"
    if [[ -d "/sys/fs/cgroup/ds01.slice/ds01-${group}.slice/${slice_name}" ]]; then
        cgroup_path="/sys/fs/cgroup/ds01.slice/ds01-${group}.slice/${slice_name}"
        cgroup_version="v2"
    elif [[ -d "/sys/fs/cgroup/unified/ds01.slice/ds01-${group}.slice/${slice_name}" ]]; then
        cgroup_path="/sys/fs/cgroup/unified/ds01.slice/ds01-${group}.slice/${slice_name}"
        cgroup_version="v2"
    elif [[ -d "/sys/fs/cgroup/memory/ds01.slice/ds01-${group}.slice/${slice_name}" ]]; then
        cgroup_path="/sys/fs/cgroup/memory/ds01.slice/ds01-${group}.slice/${slice_name}"
        cgroup_version="v1"
    fi

    # FAIL-OPEN: If cgroup doesn't exist yet, allow (will be created)
    if [ -z "$cgroup_path" ]; then
        log_debug "FAIL-OPEN: Cgroup not found for ${slice_name} (allowing, will be created)"
        return 0
    fi

    # Extract requested container memory from Docker args
    # Look for --memory or --memory= flag
    local requested_memory_bytes=0
    local prev_arg=""
    for arg in "${_ORIGINAL_ARGS[@]}"; do
        case "$arg" in
            --memory=*)
                requested_memory_bytes=$(echo "${arg#--memory=}" | python3 -c "
import sys
size_str = sys.stdin.read().strip()
# Parse Docker memory format (e.g., '32g', '2048m', '1073741824')
multipliers = {'k': 1024, 'm': 1024**2, 'g': 1024**3, 't': 1024**4}
if size_str[-1].lower() in multipliers:
    print(int(float(size_str[:-1]) * multipliers[size_str[-1].lower()]))
else:
    print(size_str)
" 2>/dev/null)
                ;;
            --memory)
                prev_arg="--memory"
                ;;
            *)
                if [ "$prev_arg" = "--memory" ]; then
                    requested_memory_bytes=$(echo "$arg" | python3 -c "
import sys
size_str = sys.stdin.read().strip()
multipliers = {'k': 1024, 'm': 1024**2, 'g': 1024**3, 't': 1024**4}
if size_str[-1].lower() in multipliers:
    print(int(float(size_str[:-1]) * multipliers[size_str[-1].lower()]))
else:
    print(size_str)
" 2>/dev/null)
                    prev_arg=""
                else
                    prev_arg=""
                fi
                ;;
        esac
    done

    # If no --memory specified, use per-container default from user's config
    if [ "$requested_memory_bytes" -eq 0 ]; then
        local user_limits
        user_limits=$(python3 "$RESOURCE_PARSER" "$user" 2>/dev/null | grep "RAM:" | awk '{print $2}' || echo "32g")
        requested_memory_bytes=$(echo "$user_limits" | python3 -c "
import sys
size_str = sys.stdin.read().strip()
multipliers = {'k': 1024, 'm': 1024**2, 'g': 1024**3, 't': 1024**4}
if size_str and size_str[-1].lower() in multipliers:
    print(int(float(size_str[:-1]) * multipliers[size_str[-1].lower()]))
else:
    print(34359738368)  # 32G default
" 2>/dev/null)
    fi

    # Check memory usage (v2: memory.current, v1: memory.usage_in_bytes)
    local memory_file="memory.current"
    [[ "$cgroup_version" == "v1" ]] && memory_file="memory.usage_in_bytes"
    if [ -n "$memory_max" ] && [ -f "$cgroup_path/$memory_file" ]; then
        local current_memory
        current_memory=$(cat "$cgroup_path/$memory_file" 2>/dev/null || echo "0")

        # FAIL-OPEN: If we can't read current memory, allow
        if [ -z "$current_memory" ] || [ "$current_memory" = "0" ]; then
            log_debug "FAIL-OPEN: Could not read memory.current (allowing)"
        else
            # Convert memory_max to bytes (format: "96G")
            local memory_max_bytes
            memory_max_bytes=$(echo "$memory_max" | python3 -c "
import sys
size_str = sys.stdin.read().strip()
multipliers = {'K': 1024, 'M': 1024**2, 'G': 1024**3, 'T': 1024**4}
if size_str[-1].upper() in multipliers:
    print(int(float(size_str[:-1]) * multipliers[size_str[-1].upper()]))
else:
    print(size_str)
" 2>/dev/null)

            # Check if adding this container would exceed limit
            local projected_memory=$((current_memory + requested_memory_bytes))
            if [ "$projected_memory" -gt "$memory_max_bytes" ]; then
                # Convert to human-readable
                local current_gb=$((current_memory / 1024 / 1024 / 1024))
                local requested_gb=$((requested_memory_bytes / 1024 / 1024 / 1024))
                local limit_gb=$(echo "$memory_max" | sed 's/G//')

                echo "" >&2
                echo "┌─────────────────────────────────────────────────────────────────┐" >&2
                echo "│  DS01 Aggregate Memory Quota Exceeded                           │" >&2
                echo "├─────────────────────────────────────────────────────────────────┤" >&2
                echo "│                                                                  │" >&2
                printf "│  Current usage:    %3dG                                          │\n" "$current_gb" >&2
                printf "│  Requested:        %3dG                                          │\n" "$requested_gb" >&2
                printf "│  Your limit:       %3dG                                          │\n" "$limit_gb" >&2
                echo "│                                                                  │" >&2
                echo "│  This container would exceed your aggregate memory quota.        │" >&2
                echo "│                                                                  │" >&2
                echo "│  To free up quota:                                               │" >&2
                echo "│    • Stop a running container: docker stop <name>                │" >&2
                echo "│    • Check your containers: docker ps                            │" >&2
                echo "│    • Check your limits: check-limits                             │" >&2
                echo "│                                                                  │" >&2
                echo "└─────────────────────────────────────────────────────────────────┘" >&2
                echo "" >&2

                # Log denial event
                if command -v log_event &>/dev/null; then
                    log_event "quota.memory_exceeded" "$user" "docker-wrapper" \
                        current_gb="$current_gb" requested_gb="$requested_gb" limit_gb="$limit_gb" || true
                fi

                return 1
            fi
        fi
    fi

    # Check pids (soft check - warn at 90%)
    # v2: pids.current in same path; v1: separate hierarchy
    local pids_path="$cgroup_path/pids.current"
    if [[ "$cgroup_version" == "v1" ]]; then
        pids_path="/sys/fs/cgroup/pids/ds01.slice/ds01-${group}.slice/${slice_name}/pids.current"
    fi
    if [ -n "$tasks_max" ] && [ -f "$pids_path" ]; then
        local current_pids
        current_pids=$(cat "$pids_path" 2>/dev/null || echo "0")

        if [ -n "$current_pids" ] && [ "$current_pids" -gt 0 ]; then
            local threshold=$((tasks_max * 90 / 100))
            if [ "$current_pids" -gt "$threshold" ]; then
                echo "WARNING: You are using $current_pids pids (limit: $tasks_max)" >&2
                echo "Consider reducing the number of processes in your containers." >&2
                log_debug "WARNING: User $user near pids limit ($current_pids/$tasks_max)"
            fi
        fi
    fi

    # CPU quota is enforced by systemd kernel-level, no pre-check needed
    log_debug "Aggregate quota check passed for $user"
    return 0
}

# Phase 03-02: Container isolation enforcement (Jan 2026)
#
# After OPA authz plugin proved non-viable, container isolation is now enforced
# directly in the Docker wrapper:
# 1. 'docker ps' filtered to show only user's containers (via label filter)
# 2. All container-targeting operations verify ownership via ds01.user label
# 3. Admin bypass for root/datasciencelab/ds01-admin group
# 4. Rate-limited denial logging to prevent log flooding
# 5. Fail-open for unowned containers (prevents blocking legacy workloads)
# 6. Monitoring mode (DS01_ISOLATION_MODE=monitoring) for safe rollout

# Check if user is an admin (root, datasciencelab, or ds01-admin group)
is_admin() {
    # Root is always admin (needed for cron jobs running as root)
    [[ "$CURRENT_UID" -eq 0 ]] && return 0
    # datasciencelab is always admin
    [[ "$CURRENT_USER" == "datasciencelab" ]] && return 0
    # Check ds01-admin group membership
    groups "$CURRENT_USER" 2>/dev/null | grep -qE '\bds01-admin\b'
}

# Filter container list for non-admins
filter_container_list() {
    # Monitoring mode: log but don't filter
    if [[ "${_MONITORING_ONLY:-false}" == "true" ]]; then
        log_debug "MONITORING: would filter container list for user=$CURRENT_USER"
        exec "$REAL_DOCKER" "$@"
    fi

    if is_admin; then
        log_debug "Admin pass-through for container list"
        exec "$REAL_DOCKER" "$@"
    fi

    # Non-admin: filter to show only own containers
    # Inject --filter for ds01.user label
    log_debug "Filtering container list for user=$CURRENT_USER"

    # Build filtered args - insert filter before other args
    local subcommand="$1"
    shift
    exec "$REAL_DOCKER" "$subcommand" --filter "label=ds01.user=$CURRENT_USER" "$@"
}

# Verify container ownership for operations
verify_container_ownership() {
    local container="$1"
    local operation="$2"  # for logging

    # Admin bypass
    is_admin && return 0

    # Get container owner from ds01.user label
    local owner
    owner=$("$REAL_DOCKER" inspect "$container" --format '{{index .Config.Labels "ds01.user"}}' 2>/dev/null || echo "")

    # Fallback: check aime.mlc.USER label for pre-Phase-3 containers
    if [[ -z "$owner" || "$owner" == "<no value>" ]]; then
        owner=$("$REAL_DOCKER" inspect "$container" --format '{{index .Config.Labels "aime.mlc.USER"}}' 2>/dev/null || echo "")
    fi

    # No owner label at all - fail-open with warning
    # FAIL-OPEN: Allow unowned containers to prevent blocking legitimate operations
    if [[ -z "$owner" || "$owner" == "<no value>" ]]; then
        log_debug "WARNING: Container $container has no owner label - allowing operation (fail-open)"
        # Log warning event (best-effort)
        if command -v log_event &>/dev/null; then
            log_event "access.unowned_container" "$CURRENT_USER" "docker-wrapper" \
                container="$container" operation="$operation" || true
        fi
        return 0
    fi

    # Check ownership
    if [[ "$owner" != "$CURRENT_USER" ]]; then
        # Monitoring mode: log but allow
        if [[ "${_MONITORING_ONLY:-false}" == "true" ]]; then
            logger -p auth.notice -t ds01-wrapper "MONITORING: would deny user=$CURRENT_USER operation=$operation container=$container owner=$owner" 2>/dev/null || true
            log_debug "MONITORING: would deny user=$CURRENT_USER operation=$operation (container belongs to $owner)"
            return 0
        fi

        echo "Permission denied: this container belongs to ${owner}" >&2
        # Rate-limited denial logging
        rate_limited_deny_log "$CURRENT_USER" "$operation $container" "container belongs to $owner"
        return 1
    fi

    return 0
}

# Rate-limited denial logging (max 10 denials per user per hour)
rate_limited_deny_log() {
    local user="$1"
    local command="$2"
    local reason="$3"
    local now
    now=$(date +%s)
    local state_file="/var/lib/ds01/rate-limits/deny-${user}.state"

    mkdir -p /var/lib/ds01/rate-limits 2>/dev/null || true

    local count=0
    local timestamp=$now
    if [[ -f "$state_file" ]]; then
        read -r count timestamp < "$state_file" 2>/dev/null || true
        # Reset if window expired (3600s = 1 hour)
        if (( now - timestamp > 3600 )); then
            count=0
            timestamp=$now
        fi
    fi

    # First denial always logged at warning level
    if (( count == 0 )); then
        logger -p auth.warning -t ds01-access "FIRST DENIAL: user=$user command=$command reason=$reason" 2>/dev/null || true
    fi

    # Check limit (max 10 per hour)
    if (( count < 10 )); then
        logger -p auth.notice -t ds01-access "DENIED: user=$user command=$command reason=$reason (${count}+1/10)" 2>/dev/null || true
    fi

    (echo "$((count + 1)) $timestamp" > "$state_file") 2>/dev/null || true

    # Log event (best-effort)
    if command -v log_event &>/dev/null; then
        log_event "auth.denied" "$user" "docker-wrapper" \
            command="$command" reason="$reason" || true
    fi
}

# Check if a container is protected infrastructure
is_protected_container() {
    local container="$1"
    local is_protected
    is_protected=$($REAL_DOCKER inspect "$container" --format '{{index .Config.Labels "ds01.protected"}}' 2>/dev/null)
    [[ "$is_protected" == "true" ]]
}

# Extract container target from args
# Skips flags (args starting with -) and their values
extract_container_target() {
    local skip_next=false
    for arg in "$@"; do
        if $skip_next; then
            skip_next=false
            continue
        fi
        case "$arg" in
            -*=*) continue ;;  # --flag=value
            -*)
                # Flags that take a value: skip next arg
                case "$arg" in
                    -e|-w|--env|--workdir|--user|-u|--name|--label|-l|--format|-f|--filter|--signal)
                        skip_next=true ;;
                esac
                continue
                ;;
            *)
                # First non-flag arg is the container
                echo "$arg"
                return 0
                ;;
        esac
    done
    return 1
}

# Main logic
main() {
    # Save original args for fail-open fallback
    _ORIGINAL_ARGS=("$@")

    # Emergency bypass - FAIL-OPEN for wrapper crashes or emergencies
    if [[ "${DS01_WRAPPER_BYPASS:-0}" == "1" ]]; then
        exec "$REAL_DOCKER" "$@"
    fi

    # Isolation mode: disabled | monitoring | full (default)
    case "${DS01_ISOLATION_MODE:-full}" in
        disabled) exec "$REAL_DOCKER" "$@" ;;
        monitoring) _MONITORING_ONLY=true ;;
        *) _MONITORING_ONLY=false ;;
    esac

    # Debug mode level 2: log all invocations
    if [[ "${DS01_WRAPPER_DEBUG:-0}" -ge 2 ]]; then
        log_debug "INVOCATION: docker $*"
    fi

    # If no arguments, pass through
    if [ $# -eq 0 ]; then
        exec "$REAL_DOCKER"
    fi

    # Get the Docker subcommand
    local subcommand="$1"

    # ========================================================================
    # CONTAINER LIST FILTERING (docker ps, docker container ls/list/ps)
    # ========================================================================
    if [[ "$subcommand" == "ps" ]]; then
        filter_container_list "$@"
    fi

    if [[ "$subcommand" == "container" ]]; then
        local container_subcommand="${2:-}"
        if [[ "$container_subcommand" == "ls" || "$container_subcommand" == "list" || "$container_subcommand" == "ps" ]]; then
            filter_container_list "$@"
        fi
    fi

    # ========================================================================
    # CONTAINER-TARGETING READ OPERATIONS (require ownership verification)
    # ========================================================================
    # exec, logs, inspect, stats, attach, top, port, diff, export, wait
    if [[ "$subcommand" == "exec" || "$subcommand" == "logs" || "$subcommand" == "inspect" || \
          "$subcommand" == "stats" || "$subcommand" == "attach" || "$subcommand" == "top" || \
          "$subcommand" == "port" || "$subcommand" == "diff" || "$subcommand" == "export" || \
          "$subcommand" == "wait" ]]; then
        shift
        local container
        if container=$(extract_container_target "$@"); then
            if ! verify_container_ownership "$container" "$subcommand"; then
                exit 1
            fi
        fi
        exec "$REAL_DOCKER" "$subcommand" "$@"
    fi

    # docker container <subcommand> — handle 'docker container exec', etc.
    if [[ "$subcommand" == "container" ]]; then
        local container_subcommand="${2:-}"
        if [[ "$container_subcommand" == "exec" || "$container_subcommand" == "logs" || \
              "$container_subcommand" == "inspect" || "$container_subcommand" == "stats" || \
              "$container_subcommand" == "attach" || "$container_subcommand" == "top" || \
              "$container_subcommand" == "port" || "$container_subcommand" == "diff" || \
              "$container_subcommand" == "export" || "$container_subcommand" == "wait" ]]; then
            shift 2
            local container
            if container=$(extract_container_target "$@"); then
                if ! verify_container_ownership "$container" "$container_subcommand"; then
                    exit 1
                fi
            fi
            exec "$REAL_DOCKER" container "$container_subcommand" "$@"
        fi
    fi

    # ========================================================================
    # CONTAINER-TARGETING WRITE OPERATIONS (ownership + protected check)
    # ========================================================================
    # stop, start, restart, pause, unpause, kill, rm, remove, rename, update
    if [[ "$subcommand" == "stop" || "$subcommand" == "start" || "$subcommand" == "restart" || \
          "$subcommand" == "pause" || "$subcommand" == "unpause" || "$subcommand" == "kill" || \
          "$subcommand" == "rm" || "$subcommand" == "remove" || "$subcommand" == "rename" || \
          "$subcommand" == "update" ]]; then
        shift
        # Extract container targets (support multiple containers for stop/kill/rm)
        local containers=()
        local skip_next=false
        for arg in "$@"; do
            if $skip_next; then
                skip_next=false
                continue
            fi
            case "$arg" in
                -*=*) continue ;;
                -*)
                    case "$arg" in
                        -t|--time|--signal) skip_next=true ;;
                    esac
                    continue
                    ;;
                *) containers+=("$arg") ;;
            esac
        done

        # Verify ownership and protected status for all containers
        for container in "${containers[@]}"; do
            # Protected container check
            if is_protected_container "$container"; then
                if ! is_admin; then
                    echo "Error: Container '$container' is protected infrastructure." >&2
                    echo "Admin access required. Contact system administrator." >&2
                    exit 1
                fi
                log_debug "Admin $CURRENT_USER allowed to $subcommand protected container: $container"
            fi

            # Ownership verification
            if ! verify_container_ownership "$container" "$subcommand"; then
                exit 1
            fi
        done

        exec "$REAL_DOCKER" "$subcommand" "$@"
    fi

    # docker container <subcommand> — handle 'docker container stop', etc.
    if [[ "$subcommand" == "container" ]]; then
        local container_subcommand="${2:-}"
        if [[ "$container_subcommand" == "stop" || "$container_subcommand" == "start" || \
              "$container_subcommand" == "restart" || "$container_subcommand" == "pause" || \
              "$container_subcommand" == "unpause" || "$container_subcommand" == "kill" || \
              "$container_subcommand" == "rm" || "$container_subcommand" == "remove" || \
              "$container_subcommand" == "rename" || "$container_subcommand" == "update" ]]; then
            shift 2
            # Extract container targets
            local containers=()
            local skip_next=false
            for arg in "$@"; do
                if $skip_next; then
                    skip_next=false
                    continue
                fi
                case "$arg" in
                    -*=*) continue ;;
                    -*)
                        case "$arg" in
                            -t|--time|--signal) skip_next=true ;;
                        esac
                        continue
                        ;;
                    *) containers+=("$arg") ;;
                esac
            done

            # Verify ownership and protected status for all containers
            for container in "${containers[@]}"; do
                # Protected container check
                if is_protected_container "$container"; then
                    if ! is_admin; then
                        echo "Error: Container '$container' is protected infrastructure." >&2
                        echo "Admin access required. Contact system administrator." >&2
                        exit 1
                    fi
                    log_debug "Admin $CURRENT_USER allowed to $container_subcommand protected container: $container"
                fi

                # Ownership verification
                if ! verify_container_ownership "$container" "$container_subcommand"; then
                    exit 1
                fi
            done

            exec "$REAL_DOCKER" container "$container_subcommand" "$@"
        fi
    fi

    # ========================================================================
    # CONTAINER CREATION (cgroup injection, label injection, GPU allocation)
    # ========================================================================
    # Check if we need to inject for container creation
    if needs_cgroup_injection "$subcommand"; then
        log_debug "Intercepting '$subcommand' for user $CURRENT_USER"

        # Get user's group
        USER_GROUP=$(get_user_group "$CURRENT_USER")
        log_debug "User group: $USER_GROUP"

        # Build the cgroup-parent path (with sanitized username for systemd compatibility)
        SANITIZED_USER=$(sanitize_username_for_slice "$CURRENT_USER")
        SLICE_NAME="ds01-${USER_GROUP}-${SANITIZED_USER}.slice"
        log_debug "Sanitized user: $SANITIZED_USER"

        # Ensure the slice exists
        ensure_user_slice "$USER_GROUP" "$CURRENT_USER"
        log_debug "Ensured slice: $SLICE_NAME"

        # Check aggregate resource quota (memory, pids)
        # This check runs BEFORE GPU allocation to fail fast on quota issues
        if ! check_aggregate_quota "$CURRENT_USER"; then
            exit 1
        fi

        # Detect container type
        local CONTAINER_TYPE
        CONTAINER_TYPE=$(detect_container_type "$@")
        log_debug "Container type: $CONTAINER_TYPE"

        # Check for GPU request
        local GPU_REQUESTED=false
        local GPU_UUID=""
        local GPU_SLOT=""

        if has_gpu_request "$@"; then
            GPU_REQUESTED=true
            log_debug "GPU request detected"

            # Check if GPU allocation should be skipped:
            # 1. DS01 native containers (atomic/orchestration) handle their own allocation
            # 2. Specific device UUID already set (e.g. mlc temp containers with pre-allocated GPU)
            local gpu_value
            gpu_value=$(get_gpu_request_value "$@")
            local skip_gpu_alloc=false

            if [[ "$CONTAINER_TYPE" == "orchestration" ]] || [[ "$CONTAINER_TYPE" == "atomic" ]]; then
                log_debug "DS01 native container - GPU allocation handled by ds01 layer"
                skip_gpu_alloc=true
            elif [[ "$gpu_value" == device=MIG-* ]] || [[ "$gpu_value" == device=GPU-* ]]; then
                log_debug "Specific GPU device already set ($gpu_value) - skipping re-allocation"
                skip_gpu_alloc=true
            fi

            if [[ "$skip_gpu_alloc" == "false" ]]; then
                # External container requesting GPU - allocate through ds01
                log_debug "External container requesting GPU - initiating allocation"

                # Determine the effective owner
                local effective_owner="$CURRENT_USER"
                local devcontainer_owner
                devcontainer_owner=$(get_devcontainer_owner "$@")
                if [ -n "$devcontainer_owner" ]; then
                    effective_owner="$devcontainer_owner"
                fi

                # Allocate GPU
                GPU_UUID=$(allocate_gpu_for_container "$effective_owner" "$CONTAINER_TYPE")

                if [ -z "$GPU_UUID" ]; then
                    # Allocation failed - log auth denial
                    if command -v log_event &>/dev/null; then
                        log_event "auth.denied" "$effective_owner" "docker-wrapper" \
                            reason="${GPU_ALLOC_ERROR}: ${GPU_ALLOC_DETAILS}" \
                            container_type="$CONTAINER_TYPE" || true
                    fi

                    # Show error to user
                    show_gpu_error "$GPU_ALLOC_ERROR" "$GPU_ALLOC_DETAILS"
                    exit 1
                fi

                # Show notice about ephemeral nature
                local idle_timeout
                local max_runtime
                idle_timeout=$(get_container_type_timeout "$CONTAINER_TYPE")
                max_runtime=$(get_container_type_max_runtime "$CONTAINER_TYPE")
                show_gpu_notice "$GPU_UUID" "$CONTAINER_TYPE" "$idle_timeout" "$max_runtime"

                GPU_SLOT="$GPU_UUID"
                log_debug "GPU allocated: $GPU_UUID"
            fi
        fi

        # Build injection arguments
        local INJECT_ARGS=()

        # Inject --cgroup-parent if not already specified
        if ! has_cgroup_parent "$@"; then
            INJECT_ARGS+=("--cgroup-parent=$SLICE_NAME")
            log_debug "Injecting cgroup-parent: $SLICE_NAME"
        fi

        # Inject owner label if not already specified
        if ! has_owner_label "$@"; then
            # Check if this is a VS Code devcontainer with a local_folder path
            local devcontainer_owner
            devcontainer_owner=$(get_devcontainer_owner "$@")
            if [ -n "$devcontainer_owner" ]; then
                # VS Code container - extract owner from devcontainer.local_folder path
                INJECT_ARGS+=("--label" "ds01.user=$devcontainer_owner")
                log_debug "Injecting owner label from devcontainer: ds01.user=$devcontainer_owner"
            else
                # Regular container - use current user
                INJECT_ARGS+=("--label" "ds01.user=$CURRENT_USER")
                log_debug "Injecting owner label: ds01.user=$CURRENT_USER"
            fi
        fi

        # Inject ds01.managed and container type labels
        INJECT_ARGS+=("--label" "ds01.managed=true")
        INJECT_ARGS+=("--label" "ds01.container_type=$CONTAINER_TYPE")
        INJECT_ARGS+=("--label" "ds01.created_at=$(date -Iseconds)")

        # Inject GPU-specific labels if GPU was allocated
        if [ -n "$GPU_SLOT" ]; then
            INJECT_ARGS+=("--label" "ds01.gpu_slot=$GPU_SLOT")
            INJECT_ARGS+=("--label" "ds01.gpu_ephemeral=true")
        fi

        # Remove subcommand from args
        shift

        # Rewrite GPU args if we allocated a specific GPU
        local FINAL_ARGS=("$@")
        if [ -n "$GPU_UUID" ] && [ "$CONTAINER_TYPE" != "orchestration" ] && [ "$CONTAINER_TYPE" != "atomic" ]; then
            # Rebuild args with rewritten GPU specification
            FINAL_ARGS=()
            local skip_next=false
            for arg in "$@"; do
                if $skip_next; then
                    skip_next=false
                    continue
                fi

                case "$arg" in
                    --gpus=*)
                        # Replace with specific device
                        FINAL_ARGS+=("--gpus" "device=$GPU_UUID")
                        ;;
                    --gpus)
                        # Skip this and the next arg (the value), replace with our allocation
                        skip_next=true
                        FINAL_ARGS+=("--gpus" "device=$GPU_UUID")
                        ;;
                    *)
                        FINAL_ARGS+=("$arg")
                        ;;
                esac
            done
            log_debug "Rewrote GPU args to device=$GPU_UUID"
        fi

        # Execute with injected args
        log_debug "Executing: $REAL_DOCKER $subcommand ${INJECT_ARGS[*]} ${FINAL_ARGS[*]}"

        # Log container creation event (best-effort, never blocks)
        # Extract container name from args for logging
        local CONTAINER_NAME=""
        local IMAGE_NAME=""
        local skip_next=false
        for arg in "${FINAL_ARGS[@]}"; do
            if $skip_next; then
                skip_next=false
                continue
            fi
            case "$arg" in
                --name)
                    skip_next=true
                    ;;
                --name=*)
                    CONTAINER_NAME="${arg#--name=}"
                    ;;
                *)
                    # Last non-flag arg is typically the image
                    if [[ "$arg" != -* ]] && [[ "$arg" != *=* ]]; then
                        IMAGE_NAME="$arg"
                    fi
                    ;;
            esac
        done

        # Determine effective owner for logging
        local LOG_USER="$CURRENT_USER"
        local devcontainer_owner
        devcontainer_owner=$(get_devcontainer_owner "$@")
        if [ -n "$devcontainer_owner" ]; then
            LOG_USER="$devcontainer_owner"
        fi

        # Log event BEFORE docker exec (so we capture creation attempt)
        # Using || true ensures this never blocks the operation
        if command -v log_event &>/dev/null; then
            log_event "container.create" "$LOG_USER" "docker-wrapper" \
                container="${CONTAINER_NAME:-unknown}" \
                image="${IMAGE_NAME:-unknown}" \
                container_type="$CONTAINER_TYPE" \
                gpu="${GPU_SLOT:-none}" || true
        fi

        exec "$REAL_DOCKER" "$subcommand" "${INJECT_ARGS[@]}" "${FINAL_ARGS[@]}"
    else
        # Pass through unchanged
        log_debug "Pass-through: $REAL_DOCKER $*"
        exec "$REAL_DOCKER" "$@"
    fi
}

# Run main
main "$@"
