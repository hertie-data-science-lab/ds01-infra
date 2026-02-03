---
phase: 03
plan: 01
subsystem: access-control
tags: [security, gpu-access, linux-video-group, nvidia-wrapper, admin-cli]
requires: [02-awareness-layer]
provides: [bare-metal-restriction, nvidia-command-interception, temporary-grants]
affects: [03-02-container-isolation]
tech-stack:
  added: []
  patterns: [linux-video-group-enforcement, rate-limited-logging, at-command-scheduling]
key-files:
  created:
    - scripts/admin/nvidia-wrapper.sh
    - scripts/admin/bare-metal-access
  modified:
    - config/resource-limits.yaml
    - scripts/lib/error-messages.sh
decisions:
  - Use Linux video group as enforcement mechanism for bare metal GPU access
  - Rate-limit denial logs to 10/hour per user to prevent log flooding
  - Temporary grants via at command with auto-revocation
  - SSH session re-login requirement for group membership changes
  - Echo piped to wall for heredoc simplicity in at command scripts
metrics:
  duration: 7m 0s
  completed: 2026-01-31
---

# Phase 03 Plan 01: Bare Metal GPU Access Restriction Summary

**One-liner:** Linux video group enforcement with nvidia-* command wrappers, admin CLI for temporary/permanent grants via at command scheduling

## Performance

- Duration: 7 minutes
- Tasks: 2/2 complete
- Commits: 2 atomic commits
- No deviations from plan

## Accomplishments

Implemented bare metal GPU access restriction to close major bypass path where users could run CUDA programs directly on host outside DS01 awareness.

**Key deliverables:**
1. nvidia-wrapper.sh - Universal wrapper for all nvidia-* commands with video group enforcement
2. bare-metal-access - Admin CLI for grant/revoke/status with at command scheduling
3. Configuration sections in resource-limits.yaml for exempt users and access control
4. Error message function for denial feedback

**Core functionality:**
- Non-exempt users blocked from nvidia-smi, nvidia-settings, and all nvidia-* commands
- Contextual error directs users to `container deploy`
- Admins (root, ds01-admin group) bypass restrictions automatically
- Rate-limited denial logging (10/hour per user) prevents log flooding
- Temporary grants with auto-revocation and 1h warning before expiry
- Permanent grants for designated users (datasciencelab, h.baker@hertie-school.lan)
- SSH session re-login required for group membership changes to take effect

## Task Commits

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Create nvidia-* wrapper and bare-metal-access CLI | fd7b87f | scripts/admin/nvidia-wrapper.sh, scripts/admin/bare-metal-access |
| 2 | Add bare_metal_access and access_control config | cd92bcc | config/resource-limits.yaml, scripts/lib/error-messages.sh |

## Files Created

- **scripts/admin/nvidia-wrapper.sh** (126 lines)
  - Template deployed to /usr/local/bin for each nvidia-* command
  - Video group check with admin bypass (root, ds01-admin)
  - Rate-limited denial logging (10/hour per user)
  - Contextual error message with container deploy guidance
  - Integrates with DS01 event logging and syslog

- **scripts/admin/bare-metal-access** (659 lines)
  - Subcommands: grant, revoke, status, list
  - Temporary grants via at command with auto-revocation
  - Warning notification 1h before expiry
  - Permanent grants recorded in state files
  - Duration parsing: Xm (minutes), Xh (hours), Xd (days), permanent
  - Status shows access type, expiry time, time remaining
  - Integrates with resource-limits.yaml for exempt users

## Files Modified

- **config/resource-limits.yaml**
  - Added `bare_metal_access` section with exempt_users, admin_group, default_grant_duration, state_dir
  - Added `access_control` section with admin_users, admin_group, wrapper enforcement mode config
  - Exempt users: datasciencelab, h.baker@hertie-school.lan

- **scripts/lib/error-messages.sh**
  - Added `show_bare_metal_restricted()` function
  - Exported function for use by nvidia-wrapper and other scripts

## Decisions Made

1. **Linux video group as enforcement mechanism** - Standard Linux convention for /dev/nvidia* device access, simple and robust
2. **Rate-limited denial logging** - Max 10 denials per user per hour prevents log flooding from repeated command attempts
3. **at command for scheduling** - Purpose-built for one-time scheduled tasks, simpler than systemd timers
4. **Echo piped to wall** - Avoids nested heredoc complexity in at command scripts
5. **SSH session re-login requirement** - Group membership changes require new session to take effect (Linux limitation, documented in messages)
6. **Permanent vs temporary grants** - Temporary uses at command, permanent recorded in state files and config
7. **Admin bypass** - Root and ds01-admin group automatically bypass restrictions (needed for system administration)

## Deviations from Plan

None - plan executed exactly as written.

## Issues & Blockers

None encountered.

## Next Phase Readiness

**Phase 03-02 (Container Isolation) dependencies:**
- ✅ bare_metal_access config section exists for admin model reference
- ✅ access_control config section with enforcement_mode toggle
- ✅ Event logging integration for denial tracking

**Ready to proceed:** Yes

**Notes:**
- Wrappers need deployment via deploy.sh (copies to /usr/local/bin)
- State directory /var/lib/ds01/bare-metal-grants needs creation on deploy
- Exempt users need manual addition to video group on first deployment
- bare-metal-access requires `at` command and `atd` service (runtime check included)

## Architecture Notes

**Enforcement model:**
```
nvidia-smi (user runs)
    ↓
/usr/local/bin/nvidia-smi (wrapper, higher precedence)
    ↓
Check: user in video group? admin? → YES → exec /usr/bin/nvidia-smi
                                   → NO  → show error + log + exit 1
```

**Grant lifecycle:**
```
bare-metal-access grant <user> 24h
    ↓
usermod -aG video <user>
    ↓
Schedule via at: gpasswd -d <user> video (24h later)
    ↓
Schedule via at: wall notification (23h later)
    ↓
User SSH re-login required for video group to take effect
```

**Rate limiting:**
- State files: /var/lib/ds01/rate-limits/nvidia-denials-<user>.state
- Prunes old entries on each check
- First denial in window always logged (warning level to syslog)

**Integration points:**
- DS01 event logging via ds01_events.sh (best-effort, never blocks)
- Syslog via logger command (auth.warning level)
- resource-limits.yaml for exempt user list
- Video group for enforcement (standard Linux device access control)
