#!/bin/bash
# /opt/ds01-infra/scripts/system/verify-cgroup-driver.sh
# Verify Docker daemon uses systemd cgroup driver (required for DS01)
#
# DS01 requires systemd cgroup driver for cgroup integration.
# Container resource limits are enforced via user slices (ds01-{group}-{user}.slice),
# which require Docker to use systemd driver (not cgroupfs).
# Both cgroup v1 (hybrid) and pure v2 are supported.
#
# Exit 0: Docker configured correctly
# Exit 1: Docker misconfigured (cgroupfs driver or other error)

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
BOLD='\033[1m'
NC='\033[0m'

# Check if Docker daemon is running
if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}ERROR: Docker daemon is not running${NC}"
    echo ""
    echo "Start Docker with: sudo systemctl start docker"
    exit 1
fi

# Check cgroup driver
CGROUP_DRIVER=$(docker info --format '{{.CgroupDriver}}' 2>/dev/null)

if [ -z "$CGROUP_DRIVER" ]; then
    echo -e "${RED}ERROR: Could not determine Docker cgroup driver${NC}"
    echo ""
    echo "Run 'docker info' to check daemon status"
    exit 1
fi

# Verify systemd driver
if [ "$CGROUP_DRIVER" != "systemd" ]; then
    echo -e "${RED}ERROR: Docker is using '$CGROUP_DRIVER' cgroup driver${NC}"
    echo ""
    echo -e "${BOLD}DS01 requires systemd cgroup driver${NC}"
    echo ""
    echo "To fix this, add to /etc/docker/daemon.json:"
    echo ""
    echo '  {'
    echo '    "exec-opts": ["native.cgroupdriver=systemd"]'
    echo '  }'
    echo ""
    echo "Then restart Docker:"
    echo "  sudo systemctl restart docker"
    echo ""
    exit 1
fi

# Detect cgroup version (informational only — both v1 and v2 are supported)
if [ -f /sys/fs/cgroup/cgroup.controllers ]; then
    CGROUP_VER="v2"
else
    CGROUP_VER="v1"
fi

# Success
echo -e "${GREEN}✓${NC} Docker cgroup driver: ${BOLD}systemd${NC} (cgroup ${CGROUP_VER})"
exit 0
