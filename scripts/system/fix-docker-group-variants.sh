#!/bin/bash
# /opt/ds01-infra/scripts/system/fix-docker-group-variants.sh
# One-time cleanup script to fix non-canonical usernames in docker group
#
# Problem: PAM may have added users with domain variants (e.g., user@students.hertie-school.org)
# instead of the canonical username from passwd (e.g., user@hertie-school.lan).
# This causes Docker permission denied errors.
#
# Solution: Scan docker group, resolve each entry to canonical form via UID,
# remove non-canonical entries, and ensure canonical entry exists.
#
# Usage:
#   sudo fix-docker-group-variants.sh --report   # Dry run - show what would be fixed
#   sudo fix-docker-group-variants.sh --apply    # Actually fix the entries

set -e

LOG_FILE="/var/log/ds01/docker-group-additions.log"

log_msg() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE" 2>/dev/null || echo "$1"
}

# Must be root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root (use sudo)"
    exit 1
fi

# Ensure log directory exists
mkdir -p "$(dirname "$LOG_FILE")" 2>/dev/null || true

# Check if docker group exists
if ! getent group docker &>/dev/null; then
    echo "Error: docker group does not exist"
    exit 1
fi

# Resolve username to canonical form via UID
get_canonical_username() {
    local input_user="$1"
    local uid
    uid=$(id -u "$input_user" 2>/dev/null) || return 1
    getent passwd "$uid" 2>/dev/null | cut -d: -f1
}

report_mode() {
    echo "=== Docker Group Variant Report ==="
    echo ""

    local docker_members
    docker_members=$(getent group docker | cut -d: -f4 | tr ',' '\n')

    local non_canonical_count=0
    local needs_canonical_count=0
    local ok_count=0

    while IFS= read -r member; do
        [ -z "$member" ] && continue

        # Try to get UID for this member
        local uid
        uid=$(id -u "$member" 2>/dev/null)
        if [ $? -ne 0 ]; then
            echo "[ORPHAN]  $member - cannot resolve UID (may be stale entry)"
            continue
        fi

        # Get canonical username for this UID
        local canonical
        canonical=$(get_canonical_username "$member")

        if [ -z "$canonical" ]; then
            echo "[ERROR]   $member (UID=$uid) - cannot resolve canonical name"
            continue
        fi

        if [ "$member" = "$canonical" ]; then
            echo "[OK]      $member"
            ok_count=$((ok_count + 1))
        else
            echo "[VARIANT] $member → should be $canonical (UID=$uid)"
            non_canonical_count=$((non_canonical_count + 1))

            # Check if canonical is already in group
            if ! echo "$docker_members" | grep -qx "$canonical"; then
                echo "          + $canonical needs to be added"
                needs_canonical_count=$((needs_canonical_count + 1))
            fi
        fi
    done <<< "$docker_members"

    echo ""
    echo "=== Summary ==="
    echo "OK (canonical):           $ok_count"
    echo "Non-canonical variants:   $non_canonical_count"
    echo "Canonical missing:        $needs_canonical_count"
    echo ""

    if [ "$non_canonical_count" -gt 0 ]; then
        echo "Run with --apply to fix these entries."
    else
        echo "No fixes needed."
    fi
}

apply_fixes() {
    echo "=== Applying Docker Group Fixes ==="
    echo ""
    log_msg "fix-docker-group-variants: Starting fix run"

    local docker_members
    docker_members=$(getent group docker | cut -d: -f4 | tr ',' '\n')

    local fixed_count=0
    local error_count=0

    # Track which canonicals we've already added (to avoid duplicate adds)
    declare -A added_canonicals

    while IFS= read -r member; do
        [ -z "$member" ] && continue

        # Try to get UID for this member
        local uid
        uid=$(id -u "$member" 2>/dev/null)
        if [ $? -ne 0 ]; then
            echo "[SKIP]    $member - cannot resolve UID (orphan entry)"
            continue
        fi

        # Get canonical username for this UID
        local canonical
        canonical=$(get_canonical_username "$member")

        if [ -z "$canonical" ]; then
            echo "[ERROR]   $member - cannot resolve canonical name"
            error_count=$((error_count + 1))
            continue
        fi

        if [ "$member" = "$canonical" ]; then
            # Already canonical, nothing to do
            continue
        fi

        echo "[FIX]     $member → $canonical (UID=$uid)"

        # First, ensure canonical is in the group (if not already added)
        if [ -z "${added_canonicals[$canonical]:-}" ]; then
            if ! groups "$canonical" 2>/dev/null | grep -q '\bdocker\b'; then
                if usermod -aG docker "$canonical" 2>/dev/null; then
                    echo "          + Added $canonical to docker group"
                    log_msg "fix-docker-group-variants: Added canonical '$canonical' to docker group"
                    added_canonicals[$canonical]=1
                else
                    echo "          ! Failed to add $canonical"
                    log_msg "fix-docker-group-variants: ERROR - Failed to add '$canonical'"
                    error_count=$((error_count + 1))
                    continue
                fi
            else
                echo "          = $canonical already in docker group"
                added_canonicals[$canonical]=1
            fi
        fi

        # Now remove the non-canonical variant
        if gpasswd -d "$member" docker 2>/dev/null; then
            echo "          - Removed $member from docker group"
            log_msg "fix-docker-group-variants: Removed variant '$member' from docker group"
            fixed_count=$((fixed_count + 1))
        else
            echo "          ! Failed to remove $member"
            log_msg "fix-docker-group-variants: ERROR - Failed to remove '$member'"
            error_count=$((error_count + 1))
        fi
    done <<< "$docker_members"

    echo ""
    echo "=== Summary ==="
    echo "Fixed:    $fixed_count"
    echo "Errors:   $error_count"
    echo ""

    log_msg "fix-docker-group-variants: Completed - fixed=$fixed_count errors=$error_count"

    if [ "$error_count" -gt 0 ]; then
        exit 1
    fi
}

# Main
case "${1:-}" in
    --report)
        report_mode
        ;;
    --apply)
        apply_fixes
        ;;
    --help|-h)
        echo "Fix non-canonical usernames in docker group"
        echo ""
        echo "Usage:"
        echo "  $0 --report   Dry run - show what would be fixed"
        echo "  $0 --apply    Actually fix the entries"
        echo "  $0 --help     Show this help"
        echo ""
        echo "This script resolves domain variant mismatches where PAM added"
        echo "users with a different domain (e.g., @students.hertie-school.org)"
        echo "than the canonical username in passwd (@hertie-school.lan)."
        ;;
    "")
        echo "Error: Must specify --report or --apply"
        echo "Run '$0 --help' for usage"
        exit 1
        ;;
    *)
        echo "Error: Unknown option '$1'"
        echo "Run '$0 --help' for usage"
        exit 1
        ;;
esac
