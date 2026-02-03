#!/bin/bash
# Add user to docker group for Docker access
# Run with: sudo bash /opt/ds01-infra/scripts/system/add-user-to-docker.sh <username>
#
# IMPORTANT: Resolves input username to canonical form via UID to handle
# domain variants (e.g., user@students.hertie-school.org vs user@hertie-school.lan)

set -e

if [ "$EUID" -ne 0 ]; then
    echo "Error: This script must be run as root (use sudo)"
    exit 1
fi

USERNAME="${1:-}"

if [ -z "$USERNAME" ]; then
    echo "Usage: sudo bash $0 <username>"
    echo ""
    echo "Example: sudo bash $0 student1"
    exit 1
fi

# Check if user exists (any domain variant)
if ! id "$USERNAME" &>/dev/null; then
    echo "Error: User '$USERNAME' does not exist"
    exit 1
fi

# Resolve to canonical username via UID
USER_UID=$(id -u "$USERNAME")
CANONICAL_USER=$(getent passwd "$USER_UID" 2>/dev/null | cut -d: -f1)

if [ -z "$CANONICAL_USER" ]; then
    echo "Error: Could not resolve canonical username for '$USERNAME'"
    exit 1
fi

# Check if docker group exists
if ! getent group docker &>/dev/null; then
    echo "Error: docker group does not exist. Docker may not be installed."
    exit 1
fi

# Display resolution if mismatch detected
if [ "$USERNAME" != "$CANONICAL_USER" ]; then
    echo "Note: Resolved '$USERNAME' to canonical username '$CANONICAL_USER'"
fi

# Add canonical user to docker group
echo "Adding $CANONICAL_USER to docker group..."
usermod -aG docker "$CANONICAL_USER"

# Add to video group (required for nvidia-smi / GPU allocator)
# Video group allows nvidia-smi to communicate with the NVIDIA driver.
# This does NOT grant bare-metal CUDA access — that's controlled by
# CUDA_VISIBLE_DEVICES="" in /etc/profile.d/ds01-gpu-awareness.sh.
# Bare-metal overrides are managed via: sudo bare-metal-access grant <user>
echo "Adding $CANONICAL_USER to video group..."
usermod -aG video "$CANONICAL_USER"

echo ""
echo "$CANONICAL_USER has been added to the docker and video groups"
echo ""
echo "IMPORTANT: The user must log out and log back in for this to take effect."
echo ""
echo "To verify after logging back in, the user can run:"
echo "  groups"
echo ""
echo "They should see 'docker' and 'video' in the list of groups."
echo ""
