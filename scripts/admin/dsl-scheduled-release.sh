#!/usr/bin/env bash
# dsl-scheduled-release.sh — punctual driver + outside-GitHub observer for the
# teaching toolkit's `Scheduled release` workflow. Run by
# dsl-scheduled-release.timer, never by hand except to test one tick.
#
# WHY a second driver: that workflow carries every deadline-sensitive action in
# every course org (materials deploys, handouts, submission freezes, autograde,
# solution pushes) and rides one GitHub Actions cron, which GitHub delivers
# best-effort — a small percentage of fires, with gaps of hours. ds01 fires the
# same workflow over the REST API on a timer that actually keeps time.
#
# WHY an observer: on GitHub every step of that workflow, the "workflow is
# failing" issue step included, authenticates with the same bot token as the
# work. A revoked token is therefore a silent total outage. Reading each org's
# recent runs from here is the only signal that survives it.
#
# PII: the journal of this unit is read by dsl-alert.sh and posted to Teams, so
# only org names and HTTP status codes are ever printed. API response bodies can
# carry student names and are parsed but never logged.

set -euo pipefail

readonly API="https://api.github.com"
# Mirrors the toolkit's own org enumeration (dsl_course/list_orgs.py): hub repos
# are marked with this topic, and 100 is GitHub's practical search page.
readonly TOPIC="dsl-course-hub"
readonly SEARCH_LIMIT=100
# One tick is 15 min; 60 min means at least three consecutive misses by BOTH
# drivers before we call an org silent.
readonly SILENT_AFTER_MIN=60

: "${GH_TOKEN:?GH_TOKEN unset (expected from /etc/dsl-scheduled-release.env)}"

tmp=$(mktemp -d)
trap 'rm -rf "$tmp"' EXIT

dispatched=0
ok=0
pruned=0
failing=0
silent=0
failure=0

# dispatch <org> — POST the repository_dispatch, print the HTTP status only.
# curl (not `gh api`) so the status code is exact and no body is ever surfaced.
dispatch() {
    curl -sS -m 30 -o /dev/null -w '%{http_code}' \
        -X POST \
        -H "Authorization: Bearer $GH_TOKEN" \
        -H "Accept: application/vnd.github+json" \
        "$API/repos/$1/.github/dispatches" \
        -d '{"event_type":"scheduled-release","client_payload":{"driver":"ds01"}}'
}

# observe <org> — judge the org's recent runs; marks failure and bumps counters.
observe() {
    local org=$1 body="$tmp/runs.json" code newest age
    code=$(curl -sS -m 30 -o "$body" -w '%{http_code}' \
        -H "Authorization: Bearer $GH_TOKEN" \
        -H "Accept: application/vnd.github+json" \
        "$API/repos/$org/.github/actions/workflows/scheduled-release.yml/runs?per_page=5" || true)
    if [ "$code" != 200 ]; then
        # 404 here means the hub repo exists (we just dispatched into it) but the
        # workflow does not — a real outage, not a lagging search index.
        echo "observe-failed $org ($code)"
        failure=1
        return
    fi

    if [ "$(jq '[.workflow_runs[] | select(.status == "completed")][:3]
                | if length == 3 and all(.conclusion == "failure") then 1 else 0 end' "$body")" = 1 ]; then
        echo "failing $org"
        failing=$((failing + 1))
        failure=1
    fi

    newest=$(jq -r '.workflow_runs[0].created_at // empty' "$body")
    if [ -z "$newest" ]; then
        echo "silent $org (no runs)"
        silent=$((silent + 1))
        failure=1
        return
    fi
    age=$((($(date +%s) - $(date -d "$newest" +%s)) / 60))
    if [ "$age" -gt "$SILENT_AFTER_MIN" ]; then
        echo "silent $org (${age}m since newest run)"
        silent=$((silent + 1))
        failure=1
    fi
}

# ── Enumerate the course orgs ────────────────────────────────────────────────
# `gh` honours GH_TOKEN, so the search runs as the bot like everything else.
gh search repos --topic "$TOPIC" --limit "$SEARCH_LIMIT" --json name,owner >"$tmp/search.json"

# Truncation guard: at the page limit we cannot know which orgs were cut, and
# driving a subset silently is worse than not driving at all.
if [ "$(jq 'length' "$tmp/search.json")" -ge "$SEARCH_LIMIT" ]; then
    echo "topic $TOPIC returned the $SEARCH_LIMIT-result search limit; results may be truncated"
    exit 1
fi

orgs=()
while IFS= read -r org; do
    orgs+=("$org")
done < <(jq -r '.[] | select(.name == ".github") | .owner.login' "$tmp/search.json" | sort -u)

if [ "${#orgs[@]}" -eq 0 ]; then
    echo "no .github hub repos found for topic $TOPIC"
    exit 1
fi

# ── Drive and observe each org ───────────────────────────────────────────────
for org in "${orgs[@]}"; do
    dispatched=$((dispatched + 1))
    code=$(dispatch "$org" || true)

    # A 5xx is GitHub, not us: one retry before it counts against the tick.
    if [[ $code =~ ^5 ]]; then
        echo "retry $org (dispatch $code)"
        sleep 5
        code=$(dispatch "$org" || true)
    fi

    case "$code" in
        204)
            ok=$((ok + 1))
            observe "$org"
            ;;
        404)
            # The search index lags org deletion; a gone org is not a fault.
            echo "prune $org"
            pruned=$((pruned + 1))
            ;;
        401 | 403)
            echo "token-dead $org (dispatch $code)"
            failure=1
            ;;
        *)
            echo "dispatch-failed $org ($code)"
            failure=1
            ;;
    esac
done

echo "dispatched=$dispatched ok=$ok pruned=$pruned failing=$failing silent=$silent"

# Non-zero iff something needs a human, so OnFailure alerts once per bad tick.
exit "$failure"
