#!/bin/bash
# DS01 Message of the Day — Notification display
# Shows announcements from /etc/ds01-motd if file exists and is non-empty.
# Deployed to /etc/profile.d/ds01-motd.sh

# Only show for interactive shells
[[ $- == *i* ]] || return

MOTD_FILE="/etc/ds01-motd"

# Skip if no announcements
[[ -f "$MOTD_FILE" ]] || return
[[ -s "$MOTD_FILE" ]] || return

_Y='\033[0;33m'
_D='\033[2m'
_NC='\033[0m'

echo ""
echo -e "  ${_Y}┌─ Announcements ──────────────────────────────────┐${_NC}"
while IFS= read -r line; do
    printf "  ${_Y}│${_NC}  %-48s${_Y}│${_NC}\n" "$line"
done < "$MOTD_FILE"
echo -e "  ${_Y}└──────────────────────────────────────────────────┘${_NC}"

unset _Y _D _NC MOTD_FILE
