#!/bin/bash
# check-mig-topology.sh - Detect MIG topology mismatches and restart DCGM if needed
#
# Runs periodically (via cron) to ensure DCGM stays in sync with nvidia-smi
# after MIG partition changes.
#
# Usage: check-mig-topology.sh [--dry-run]

set -e

EXPORTER_URL="${DS01_EXPORTER_URL:-http://localhost:9101/metrics}"
COMPOSE_DIR="/opt/ds01-infra/monitoring"
LOG_FILE="/var/log/ds01/mig-topology-sync.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

DRY_RUN=false
if [[ "$1" == "--dry-run" ]]; then
    DRY_RUN=true
fi

# Query the mapping status metric
STATUS=$(curl -sf "$EXPORTER_URL" 2>/dev/null | grep -E '^ds01_mig_mapping_status' | awk '{print $2}' || echo "")

if [[ -z "$STATUS" ]]; then
    # Metric not available - exporter may be down or metric not yet implemented
    exit 0
fi

if [[ "$STATUS" == "1" ]]; then
    # All good - topology in sync
    exit 0
fi

# Mismatch detected - need to restart DCGM
log "MIG topology mismatch detected (status=$STATUS)"

# Extract mapped/unmapped counts from labels
DETAILS=$(curl -sf "$EXPORTER_URL" 2>/dev/null | grep -E '^ds01_mig_mapping_status' | head -1)
log "Details: $DETAILS"

if [[ "$DRY_RUN" == "true" ]]; then
    log "DRY-RUN: Would restart dcgm-exporter"
    exit 0
fi

log "Restarting dcgm-exporter to sync with new MIG topology..."
cd "$COMPOSE_DIR"
docker compose restart dcgm-exporter

# Wait for DCGM to come back up
sleep 10

# Verify the fix
NEW_STATUS=$(curl -sf "$EXPORTER_URL" 2>/dev/null | grep -E '^ds01_mig_mapping_status' | awk '{print $2}' || echo "unknown")
log "After restart: status=$NEW_STATUS"

if [[ "$NEW_STATUS" == "1" ]]; then
    log "SUCCESS: MIG topology now in sync"
else
    log "WARNING: Topology still mismatched after DCGM restart - manual intervention may be needed"
fi
