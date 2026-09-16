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

# The prod paths below default to prod and are overridable from the environment. Not
# configurability for its own sake: the drift branch restores a live config file and is
# the only thing that alerts, so tests/unit/test_config_watchdog.py rehearses it against a
# temporary tree. Nothing on the box sets any of them.

SCRIPT_PATH="$(readlink -f "${BASH_SOURCE[0]}")"
SCRIPT_DIR="$(dirname "$SCRIPT_PATH")"
INFRA_ROOT="$(dirname "$(dirname "$SCRIPT_DIR")")"

CONFIG_FILE="$INFRA_ROOT/config/runtime/resource-limits.yaml"
CONFIG_BACKUP="$CONFIG_FILE.bak-runtime-test"
CRON_FILE="${CRON_FILE:-/etc/cron.d/ds01-maintenance}"
CRON_DISABLED="$CRON_FILE.disabled-by-test"
LOG_FILE="${LOG_FILE:-/var/log/ds01/config-watchdog.log}"

mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] config-watchdog: $1" | tee -a "$LOG_FILE"
}

# alert <summary> [detail] — tell a human that config drifted, on two independent
# channels, exactly as scripts/maintenance/dsl-alert.sh does it:
#
#   Teams  a webhook (env DS01_TEAMS_WEBHOOK_URL, else the prod-only, git-ignored
#          config/runtime/teams-webhook-url.txt)
#   mail   dsl-alert-mail.py through Microsoft Graph
#
# Either may be absent and neither may fail the watchdog — this alert rides on the
# restore of a config file, and an alerter must never become the outage.
#
# Drift was Teams-only until the mail channel existed, and Teams was never
# provisioned: the webhook file on prod holds PASTE_LOGIC_AZURE_URL_HERE. Every
# drift alert since has gone nowhere.
alert() {
    local summary=$1 detail=${2:-} url="${DS01_TEAMS_WEBHOOK_URL:-}"
    if [ -z "$url" ] && [ -r "$INFRA_ROOT/config/runtime/teams-webhook-url.txt" ]; then
        url=$(head -1 "$INFRA_ROOT/config/runtime/teams-webhook-url.txt" | tr -d '[:space:]')
    fi
    # Accept only a real URL. The old test rejected `PLACEHOLDER*`, which is not what
    # the shipped placeholder says, so this POSTed to a non-URL and logged a WARNING
    # on every drift instead of being the intended no-op.
    case "$url" in
        https://*) ;;
        *) url= ;;
    esac

    local text="$summary"
    [ -n "$detail" ] && text="$summary"$'\n\n```\n'"$detail"$'\n```'

    if [ -n "$url" ]; then
        local payload
        payload=$(python3 -c 'import json,sys; print(json.dumps({"text": sys.argv[1]}))' "$text" 2>/dev/null) || payload=
        if [ -n "$payload" ]; then
            curl -sS -m 10 -X POST -H "Content-Type: application/json" -d "$payload" "$url" >/dev/null 2>&1 ||
                log "WARNING: Teams drift alert POST failed"
        else
            log "WARNING: Teams drift alert payload build failed"
        fi
    fi

    # The mailer reads /etc/dsl-alert-mail.env itself — this runs from cron, which
    # inherits nothing from dsl-alert@.service's EnvironmentFile. Ask first, so a box
    # with no mail provisioning stays silent rather than logging a WARNING about a
    # channel nobody asked for.
    if [ -n "${DSL_ALERT_TO:-}" ] || [ -r "${DSL_ALERT_ENV_FILE:-/etc/dsl-alert-mail.env}" ]; then
        # Body on stdin, not argv: /proc here is world-readable, so a diff on a command
        # line is a diff in `ps`.
        printf '%s\n' "$text" |
            python3 "$INFRA_ROOT/scripts/maintenance/dsl-alert-mail.py" \
                "[ds01] config drift on $(hostname)" ||
            log "WARNING: mail drift alert failed"
    fi
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
    # Compare live config against the DEPLOYED source of truth. Prod has no .git
    # (detached prod), so read from the staging clone at the deployed SHA, AND
    # as the checkout owner — root would hit git's dubious-ownership guard and
    # silently disable this check.
    #
    # Emergency path: an on-box hand-edit to resource-limits.yaml is reverted
    # here (01:00 daily) or at the next sync UNLESS a PR lands the change first.
    CURRENT_SHA_FILE="${CURRENT_SHA_FILE:-/var/lib/ds01/deploy/current-sha}"
    STAGING="${STAGING:-/opt/ds01-staging}"
    OWNER="${OWNER:-datasciencelab}"

    sha=$(cat "$CURRENT_SHA_FILE" 2>/dev/null || true)
    if [ -z "$sha" ]; then
        log "No deployed SHA at $CURRENT_SHA_FILE, skipping integrity check"
        exit 0
    fi

    git_config=$(runuser -u "$OWNER" -- git -C "$STAGING" show "$sha:config/runtime/resource-limits.yaml" 2>/dev/null) || {
        log "WARNING: Could not read reference config from staging at $sha, skipping integrity check"
        exit 0
    }

    live_hash=$(sha256sum "$CONFIG_FILE" | cut -d' ' -f1)
    git_hash=$(echo "$git_config" | sha256sum | cut -d' ' -f1)

    if [ "$live_hash" != "$git_hash" ]; then
        log "WARNING: Config has drifted from deployed source ($sha). Alerting + restoring."
        # Alert (with a diff) in ADDITION to restoring, so silent drift is visible.
        drift_diff=$(diff <(echo "$git_config") "$CONFIG_FILE" 2>/dev/null | head -40 || true)
        alert "DS01 config drift on $(hostname): config/runtime/resource-limits.yaml differs from deployed $sha and is being restored." "$drift_diff"
        echo "$git_config" >"$CONFIG_FILE"
        logger -t ds01-watchdog "Config drift detected and restored from deployed SHA $sha"
    fi
fi
