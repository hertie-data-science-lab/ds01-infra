#!/bin/bash
# DS01 GPU Awareness Layer
# Prevents direct host GPU access from PyTorch/CUDA applications.
# Use containers for GPU workloads instead.
#
# Sets CUDA_VISIBLE_DEVICES="" which makes torch.cuda.is_available() return False
# while keeping nvidia-smi functional for system tools and GPU allocation.
#
# Override mechanism (bare-metal GPU access):
#   - Permanently exempt users listed in resource-limits.yaml bare_metal_access.exempt_users
#   - Temporary/permanent grants via: sudo bare-metal-access grant <user> [duration]
#   - Grant state stored in /var/lib/ds01/bare-metal-grants/<user>.json
#
# All docker users are in the video group (required for nvidia-smi / GPU allocator).
# Video group does NOT grant bare-metal CUDA access — only grant files do.
#
# NVIDIA Container Runtime automatically sets CUDA_VISIBLE_DEVICES inside containers,
# so this host-level setting does not affect containerised workloads.
#
# Standard HPC approach used by SLURM and other cluster managers.

# Skip for non-interactive shells (cron jobs, systemd services, scripts)
[[ $- == *i* ]] || return 0

# Check bare-metal access grant file (created by: sudo bare-metal-access grant <user>)
_ds01_grant_file="/var/lib/ds01/bare-metal-grants/$(whoami).json"
if [ -f "$_ds01_grant_file" ]; then
    unset _ds01_grant_file
    return 0
fi
unset _ds01_grant_file

# Check permanently exempt users from config (fast grep, no python)
_ds01_user="$(whoami)"
if grep -qx "  - ${_ds01_user}" /opt/ds01-infra/config/runtime/resource-limits.yaml 2>/dev/null; then
    unset _ds01_user
    return 0
fi
unset _ds01_user

# Note: video group is for nvidia-smi query access (all docker users).
# It does NOT grant bare-metal compute — only grant files and exempt_users do.

export CUDA_VISIBLE_DEVICES=""

# LD_PRELOAD notice: intercepts cuInit() to show a message when CUDA init fails
# Hooks cuInit (Driver API) only when it FAILS, so it doesn't fire on successful availability probes
# Always-on — the failure check ensures notice only fires on blocked compute attempts
_ds01_notice="/opt/ds01-infra/lib/libds01_gpu_notice.so"
if [ -r "$_ds01_notice" ]; then
    export LD_PRELOAD="${_ds01_notice}${LD_PRELOAD:+:$LD_PRELOAD}"
fi
unset _ds01_notice
