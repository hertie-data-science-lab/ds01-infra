---
created: 2026-02-01T00:05
title: Design group management & file permissions system
area: tooling
files:
  - scripts/system/deploy.sh:275-342
  - scripts/system/add-user-to-docker.sh
  - config/deploy/profile.d/ds01-gpu-awareness.sh
  - scripts/admin/bare-metal-access
---

## Problem

DS01 file permissions and group management are currently ad-hoc, causing repeated
production failures. Issues encountered during GPU allocation debugging (2026-01-31):

1. **Group assignment inconsistent** — docker users need video group for nvidia-smi,
   but deploy.sh was actively removing non-exempt users from video on every deploy.
   Bare-metal-access grant/revoke was adding/removing from video. Now decoupled but
   the overall group management story is fragile.

2. **File/directory permissions drift** — scripts at 700 instead of 755, config
   directories with inconsistent other-execute bits (drwx---r-x), __pycache__
   directories created by root with 700 preventing non-root users from importing
   Python modules.

3. **State directory permissions** — /var/lib/ds01/ and /var/log/ds01/ owned by
   datasciencelab:datasciencelab with 755, meaning non-root users can't create lock
   files or write logs. Lock files need 666 pre-creation or writable directories.

4. **__pycache__ ownership** — Python bytecode cache created by whichever user runs
   the script first (often root via deploy/cron). Subsequent non-root users get
   PermissionError on import.

5. **No single enforcement point** — permissions are fixed manually after each failure
   rather than enforced deterministically on deploy.

## Solution

Add a permissions enforcement pass to deploy.sh that runs on every `sudo deploy`:

1. **Group sync**: All docker group members → also in video group (done, needs hardening)
2. **File permissions**: `find /opt/ds01-infra/scripts -type f -name '*.sh' -o -name '*.py' | xargs chmod 755`
3. **Directory permissions**: `find /opt/ds01-infra -type d | xargs chmod 755`
4. **Config permissions**: `find /opt/ds01-infra/config -type f | xargs chmod 644`
5. **__pycache__ cleanup**: `find /opt/ds01-infra/scripts -type d -name __pycache__ -exec rm -rf {} +` (already added)
6. **State directories**: Ensure /var/lib/ds01/ and /var/log/ds01/ are group-writable by docker group
7. **Lock files**: Pre-create with 666 permissions

Should be a single function in deploy.sh (~20 lines), idempotent, runs every deploy.
