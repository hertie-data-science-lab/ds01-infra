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

# Block-character banner
echo -e "
  ${_B}██████╗ ███████╗ ██████╗  ██╗${_NC}
  ${_B}██╔══██╗██╔════╝██╔═████╗███║${_NC}
  ${_B}██║  ██║███████╗██║██╔██║╚██║${_NC}   Hertie Data Science Lab
  ${_B}██║  ██║╚════██║████╔╝██║ ██║${_NC}   GPU-enabled Compute Server
  ${_B}██████╔╝███████║╚██████╔╝ ██║${_NC}
  ${_B}╚═════╝ ╚══════╝ ╚═════╝  ╚═╝${_NC}
"

# Check if user has aggregate limits (null = admin/unlimited)
_agg=$(python3 "$_SCRIPTS/docker/get_resource_limits.py" "$_username" --aggregate 2>/dev/null)

if [[ "$_agg" == "null" || -z "$_agg" ]]; then
    # Admin / unlimited user
    echo -e " Welcome ${_B}${_username}${_NC} (${_group}) — ${_GREEN}unlimited resources${_NC}"
else
    # Regular user — build static quota line
    _gpus=$(python3 "$_SCRIPTS/docker/get_resource_limits.py" "$_username" --max-gpus 2>/dev/null || echo "?")
    # Detect GPU topology: MIG slots vs physical GPUs
    _gpu_listing=$(nvidia-smi -L 2>/dev/null) || _gpu_listing=""
    _mig_count=$(echo "$_gpu_listing" | grep -c "MIG") || _mig_count=0
    _phys_count=$(echo "$_gpu_listing" | grep -c "^GPU") || _phys_count=0
    _gpu_unit="GPUs"
    _sys_total=$_phys_count
    if [[ $_mig_count -gt 0 ]]; then
        _gpu_unit="MIG slots"
        _sys_total=$_mig_count
    fi
    # Cap to actual hardware (only if we detected hardware)
    if [[ $_sys_total -gt 0 ]] && [[ "$_gpus" =~ ^[0-9]+$ ]] && [[ $_gpus -gt $_sys_total ]]; then
        _gpus=$_sys_total
    fi
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
    echo -e " Quota: ${_gpu_unit} ${_B}${_gpus}${_NC}, Memory ${_B}${_mem_display}${_NC}, CPUs ${_B}${_cpus}${_NC}, Containers ${_B}${_containers}${_NC}"
fi

# Pending alerts from resource monitoring
_alerts_file="/var/lib/ds01/alerts/${_username}.json"
if [ -f "$_alerts_file" ]; then
    _alert_summary=$(python3 -c "
import json, sys
try:
    alerts = json.load(open('$_alerts_file'))
    if not alerts:
        sys.exit(0)
    for a in alerts:
        severity = 'ALERT' if 'reached' in a.get('type', '') else 'WARNING'
        print(f'  [{severity}] {a[\"message\"]}')
except:
    pass
" 2>/dev/null)
    if [ -n "$_alert_summary" ]; then
        echo -e " ${_B}\033[0;31mPending alerts:\033[0m"
        echo "$_alert_summary"
        echo ""
    fi
fi

echo -e " ${_D}Useful commands: user-setup · project-launch · container deploy${_NC}"
echo -e " ${_D}                container retire · check-limits · aliases${_NC}"
echo ""

# Cleanup
unset _B _D _GREEN _NC _username _group _SCRIPTS _agg _gpus _containers _mem _cpus _mem_display _gpu_listing _mig_count _phys_count _gpu_unit _sys_total _alerts_file _alert_summary
