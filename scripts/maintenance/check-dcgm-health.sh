#!/bin/bash
# check-dcgm-health.sh - Auto-restart DCGM exporter if unresponsive
#
# Checks if DCGM metrics endpoint is responding. If not, restarts the container.
# Run via cron every 5 minutes for quick recovery.

set -e

DCGM_URL="http://127.0.0.1:9400/metrics"
COMPOSE_DIR="/opt/ds01-infra/monitoring"
LOG_FILE="/var/log/ds01/dcgm-health.log"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $*" | tee -a "$LOG_FILE"
}

# Check if DCGM is responding (timeout 10s)
if wget -q --timeout=10 -O /dev/null "$DCGM_URL" 2>/dev/null; then
    # Healthy - exit silently
    exit 0
fi

# DCGM not responding
log "DCGM exporter not responding at $DCGM_URL"

# Check if container exists
CONTAINER_STATUS=$(docker inspect -f '{{.State.Status}}' ds01-dcgm-exporter 2>/dev/null || echo "missing")
log "Container status: $CONTAINER_STATUS"

if [[ "$CONTAINER_STATUS" == "missing" ]]; then
    log "Container missing - starting via docker compose"
    cd "$COMPOSE_DIR"
    docker compose up -d dcgm-exporter
elif [[ "$CONTAINER_STATUS" == "running" ]]; then
    log "Container running but unresponsive - restarting"
    docker restart ds01-dcgm-exporter
else
    log "Container in state '$CONTAINER_STATUS' - starting"
    docker start ds01-dcgm-exporter
fi

# Wait and verify
sleep 15

if wget -q --timeout=10 -O /dev/null "$DCGM_URL" 2>/dev/null; then
    log "SUCCESS: DCGM exporter recovered"
else
    log "WARNING: DCGM still not responding after restart"
fi
