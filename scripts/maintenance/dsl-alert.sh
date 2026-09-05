#!/usr/bin/env bash
# dsl-alert.sh <unit> — post a failed unit's last journal lines to Teams and mail.
#
# Wired in as `OnFailure=dsl-alert@%n.service`. Exists because the box has no
# shared alert helper: config-watchdog.sh keeps its own alert_teams() and this
# resolves the same webhook (DS01_TEAMS_WEBHOOK_URL, else the prod-only,
# git-ignored config/runtime/teams-webhook-url.txt).
#
# Two independent channels, each optional and each unable to fail the alerter —
# an alerter must not become the outage:
#   Teams  a webhook, when one is configured
#   mail   dsl-alert-mail.py through Microsoft Graph, when DSL_ALERT_TO is set
#          (with the rest of GRAPH_* — see /etc/dsl-alert-mail.env in
#          dsl-alert@.service, provisioning in docs/admin/maintenance.md)
# With neither configured the alert is a journal-only no-op.
#
# Only post journals of units that keep student data out of their logs.

set -euo pipefail

unit=${1:?usage: dsl-alert.sh <unit>}

INFRA_ROOT=$(dirname "$(dirname "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")")")

url="${DS01_TEAMS_WEBHOOK_URL:-}"
if [ -z "$url" ] && [ -r "$INFRA_ROOT/config/runtime/teams-webhook-url.txt" ]; then
    url=$(head -1 "$INFRA_ROOT/config/runtime/teams-webhook-url.txt" | tr -d '[:space:]')
fi
# Accept only a real URL: the tracked teams-webhook-url.txt ships a placeholder
# (PASTE_LOGIC_AZURE_URL_HERE) that config-watchdog.sh's "PLACEHOLDER*" test does
# not catch, and POSTing to a non-URL just fails noisily every tick.
case "$url" in
    https://*) ;;
    *) url= ;;
esac

mail_to="${DSL_ALERT_TO:-}"

if [ -z "$url" ] && [ -z "$mail_to" ]; then
    echo "no alert channel configured; $unit failure not posted"
    exit 0
fi

detail=$(journalctl -u "$unit" -n 20 --no-pager -o short-iso 2>/dev/null || true)

if [ -n "$url" ]; then
    text="$unit failed on $(hostname)."$'\n\n```\n'"$detail"$'\n```'
    payload=$(python3 -c 'import json,sys; print(json.dumps({"text": sys.argv[1]}))' "$text") ||
        payload=
    if [ -n "$payload" ]; then
        curl -sS -m 10 -X POST -H "Content-Type: application/json" -d "$payload" "$url" >/dev/null ||
            echo "WARNING: Teams alert POST failed for $unit"
    else
        echo "WARNING: Teams alert payload build failed for $unit"
    fi
fi

if [ -n "$mail_to" ]; then
    # Body on stdin, not argv: /proc here is world-readable, so a journal tail on a
    # command line is a journal tail in `ps`.
    printf '%s\n' "$detail" |
        python3 "$INFRA_ROOT/scripts/maintenance/dsl-alert-mail.py" "[ds01] $unit failed" ||
        echo "WARNING: mail alert failed for $unit"
fi
