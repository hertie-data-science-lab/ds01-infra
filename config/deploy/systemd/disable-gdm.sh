#!/bin/bash
# Disable GDM/X on compute servers
# GPU compute servers should not run display managers - they grab all GPUs
#
# Applied: 2026-01-08
# Reason: Xorg was holding /dev/nvidia* preventing MIG reconfiguration
#
# Commands run:
#   sudo systemctl disable gdm
#   sudo systemctl mask gdm
#
# Note: xorg.conf already configured to use ASPeed BMC (not NVIDIA GPUs)
# Location: /etc/X11/xorg.conf

set -e

if systemctl is-enabled gdm &>/dev/null; then
    echo "Disabling GDM..."
    systemctl disable gdm
    systemctl mask gdm
    echo "GDM disabled and masked"
else
    echo "GDM already disabled"
fi
