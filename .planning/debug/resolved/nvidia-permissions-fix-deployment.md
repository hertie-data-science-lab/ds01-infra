# NVIDIA Device Permissions Fix - Deployment Instructions

## Problem
NVIDIA kernel module creates /dev/nvidia* device files with hardcoded permissions:
- GID: 0 (root) instead of 44 (video)
- Mode: 0666 instead of 0660

This allows any user to access GPU devices directly, bypassing DS01 container-based access control.

## Root Cause
NVIDIA kernel module parameters in `/proc/driver/nvidia/params`:
```
DeviceFileGID: 0
DeviceFileMode: 438 (0o666)
```

## Solution
Set NVIDIA kernel module parameters via `/etc/modprobe.d/nvidia-permissions.conf`:
```
options nvidia NVreg_DeviceFileGID=44 NVreg_DeviceFileMode=432
```

Where:
- 44 = video group GID
- 432 = decimal for 0660 octal

## Deployment Steps

### 1. Deploy Configuration
```bash
sudo deploy
```

This will:
- Copy `config/deploy/modprobe.d/nvidia-permissions.conf` to `/etc/modprobe.d/`
- Show warning that nvidia module reload or reboot is required

### 2. Apply Changes (Choose ONE)

#### Option A: Reboot (RECOMMENDED - safest)
```bash
sudo reboot
```

#### Option B: Reload NVIDIA Module (RISKY - kills all GPU processes)
**Only during maintenance window when no containers are running:**

```bash
# 1. Stop all GPU containers
docker ps --filter "label=ds01.gpu_allocation" -q | xargs -r docker stop

# 2. Stop nvidia-persistenced
sudo systemctl stop nvidia-persistenced

# 3. Unload nvidia modules (in dependency order)
sudo rmmod nvidia_uvm
sudo rmmod nvidia_drm
sudo rmmod nvidia_modeset
sudo rmmod nvidia

# 4. Reload nvidia module (picks up new params from /etc/modprobe.d/)
sudo modprobe nvidia

# 5. Restart nvidia-persistenced
sudo systemctl start nvidia-persistenced
```

### 3. Verify Fix
```bash
# Check kernel module parameters
cat /proc/driver/nvidia/params | grep DeviceFile
# Should show:
#   DeviceFileGID: 44
#   DeviceFileMode: 432

# Check device permissions
ls -l /dev/nvidia0
# Should show: crw-rw---- 1 root video

# Check all nvidia devices
ls -l /dev/nvidia*
# All primary devices should be root:video 0660
```

## Expected Results

### Before Fix
```
crw-rw-rw- 1 root root  195, 0 /dev/nvidia0
crw-rw-rw- 1 root root  195, 1 /dev/nvidia1
```

### After Fix
```
crw-rw---- 1 root video 195, 0 /dev/nvidia0
crw-rw---- 1 root video 195, 1 /dev/nvidia1
```

## Cleanup (Optional)

The following components are now unnecessary and can be removed:

1. **ub-device-create wrapper** - No longer needed since kernel module creates correct permissions
   ```bash
   sudo rm /usr/sbin/ub-device-create
   sudo mv /usr/sbin/ub-device-create.original /usr/sbin/ub-device-create
   ```

2. **99-ds01-nvidia.rules** - No longer needed
   ```bash
   sudo rm /etc/udev/rules.d/99-ds01-nvidia.rules
   sudo udevadm control --reload-rules
   ```

3. **Permission fix loop in deploy.sh** - Can be removed from script

However, keeping these as redundancy is harmless and may provide defense in depth.

## Rollback

If issues occur:
```bash
# Remove config
sudo rm /etc/modprobe.d/nvidia-permissions.conf

# Reboot or reload nvidia module
sudo reboot
```

## Files Changed
- `config/deploy/modprobe.d/nvidia-permissions.conf` (new)
- `scripts/system/deploy.sh` (modified - added modprobe.d deployment)
