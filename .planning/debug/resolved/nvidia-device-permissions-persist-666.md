---
status: fixing
trigger: "nvidia device permissions keep reverting to 0666"
created: 2026-01-31T10:30:00Z
updated: 2026-01-31T10:40:00Z
---

## Current Focus

hypothesis: CONFIRMED - Fix implemented
test: Files created and deployment script updated
expecting: User deployment with sudo deploy, then reboot/module reload to apply
next_action: Verify fix cannot be applied without sudo access - requires user to deploy and reboot

## Symptoms

expected: /dev/nvidia* should be 0660 root:video after deploy
actual: Some devices persist at 0660, others revert to 0666 within minutes

**KEY PATTERN:**
- REVERTS to 666: nvidia0, nvidia1, nvidia2, nvidia3, nvidiactl, nvidia-uvm, nvidia-uvm-tools (PRIMARY GPU devices)
- PERSISTS at 660: nvidia-modeset, nvidia-nvswitchctl, nvidia-caps (AUXILIARY devices)

**Context:**
- Manual `chmod 0660 /dev/nvidia0` works and persists for at least 2 seconds
- deploy.sh sets permissions in explicit loop, but they revert within minutes
- No cron jobs, tmpfiles rules, or udev triggers found resetting them
- nvidia-persistenced.service IS running
- ub-device-create wrapper deployed at /usr/sbin/ub-device-create
- Wrapper has `set -e` which may cause early exit on non-zero return
- DCGM exporter container running with --gpus all
- AppArmor loaded

reproduction: Deploy system, observe /dev/nvidia0 permissions over time
started: Unknown, discovered during deployment validation

## Eliminated

## Evidence

- timestamp: 2026-01-31T10:30:00Z
  checked: Initial context and symptoms
  found: Primary GPU devices revert, auxiliary devices persist
  implication: The mechanism creating/managing primary GPU devices is different from auxiliary ones

- timestamp: 2026-01-31T10:32:00Z
  checked: Current device permissions on system
  found: nvidia0-3, nvidiactl, nvidia-uvm, nvidia-uvm-tools are 0666 root:root | nvidia-modeset, nvidia-nvswitchctl are 0660 root:video
  implication: Confirms symptom pattern - primary GPU devices have wrong permissions RIGHT NOW

- timestamp: 2026-01-31T10:33:00Z
  checked: nvidia-persistenced service status and config
  found: Running as root (UID 2093), started with --verbose flag only, no --user or --group flags
  implication: nvidia-persistenced runs as root and creates/manages device files with default root:root ownership

- timestamp: 2026-01-31T10:34:00Z
  checked: ub-device-create wrapper implementation
  found: Wrapper has `set -e` on line 9, calls original binary, then fixes permissions with find loop
  implication: If original binary returns non-zero, script exits before permission fix. BUT this doesn't explain ongoing reverts

- timestamp: 2026-01-31T10:35:00Z
  checked: nvidia-persistenced --help output
  found: Has --user=USERNAME and --group=GROUPNAME options to run with specific user/group permissions
  implication: Potential fix approach, but not the root cause

- timestamp: 2026-01-31T10:36:00Z
  checked: /proc/driver/nvidia/params kernel module parameters
  found: ModifyDeviceFiles=1, DeviceFileUID=0, DeviceFileGID=0, DeviceFileMode=438 (0o666)
  implication: ROOT CAUSE CONFIRMED - NVIDIA kernel module is hardcoded to create device files with GID=0 (root) and mode 0666

- timestamp: 2026-01-31T10:37:00Z
  checked: video group GID
  found: GID=44
  implication: Need to set NVreg_DeviceFileGID=44 and NVreg_DeviceFileMode=0660 (432 decimal) in kernel module parameters

- timestamp: 2026-01-31T10:40:00Z
  checked: Fix implementation
  found: Created nvidia-permissions.conf modprobe config, updated deploy.sh to install it
  implication: Fix ready for deployment - requires sudo access and reboot to apply
## Resolution

root_cause: NVIDIA kernel module hardcoded parameters DeviceFileGID=0 and DeviceFileMode=438 (0666) cause all /dev/nvidia* device files to be created with root:root 0666 permissions, overriding any udev rules or wrapper scripts. The kernel module's ModifyDeviceFiles=1 setting means it actively manages device file permissions.

fix: Created /etc/modprobe.d/nvidia-permissions.conf to set NVreg_DeviceFileGID=44 (video group) and NVreg_DeviceFileMode=432 (0660 decimal). Updated deploy.sh to copy this file. Requires nvidia module reload or system reboot to take effect.

verification: Cannot verify without sudo access. User must: 1) Run `sudo deploy`, 2) Reboot or reload nvidia module, 3) Verify with `cat /proc/driver/nvidia/params | grep DeviceFile` and `ls -l /dev/nvidia0`

files_changed:
  - config/deploy/modprobe.d/nvidia-permissions.conf (new)
  - scripts/system/deploy.sh (modified - added modprobe.d deployment section)
  - .planning/debug/nvidia-permissions-fix-deployment.md (deployment instructions)
