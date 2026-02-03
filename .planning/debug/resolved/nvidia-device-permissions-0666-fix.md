---
status: investigating
trigger: "nvidia-device-permissions-0666-fix"
created: 2026-02-01T00:00:00Z
updated: 2026-02-01T00:00:00Z
---

## Current Focus

hypothesis: The current 0660 approach (modprobe.d config) is WRONG for DS01's architecture. Research shows 0666 is standard for container/HPC. Need to change to 0666.
test: Research multi-user HPC and container environments, compare with Phase 2.1 findings
expecting: Confirmation that 0666 is correct approach, then fix modprobe.d + udev rules
next_action: Update modprobe.d config to set 0666, align udev rules, update deploy.sh

## Symptoms

expected: Non-video-group users should be able to allocate GPUs via `container deploy`. The GPU availability checker calls `/usr/bin/nvidia-smi -L` to enumerate GPUs.
actual: `sudo -u 'h.baker@hertie-school.lan' /usr/bin/nvidia-smi -L` returns "Failed to initialize NVML: Insufficient Permissions". Device files are 0660 root:video. GPU allocation reports "No GPUs Currently Available".
errors: "Failed to initialize NVML: Insufficient Permissions" from nvidia-smi, "No GPUs Currently Available" from container deploy
reproduction: Run `/usr/bin/nvidia-smi -L` as any user NOT in the video group. Fails every time.
started: This has been the driver default all along. Was masked when users were in the video group. Became visible when Phase 3.1 restricted video group to exempt users only.

## Eliminated

## Evidence

- timestamp: 2026-02-01T00:00:00Z
  checked: Prior debug files
  found: nvidia-device-permissions-persist-666.md shows modprobe.d config was created to set 0660 root:video (GID 44, mode 432). This is DEPLOYED and ACTIVE. /proc/driver/nvidia/params confirms DeviceFileGID=44, DeviceFileMode=432. Devices are correctly 0660 root:video.
  implication: The "fix" from yesterday WORKED but set the WRONG permissions (0660 instead of 0666). This is the OPPOSITE of what's needed.

- timestamp: 2026-02-01T00:05:00Z
  checked: Phase 2.1 research (prior_context)
  found: "SLURM and Kubernetes both use 0666 device permissions", "Device-level restriction is an anti-pattern (breaks nvidia-smi, monitoring tools)", "Three-layer architecture designed: Layer 1 (CUDA_VISIBLE_DEVICES), Layer 2 (Docker device mapping), Layer 3 (video group for bare-metal opt-in)"
  implication: DS01 was DESIGNED to use 0666 permissions. The current 0660 setup contradicts the architecture.

- timestamp: 2026-02-01T00:10:00Z
  checked: Web research - NVIDIA Container Toolkit documentation
  found: Multiple GitHub issues (nvidia-docker #1523, #1547, #284) confirm "Insufficient Permissions" error occurs with 0660 permissions in multi-user container environments. Solutions consistently involve either adding users to video group OR setting 0666 permissions.
  implication: Industry standard for container environments is 0666 permissions, not group-based restrictions.

- timestamp: 2026-02-01T00:15:00Z
  checked: Web research - NVIDIA kernel module parameters
  found: Gentoo wiki shows standard config: "options nvidia NVreg_DeviceFileMode=0660 NVreg_DeviceFileUID=0 NVreg_DeviceFileGID=27" with WARNING: "ONLY ADD TRUSTED USERS TO THE VIDEO GROUP, THESE USERS MAY BE ABLE TO CRASH, COMPROMISE, OR IRREPARABLY DAMAGE THE MACHINE"
  implication: 0660 + video group is the traditional approach BUT comes with severe security warnings. This is why DS01 uses container-based access control instead.

- timestamp: 2026-02-01T00:20:00Z
  checked: Current file state
  found: config/deploy/udev/99-ds01-nvidia.rules sets MODE="0666" with clear comment explaining the design. config/deploy/modprobe.d/nvidia-permissions.conf sets mode 432 (0660). CONFLICT: udev says 0666, modprobe.d says 0660.
  implication: The modprobe.d config OVERRIDES the udev rules (kernel module creates files before udev runs). Current state is 0660 because modprobe.d wins.

- timestamp: 2026-02-01T00:25:00Z
  checked: 99-ds01-nvidia.rules comments
  found: "GPU access control is enforced at Layer 1 (CUDA_VISIBLE_DEVICES) and Layer 2 (Docker --gpus device mapping), NOT at device permission level. See: .planning/phases/02.1-gpu-access-control-research/"
  implication: The udev rules file has CORRECT architectural understanding documented. The modprobe.d config contradicts this.

## Resolution

root_cause:

fix:

verification:

files_changed: []
