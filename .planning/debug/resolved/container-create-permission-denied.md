---
status: resolved
trigger: "container-create permission denied when called from container-deploy during new user project-launch"
created: 2026-02-05T00:00:00Z
updated: 2026-02-05T17:35:00Z
---

## Current Focus

hypothesis: CONFIRMED AND FIXED - 8 scripts had 700 permissions instead of 755
test: chmod 755 applied, verified no 700-permission scripts remain
expecting: users can now run container-create without permission denied
next_action: archive session

## Symptoms

expected: container-create should successfully create and start the Docker container for the user
actual: Permission denied error when container-deploy tries to run container-create
errors: "Permission denied" -- exact location unclear (could be file execute permission or internal command)
reproduction: Run project-launch for a new user -> image builds -> container-deploy is called -> container-create fails
started: First attempt / new user -- never worked before for this user

## Eliminated

- hypothesis: container-create script itself lacks execute permission
  evidence: ls -la shows -rwxr-xr-x (755) on scripts/user/atomic/container-create
  timestamp: 2026-02-05T17:20:00Z

- hypothesis: symlink in /usr/local/bin is broken
  evidence: symlink resolves correctly to scripts/user/atomic/container-create
  timestamp: 2026-02-05T17:20:00Z

## Evidence

- timestamp: 2026-02-05T17:20:00Z
  checked: File permissions on scripts/user/atomic/container-create
  found: -rwxr-xr-x (755) -- correct
  implication: Permission denied is NOT on the container-create script itself

- timestamp: 2026-02-05T17:22:00Z
  checked: Call chain project-launch -> container-deploy -> container-create -> mlc-create-wrapper.sh -> mlc-patched.py
  found: container-create calls bash "$MLC_WRAPPER" (line 1320), wrapper calls python3 "$MLC_PATCHED" (line 676)
  implication: Permission denied could be on mlc-create-wrapper.sh or mlc-patched.py

- timestamp: 2026-02-05T17:25:00Z
  checked: File permissions on scripts/docker/*.py and scripts/docker/*.sh
  found: 4 files have -rwx------ (700) while all others have -rwxr-xr-x (755):
    - mlc-patched.py (700, modified 2026-02-05 17:00)
    - mlc-create-wrapper.sh (700, modified 2026-02-05 17:00)
    - get_resource_limits.py (700, modified 2026-02-05 17:09)
    - gpu_allocator_v2.py (700, modified 2026-02-05 17:00)
  implication: ROOT CAUSE -- non-owner users cannot read/execute these files

- timestamp: 2026-02-05T17:27:00Z
  checked: permissions-manifest.sh line 34
  found: chmod 755 "$INFRA_ROOT"/scripts/docker/*.sh "$INFRA_ROOT"/scripts/docker/*.py
  implication: confirms intended permissions are 755, not 700

- timestamp: 2026-02-05T17:28:00Z
  checked: git diff HEAD on the 4 affected files
  found: no content changes (only permissions differ from expected)
  implication: permissions were changed outside of git, likely by editing with a restrictive umask

- timestamp: 2026-02-05T17:30:00Z
  checked: Broader scan for 700-permission scripts across /opt/ds01-infra/scripts/
  found: 4 additional files also at 700: ds01_events.py, deploy.sh, backup.sh, restore-datasciencelab-sudo.sh
  implication: Same umask issue affected all files edited in this session

- timestamp: 2026-02-05T17:33:00Z
  checked: Full call chain permissions after fix
  found: All 8 files in path from container-create to mlc-patched.py now 755
  implication: Fix verified at permission level

## Resolution

root_cause: Eight files across scripts/docker/, scripts/lib/, scripts/system/, and scripts/backup/ had 700 permissions (owner-only) instead of 755 (world-readable+executable). The four critical files in the container creation path (mlc-create-wrapper.sh, mlc-patched.py, get_resource_limits.py, gpu_allocator_v2.py) caused "Permission denied" when non-owner users hit them during container-create. All affected files were modified today around 17:00-17:09, indicating they were written with a restrictive umask (0077).

fix: chmod 755 on all 8 affected files:
  - scripts/docker/mlc-patched.py
  - scripts/docker/mlc-create-wrapper.sh
  - scripts/docker/get_resource_limits.py
  - scripts/docker/gpu_allocator_v2.py
  - scripts/lib/ds01_events.py
  - scripts/system/deploy.sh
  - scripts/backup/backup.sh
  - scripts/backup/restore-datasciencelab-sudo.sh

verification: All files confirmed at 755. Full call chain (container-create -> init.sh -> mlc-create-wrapper.sh -> get_resource_limits.py -> gpu_allocator_v2.py -> mlc-patched.py) verified readable+executable. No remaining 700-permission .sh/.py files in scripts/.

files_changed: (permissions only, no content changes)
  - scripts/docker/mlc-patched.py
  - scripts/docker/mlc-create-wrapper.sh
  - scripts/docker/get_resource_limits.py
  - scripts/docker/gpu_allocator_v2.py
  - scripts/lib/ds01_events.py
  - scripts/system/deploy.sh
  - scripts/backup/backup.sh
  - scripts/backup/restore-datasciencelab-sudo.sh
