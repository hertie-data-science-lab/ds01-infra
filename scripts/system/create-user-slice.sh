#!/bin/bash
# /opt/ds01-infra/scripts/system/create-user-slice.sh
# Dynamically creates per-user systemd cgroup slices
#
# This script is called automatically by container-create to ensure
# each user gets their own monitoring slice within their group.
#
# Hierarchy: ds01.slice → ds01-{group}.slice → ds01-{group}-{username}.slice

set -euo pipefail

# Source username sanitization library
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/username-utils.sh"

# Check if running as root
if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root (use sudo)"
    exit 1
fi

# Usage check
if [ $# -lt 2 ]; then
    echo "Usage: $0 <group> <username>"
    echo ""
    echo "Example: $0 student alice"
    echo "  Creates: ds01-student-alice.slice under ds01-student.slice"
    exit 1
fi

GROUP="$1"
USERNAME="$2"
SANITIZED_USERNAME=$(sanitize_username_for_slice "$USERNAME")
SLICE_NAME="ds01-${GROUP}-${SANITIZED_USERNAME}.slice"
PARENT_SLICE="ds01-${GROUP}.slice"
SLICE_FILE="/etc/systemd/system/${SLICE_NAME}"

# Check if parent slice exists (check for slice file OR active slice)
PARENT_SLICE_FILE="/etc/systemd/system/${PARENT_SLICE}"
if [ ! -f "$PARENT_SLICE_FILE" ]; then
    echo "Error: Parent slice $PARENT_SLICE does not exist"
    echo "Run: sudo /opt/ds01-infra/scripts/system/setup-resource-slices.sh"
    exit 1
fi

# Check if user slice already exists
if [ -f "$SLICE_FILE" ]; then
    # Slice already exists, nothing to do
    exit 0
fi

# Create user slice
# Note: Description includes original username for identification
cat > "$SLICE_FILE" << EOF
[Unit]
Description=DS01 ${GROUP^} - ${USERNAME} (${SANITIZED_USERNAME})
Before=slices.target

[Slice]
Slice=${PARENT_SLICE}
CPUAccounting=true
MemoryAccounting=true
TasksAccounting=true
IOAccounting=true
EOF

# Reload systemd
systemctl daemon-reload

# Apply aggregate resource limits from resource-limits.yaml
# Uses generate-user-slice-limits.py with --user flag for fast single-user update
# Falls back gracefully if generator not deployed yet
if [ -x "$SCRIPT_DIR/generate-user-slice-limits.py" ]; then
    python3 "$SCRIPT_DIR/generate-user-slice-limits.py" --user "$USERNAME" 2>/dev/null || true
fi

# Note: We don't set resource limits at the user level.
# Resource limits are enforced at:
# 1. Group level (via parent slice)
# 2. Container level (via docker update)
# 3. Per-user aggregate (via drop-in files, Phase 4)
#
# User slices are primarily for monitoring/tracking, but now also
# enforce aggregate limits via drop-in configurations.

exit 0
