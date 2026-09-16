#!/usr/bin/env bash
# alarm.sh report|close — keep ONE self-closing issue per alarm, and say whether to mail.
#
# GitHub emails a scheduled run's failure to whoever last touched the cron file, which is
# nobody who reads that mailbox, so an unattended failure here is invisible until somebody
# notices the thing it maintains has stopped happening. The issue is the DURABLE record: it
# survives a mailbox, a second failure comments on it, and a green run closes it. The mail
# beside it (see action.yml) is how the maintainer hears at all.
#
# Both are gated on the `report` output, so a run cannot mail without filing and cannot
# file without mailing: whoever gets the mail can always find the thread it came from.
#
# Shape and reasoning lifted from the teaching toolkit's dsl_course/workflows_render.py,
# which has run this loop in every course org for a year.
#
#   report  file the issue, or comment on the open one if it has been quiet for 6h
#   close   close every open issue with this exact title
#
# Everything comes from the environment: a note is multi-line and an argv is not the place
# for it.
#
#   ALARM_REPO      owner/name the issue lives in
#   ALARM_TITLE     the issue title, and the identity of the alarm
#   ALARM_RUN_URL   the run to link
#   ALARM_NOTE      report only: the body
#   GH_TOKEN        as ever

set -euo pipefail

mode=${1:?usage: alarm.sh report|close}
: "${ALARM_REPO:?ALARM_REPO unset}"
: "${ALARM_TITLE:?ALARM_TITLE unset}"
: "${ALARM_RUN_URL:?ALARM_RUN_URL unset}"

# A failing job fails on EVERY tick while the fault stands. A comment per run buries the
# thread, so comment only once it has been quiet this long.
readonly THROTTLE=21600 # 6h

# The open issues with EXACTLY this title. `--search` is a WORD match, so a search for
# "Deploy is failing" also matches "System CI is failing" once both exist - and the close
# loop would then close the other alarm's open issue on every green run. The search is the
# cheap server-side narrowing; jq is the guard.
open_issues() {
    gh issue list --repo "$ALARM_REPO" --state open \
        --search "$ALARM_TITLE in:title" --json number,title,updatedAt |
        jq -r --arg t "$ALARM_TITLE" '.[] | select(.title == $t) | "\(.number) \(.updatedAt)"'
}

case "$mode" in
    close)
        # No `report` output: a close never mails. Recovery is not news, and the closed
        # issue says so where the failure was reported.
        while read -r number _; do
            [ -n "$number" ] || continue
            gh issue close "$number" --repo "$ALARM_REPO" --comment "Recovered: $ALARM_RUN_URL"
        done < <(open_issues)
        ;;

    report)
        : "${ALARM_NOTE:?ALARM_NOTE unset}"
        # Unguarded, this capture would abort the script on a transient search failure —
        # before the `gh issue create` that is the whole point. No dedupe hit just means a
        # fresh issue.
        existing=$(open_issues | head -1) || true

        if [ -z "$existing" ]; then
            gh issue create --repo "$ALARM_REPO" --title "$ALARM_TITLE" --body "$ALARM_NOTE"
            echo "report=true" >>"$GITHUB_OUTPUT"
            exit 0
        fi

        number=${existing%% *}
        updated=${existing#* }
        # jq and not `date -u -d`, which is GNU-only: the runner has GNU date, a laptop
        # running the tests does not, and jq is already a hard dependency here.
        # An unparseable timestamp reads as the epoch, i.e. "long overdue": the point of
        # the issue is that somebody hears about the failure.
        last=$(jq -rn --arg t "$updated" '$t | fromdateiso8601' 2>/dev/null || echo 0)
        if [ $(($(date -u +%s) - last)) -lt "$THROTTLE" ]; then
            echo "already reported within the last 6h - see issue $number"
            echo "report=false" >>"$GITHUB_OUTPUT"
            exit 0
        fi

        gh issue comment "$number" --repo "$ALARM_REPO" --body "$ALARM_NOTE"
        echo "report=true" >>"$GITHUB_OUTPUT"
        ;;

    *)
        echo "usage: alarm.sh report|close" >&2
        exit 1
        ;;
esac
