#!/bin/bash
# DS01 Login Greeting
# Shows ASCII banner + static quota summary at SSH login.
# Deployed to /etc/profile.d/ via deploy.sh.

# Skip for non-interactive shells
[[ $- == *i* ]] || return 0

# Colour codes
_B='\033[1m'
_D='\033[2m'
_GREEN='\033[0;32m'
_NC='\033[0m'

_username="$(whoami)"
_SCRIPTS="/opt/ds01-infra/scripts"

# Get user group
_group=$(python3 "$_SCRIPTS/docker/get_resource_limits.py" "$_username" --group 2>/dev/null || echo "unknown")

# Hardcoded figlet banner (font: small)
echo -e "
  ${_B}____  ____   ___  _${_NC}
  ${_B}|  _ \\/ ___| / _ \\/ |${_NC}
  ${_B}| | | \\___ \\| | | | |${_NC}   GPU Server
  ${_B}| |_| |___) | |_| | |${_NC}   Hertie Data Science Lab
  ${_B}|____/|____/ \\___/|_|${_NC}
"

# Check if user has aggregate limits (null = admin/unlimited)
_agg=$(python3 "$_SCRIPTS/docker/get_resource_limits.py" "$_username" --aggregate 2>/dev/null)

if [[ "$_agg" == "null" || -z "$_agg" ]]; then
    # Admin / unlimited user
    echo -e " Welcome ${_B}${_username}${_NC} (${_group}) — ${_GREEN}unlimited resources${_NC}"
else
    # Regular user — build static quota line
    _gpus=$(python3 "$_SCRIPTS/docker/get_resource_limits.py" "$_username" --max-gpus 2>/dev/null || echo "?")
    _containers=$(python3 "$_SCRIPTS/docker/get_resource_limits.py" "$_username" --max-containers 2>/dev/null || echo "?")

    # Parse memory and CPUs from aggregate JSON
    _mem=$(echo "$_agg" | python3 -c "import json,sys; print(json.load(sys.stdin).get('memory_max','?'))" 2>/dev/null || echo "?")
    _cpus=$(echo "$_agg" | python3 -c "
import json, sys
agg = json.load(sys.stdin)
q = agg.get('cpu_quota', '?')
if isinstance(q, str) and q.endswith('%'):
    print(int(q.rstrip('%')) // 100)
else:
    print(q)
" 2>/dev/null || echo "?")

    # Strip trailing G from memory if present, then re-add with space
    _mem_display="$_mem"
    if [[ "$_mem" =~ ^[0-9]+G$ ]]; then
        _mem_display="${_mem%G} GB"
    fi

    echo -e " Welcome ${_B}${_username}${_NC} (${_group})"
    echo -e " Quota: GPUs ${_B}${_gpus}${_NC}, Memory ${_B}${_mem_display}${_NC}, CPUs ${_B}${_cpus}${_NC}, Containers ${_B}${_containers}${_NC}"
fi

echo ""
echo -e " ${_D}Useful commands: user-setup · project-launch · container deploy${_NC}"
echo -e " ${_D}                container retire · check-limits · aliases${_NC}"
echo ""

# Cleanup
unset _B _D _GREEN _NC _username _group _SCRIPTS _agg _gpus _containers _mem _cpus _mem_display
