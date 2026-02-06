#!/bin/bash
# DS01 Permissions Manifest
# =========================
# Sourced by deploy.sh to enforce deterministic file permissions.
# Ensures correct permissions regardless of umask or git checkout state.
#
# Principles:
#   - Executable scripts: 755 (world-readable + executable)
#   - Configuration files: 644 (world-readable, owner-writable)
#   - Shared libraries (.so): 755 (loadable via LD_PRELOAD)
#   - State directories: per-policy (see comments below)
#
# This file is the single source of truth for DS01 file permissions.
# Add new paths here when creating new scripts, config, or state directories.

# Requires: INFRA_ROOT, USER_ATOMIC, USER_ORCHESTRATORS, USER_WIZARDS,
#           USER_HELPERS, USER_DISPATCHERS, DIM, NC (from deploy.sh)

echo -e "${DIM}Enforcing permissions...${NC}"

# =============================================================================
# Executable Scripts (755)
# =============================================================================

# User commands (L2-L4)
chmod 755 "$USER_ATOMIC"/* 2>/dev/null
chmod 755 "$USER_ORCHESTRATORS"/* 2>/dev/null
chmod 755 "$USER_WIZARDS"/* 2>/dev/null
chmod 755 "$USER_HELPERS"/* 2>/dev/null
chmod 755 "$USER_DISPATCHERS"/* 2>/dev/null

# Internal scripts
chmod 755 "$INFRA_ROOT"/scripts/lib/*.sh "$INFRA_ROOT"/scripts/lib/*.py 2>/dev/null
chmod 755 "$INFRA_ROOT"/scripts/docker/*.sh "$INFRA_ROOT"/scripts/docker/*.py 2>/dev/null
chmod 755 "$INFRA_ROOT"/scripts/admin/* 2>/dev/null
chmod 755 "$INFRA_ROOT"/scripts/monitoring/*.sh "$INFRA_ROOT"/scripts/monitoring/*.py 2>/dev/null
chmod 755 "$INFRA_ROOT"/scripts/maintenance/*.sh 2>/dev/null
chmod 755 "$INFRA_ROOT"/scripts/system/*.sh "$INFRA_ROOT"/scripts/system/*.py 2>/dev/null
chmod 755 "$INFRA_ROOT"/scripts/user/ds01-login-check 2>/dev/null

# =============================================================================
# Configuration Files (644) and Directories (755)
# =============================================================================

# Config directories must be traversable
chmod 755 "$INFRA_ROOT"/config/runtime 2>/dev/null
chmod 755 "$INFRA_ROOT"/config/runtime/groups 2>/dev/null

# Config files must be world-readable
chmod 644 "$INFRA_ROOT"/config/*.yaml "$INFRA_ROOT"/config/*.yml 2>/dev/null
chmod 644 "$INFRA_ROOT"/config/*.env 2>/dev/null
chmod 644 "$INFRA_ROOT"/config/runtime/*.yaml "$INFRA_ROOT"/config/runtime/*.yml 2>/dev/null
chmod 644 "$INFRA_ROOT"/config/runtime/*.txt 2>/dev/null
chmod 644 "$INFRA_ROOT"/config/runtime/groups/*.members 2>/dev/null

# =============================================================================
# Shared Libraries (755)
# =============================================================================

# lib directory must be traversable for LD_PRELOAD to work
chmod 755 "$INFRA_ROOT"/lib 2>/dev/null
# .so files must be world-readable+executable for dynamic linker
chmod 755 "$INFRA_ROOT"/lib/*.so 2>/dev/null

# =============================================================================
# AIME ML Containers Submodule (restricted)
# =============================================================================

chown -R datasciencelab:docker "$INFRA_ROOT"/aime-ml-containers/ 2>/dev/null
chmod 750 "$INFRA_ROOT"/aime-ml-containers/ 2>/dev/null
chmod 640 "$INFRA_ROOT"/aime-ml-containers/* 2>/dev/null

# =============================================================================
# State Directories (/var/lib/ds01/)
# =============================================================================

# Root state directory (775 root:docker)
mkdir -p /var/lib/ds01
chown root:docker /var/lib/ds01
chmod 775 /var/lib/ds01

# bare-metal-grants: users need to stat own grant file (711 = traverse without listing)
mkdir -p /var/lib/ds01/bare-metal-grants
chmod 711 /var/lib/ds01/bare-metal-grants

# rate-limits: users write own denial state (1777 = world-writable with sticky)
mkdir -p /var/lib/ds01/rate-limits
chmod 1777 /var/lib/ds01/rate-limits

# =============================================================================
# Log Directory (/var/log/ds01/)
# =============================================================================

mkdir -p /var/log/ds01
chown root:docker /var/log/ds01
chmod 775 /var/log/ds01

# events.jsonl: must be group-writable so non-root users can log events
if [ -f /var/log/ds01/events.jsonl ]; then
    chown root:docker /var/log/ds01/events.jsonl
    chmod 664 /var/log/ds01/events.jsonl
else
    touch /var/log/ds01/events.jsonl
    chown root:docker /var/log/ds01/events.jsonl
    chmod 664 /var/log/ds01/events.jsonl
fi

# =============================================================================
# Cleanup
# =============================================================================

# Clean stale __pycache__ files (can cause import failures for non-root users)
echo -e "${DIM}Cleaning stale __pycache__ files...${NC}"
find "$INFRA_ROOT"/scripts -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
