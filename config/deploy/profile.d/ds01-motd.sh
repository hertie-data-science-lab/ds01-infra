#!/bin/bash
# DS01 Message of the Day
# Deployed to /etc/profile.d/ds01-motd.sh

# Only show for interactive shells
[[ $- == *i* ]] || return

# Only show once per day per user
MOTD_STATE="/tmp/.ds01-motd-$(whoami)-$(date +%Y%m%d)"
[[ -f "$MOTD_STATE" ]] && return
touch "$MOTD_STATE" 2>/dev/null || true

echo ""
echo "  DS01 GPU Server"
echo "  ───────────────────────────────────────"
echo "  GPU access is container-only by default."
echo "  Quick start: container deploy my-project"
echo "  Help:        help"
echo ""
