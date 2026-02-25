#!/bin/bash
# DS01 Message of the Day — Login notice and announcement display
# Shows GPU access policy notice once per day.
# Shows announcements from /etc/ds01-motd if file exists and is non-empty.
# Deployed to /etc/profile.d/ds01-motd.sh

# Only show for interactive shells
[[ $- == *i* ]] || return

# Only show GPU policy notice once per day per user
_DS01_MOTD_STATE="/tmp/.ds01-motd-$(whoami)-$(date +%Y%m%d)"
if [[ ! -f "$_DS01_MOTD_STATE" ]]; then
    touch "$_DS01_MOTD_STATE" 2>/dev/null || true
    echo ""
    echo "  DS01 GPU Server"
    echo "  ───────────────────────────────────────"
    echo "  GPU access is container-only by default."
    echo "  Quick start: container deploy my-project"
    echo "  Help:        help"
    echo ""
fi
unset _DS01_MOTD_STATE

# Show admin announcements (if any)
MOTD_FILE="/etc/ds01-motd"
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
