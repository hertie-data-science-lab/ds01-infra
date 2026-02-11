#!/bin/bash
# config-watchdog.sh — Config integrity and test crash recovery
#
# Modes:
#   (no args)   Quick check: recover from test crash artifacts (runs every 5 min)
#   --full      Full check: also verify config matches git HEAD (runs daily)
#
# Test crash artifacts:
#   1. Lowered config values (resource-limits.yaml modified by test fixture)
#   2. Disabled cron (/etc/cron.d/ds01-maintenance.disabled-by-test)
#   3. Backup file (resource-limits.yaml.bak-runtime-test)

set -e

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
INFRA_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

CONFIG_FILE="$INFRA_ROOT/config/runtime/resource-limits.yaml"
CONFIG_BACKUP="$CONFIG_FILE.bak-runtime-test"
CRON_FILE="/etc/cron.d/ds01-maintenance"
CRON_DISABLED="/etc/cron.d/ds01-maintenance.disabled-by-test"
LOG_FILE="/var/log/ds01/config-watchdog.log"

mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] config-watchdog: $1" | tee -a "$LOG_FILE"
}

restored=false

# --- Quick checks (test crash artifacts) ---

# Check 1: Disabled cron file from crashed test
if [ -f "$CRON_DISABLED" ]; then
    log "WARNING: Found disabled cron file (test crash artifact). Restoring."
    mv "$CRON_DISABLED" "$CRON_FILE"
    restored=true
fi

# Check 2: Leftover config backup from crashed test
if [ -f "$CONFIG_BACKUP" ]; then
    log "WARNING: Found config backup (test crash artifact). Restoring original config."
    cp "$CONFIG_BACKUP" "$CONFIG_FILE"
    rm -f "$CONFIG_BACKUP"
    restored=true
fi

if [ "$restored" = true ]; then
    log "Recovery complete. Production config and cron restored."
    logger -t ds01-watchdog "Recovered from test crash: config and/or cron restored"
fi

# --- Full check (--full flag, daily) ---

if [ "${1:-}" = "--full" ]; then
    # Compare live config against git HEAD (the source of truth)
    git_config=$(git -C "$INFRA_ROOT" show HEAD:config/runtime/resource-limits.yaml 2>/dev/null) || {
        log "WARNING: Could not read config from git HEAD, skipping integrity check"
        exit 0
    }

    live_hash=$(sha256sum "$CONFIG_FILE" | cut -d' ' -f1)
    git_hash=$(echo "$git_config" | sha256sum | cut -d' ' -f1)

    if [ "$live_hash" != "$git_hash" ]; then
        log "WARNING: Config has drifted from git HEAD. Restoring."
        echo "$git_config" > "$CONFIG_FILE"
        logger -t ds01-watchdog "Config drift detected and restored from git HEAD"
    fi
fi
