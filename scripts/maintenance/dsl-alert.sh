#!/usr/bin/env bash
# dsl-alert.sh <unit> — post a failed unit's last journal lines to Teams.
#
# Wired in as `OnFailure=dsl-alert@%n.service`. Exists because the box has no
# shared alert helper: config-watchdog.sh keeps its own alert_teams() and this
# resolves the same webhook (DS01_TEAMS_WEBHOOK_URL, else the prod-only,
# git-ignored config/runtime/teams-webhook-url.txt). A missing webhook is a
# journal-only no-op, never a failure — an alerter must not become the outage.
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
    *)
        echo "no Teams webhook configured; $unit failure not posted"
        exit 0
        ;;
esac

detail=$(journalctl -u "$unit" -n 20 --no-pager -o short-iso 2>/dev/null || true)
text="$unit failed on $(hostname)."$'\n\n```\n'"$detail"$'\n```'

payload=$(python3 -c 'import json,sys; print(json.dumps({"text": sys.argv[1]}))' "$text")
curl -sS -m 10 -X POST -H "Content-Type: application/json" -d "$payload" "$url" >/dev/null ||
    echo "WARNING: Teams alert POST failed for $unit"
