#!/bin/bash
# Restore NVIDIA device permissions to defaults
# Run this after switching from device-permission to CUDA_VISIBLE_DEVICES approach

set -e

echo "Restoring NVIDIA device permissions to defaults..."
echo ""

# 1. Restore original ub-device-create
if [ -f "/usr/sbin/ub-device-create.original" ]; then
    echo "Restoring original ub-device-create..."
    mv /usr/sbin/ub-device-create.original /usr/sbin/ub-device-create
    echo "✓ Restored /usr/sbin/ub-device-create"
else
    echo "! ub-device-create.original not found (already restored or not backed up)"
fi

# 2. Remove udev rules
if [ -f "/etc/udev/rules.d/99-ds01-nvidia.rules" ]; then
    echo "Removing nvidia udev rules..."
    rm -f /etc/udev/rules.d/99-ds01-nvidia.rules
    udevadm control --reload-rules 2>/dev/null || true
    echo "✓ Removed /etc/udev/rules.d/99-ds01-nvidia.rules"
fi

# 3. Remove modprobe configuration
if [ -f "/etc/modprobe.d/nvidia-permissions.conf" ]; then
    echo "Removing NVIDIA kernel module configuration..."
    rm -f /etc/modprobe.d/nvidia-permissions.conf
    echo "✓ Removed /etc/modprobe.d/nvidia-permissions.conf"
    echo "! Note: Requires nvidia module reload or reboot to take effect"
fi

# 4. Reset device permissions to defaults (0666 root:root)
echo "Resetting device permissions to defaults (0666 root:root)..."
for dev in /dev/nvidia0 /dev/nvidia1 /dev/nvidia2 /dev/nvidia3 \
           /dev/nvidiactl /dev/nvidia-modeset /dev/nvidia-uvm \
           /dev/nvidia-uvm-tools /dev/nvidia-nvswitchctl; do
    if [ -c "$dev" ]; then
        chown root:root "$dev" 2>/dev/null || true
        chmod 0666 "$dev" 2>/dev/null || true
        echo "  ✓ Reset $dev"
    fi
done

# 5. Remove nvidia-smi cache (legacy)
if [ -f "/var/lib/ds01/gpu-inventory.cache" ]; then
    echo "Removing nvidia-smi cache (no longer needed)..."
    rm -f /var/lib/ds01/gpu-inventory.cache
    echo "✓ Removed /var/lib/ds01/gpu-inventory.cache"
fi

echo ""
echo "✓ NVIDIA device permissions restored to defaults"
echo ""
echo "Next steps:"
echo "  1. Run: sudo deploy"
echo "  2. Users should logout and login to get CUDA_VISIBLE_DEVICES=\"\" in environment"
echo "  3. Test: python3 -c 'import torch; print(torch.cuda.is_available())' → should be False"
echo "  4. Test: nvidia-smi -L → should work and list GPUs"
echo "  5. Test: container deploy → should succeed"
