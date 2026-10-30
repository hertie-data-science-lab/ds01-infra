#!/bin/bash
# DS01 Maintenance Window Notice
# Warns users at login during the 7 days before the monthly update window
# (last Friday of each month, 10:00-10:30 server local time).
# Deployed to /etc/profile.d/ via deploy.sh.

# Only show for interactive shells
[[ $- == *i* ]] || return 0

_now=$(date +%s)
_today=$(date -d "@$_now" +%Y-%m-%d)

# Last Friday of the current month (date +%u: Mon=1 .. Fri=5 .. Sun=7)
_last_day=$(date -d "$(date -d "$_today" +%Y-%m-01) +1 month -1 day" +%Y-%m-%d)
_offset=$(( ($(date -d "$_last_day" +%u) - 5 + 7) % 7 ))
_window_day=$(date -d "$_last_day -$_offset days" +%Y-%m-%d)

_notice_from=$(date -d "$_window_day -7 days" +%s)
_window_start=$(date -d "$_window_day 10:00" +%s)
_window_end=$(date -d "$_window_day 10:30" +%s)

# Once this month's window has passed, the next one is 3+ weeks away
if (( _now >= _notice_from && _now < _window_end )); then
    _Y='\033[0;33m'
    _NC='\033[0m'
    if (( _now >= _window_start )); then
        _headline="Maintenance in progress until 10:30"
    else
        _headline="Maintenance: $(date -d "$_window_day" '+%a %-d %b'), 10:00-10:30"
    fi
    echo ""
    echo -e "  ${_Y}┌─ Scheduled maintenance ──────────────────────────┐${_NC}"
    for _line in \
        "$_headline" \
        "" \
        "System updates run on the last Friday of each" \
        "month. Running containers may be stopped and" \
        "the server may reboot. Save your work and" \
        "checkpoint long-running jobs beforehand."; do
        printf "  ${_Y}│${_NC}  %-48s${_Y}│${_NC}\n" "$_line"
    done
    echo -e "  ${_Y}└──────────────────────────────────────────────────┘${_NC}"
    unset _Y _NC _headline _line
fi

unset _now _today _last_day _offset _window_day _notice_from _window_start _window_end
