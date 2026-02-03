---
status: complete
phase: cross-phase-audit (phases 1, 2, 2.1, 3)
source: 01-VERIFICATION.md, 02-VERIFICATION.md, 02.1-VERIFICATION.md, 03-01-SUMMARY.md, 03-02-SUMMARY.md, system-state-audit
started: 2026-02-01T14:00:00Z
updated: 2026-02-01T14:30:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Event logging library functional (Phase 1)
expected: Python event logging library importable, log_event() writes structured JSON to events.jsonl
result: issue
reported: "log_event returns False for h.baker — permission denied on /var/log/ds01/events.jsonl (644 root:root)"
severity: major

### 2. Event query tool works (Phase 1)
expected: ds01-events command deployed and returns structured event data from log
result: issue
reported: "bash: /usr/local/bin/ds01-events: Permission denied — script is 700 (owner-only)"
severity: major

### 3. DCGM exporter running (Phase 1)
expected: ds01-dcgm-exporter.service is active and serving GPU metrics
result: issue
reported: "Service failed since Jan 31 20:54:20 CET — GPU metrics export is down"
severity: major

### 4. Workload detector running (Phase 2)
expected: ds01-workload-detector.timer active, workload-inventory.json updating every 30s
result: pass

### 5. ds01-workloads command works (Phase 2)
expected: ds01-workloads shows container inventory with type classification and user attribution
result: pass
note: Verified as admin (datasciencelab). Likely 700 permissions for non-admin — needs separate verification.

### 6. Host GPU process detection (Phase 2)
expected: A host GPU process appears in workload inventory
result: skipped
reason: No host GPU process running at time of test; detector timer is functional so detection likely works

### 7. CUDA_VISIBLE_DEVICES set for regular users (Phase 2.1/3)
expected: Non-exempt user's shell has CUDA_VISIBLE_DEVICES="" after login
result: issue
reported: "CUDA_VISIBLE_DEVICES is set correctly, but BOTH exemption paths are broken by permissions: grant dir is 700 root:root (users can't check grant files), resource-limits.yaml is 600 (users can't read exempt list). So ALL users are blocked regardless of exemption status."
severity: blocker

### 8. Exempt user bypasses GPU block (Phase 2.1/3)
expected: Exempt user (e.g., h.baker with grant or in exempt_users) has CUDA_VISIBLE_DEVICES unset
result: issue
reported: "h.baker has bare-metal-access GRANTED but still gets CUDA_VISIBLE_DEVICES='' because grant dir /var/lib/ds01/bare-metal-grants/ is 700 root:root and config is 600. Both exemption checks fail silently."
severity: blocker

### 9. Container isolation - user sees own containers only (Phase 3)
expected: Regular user running docker ps only sees their own containers (filtered by ds01.user label)
result: skipped
reason: Not tested as non-admin user; admin bypass confirmed working (datasciencelab sees all containers)

### 10. Container isolation - cross-user operations blocked (Phase 3)
expected: User cannot exec/stop/rm another user's container; gets permission denied
result: skipped
reason: Not tested; requires two users with running containers

### 11. bare-metal-access admin CLI works (Phase 3)
expected: sudo bare-metal-access status shows current access grants; grant/revoke functional
result: pass
note: Shows h.baker as GRANTED (Unknown type — no metadata). Command functional for admin.

### 12. GPU allocation pipeline works end-to-end (Foundation)
expected: container deploy <name> allocates a GPU and creates container for regular user
result: issue
reported: "Known bugs: gpu-availability-checker only queries MIG (reports 0 GPUs when MIG disabled on 4x A100), gpu_allocator_v2 doesn't load .members files (all users fall to student defaults). Code changes identified but not yet applied."
severity: blocker

### 13. deploy.sh runs cleanly (Foundation)
expected: sudo deploy completes without errors, deploys all commands and config
result: issue
reported: "mlc-create was deployed as regular file copy (not symlink), causing SCRIPT_DIR to resolve to /usr/local/bin/ instead of source dir. Python dependencies (gpu_allocator_v2.py, etc.) not found. Fix identified in deploy.sh but needs sudo deploy to apply."
severity: major

### 14. File permissions allow non-root operation (Foundation)
expected: Non-admin user can run ds01 commands, read config, write state files as needed
result: issue
reported: "Systemic failure: scripts are 700 (owner-only), config is 600, state dirs are 700 root:root, .so library is 700. Non-admin users cannot use ds01-events, read resource-limits.yaml, check grant files, or load LD_PRELOAD notice. This is the root cause of most other failures."
severity: blocker

## Summary

total: 14
passed: 3
issues: 8
pending: 0
skipped: 3

## Gaps

- truth: "Non-root users can log events via ds01_events.py"
  status: failed
  reason: "User reported: log_event returns False — permission denied on /var/log/ds01/events.jsonl (644 root:root)"
  severity: major
  test: 1
  root_cause: "events.jsonl owned by root:root with 644 — needs group-writable (664 root:docker or root:ds-admin)"
  artifacts:
    - path: "/var/log/ds01/events.jsonl"
      issue: "644 root:root — not writable by non-root users"
  missing:
    - "Set events.jsonl to 664 root:docker (or root:ds-admin) in deploy.sh"

- truth: "ds01-events command executable by all users"
  status: failed
  reason: "User reported: Permission denied — script is 700"
  severity: major
  test: 2
  root_cause: "scripts/monitoring/ds01-events has 700 permissions (owner-only execute)"
  artifacts:
    - path: "scripts/monitoring/ds01-events"
      issue: "700 permissions, should be 755"
  missing:
    - "chmod 755 all scripts in scripts/*/ as part of deploy.sh"

- truth: "DCGM exporter runs reliably"
  status: failed
  reason: "Service failed since Jan 31 20:54:20 CET"
  severity: major
  test: 3
  root_cause: "Service crashed and failed to auto-recover — needs investigation of exit code and logs"
  artifacts:
    - path: "config/deploy/systemd/ds01-dcgm-exporter.service"
      issue: "Service failed and not recovering"
  missing:
    - "Diagnose DCGM failure, restart service, verify stability"

- truth: "Exempt users bypass CUDA_VISIBLE_DEVICES block via grant files or config"
  status: failed
  reason: "Both exemption paths broken by file permissions: grant dir 700 root:root, config 600 owner-only"
  severity: blocker
  test: 7, 8
  root_cause: "/var/lib/ds01/bare-metal-grants/ is 700 root:root (users can't stat files inside), resource-limits.yaml is 600 (users can't read exempt list)"
  artifacts:
    - path: "/var/lib/ds01/bare-metal-grants/"
      issue: "700 root:root — needs 755 or 711 so users can check own grant file"
    - path: "config/resource-limits.yaml"
      issue: "600 owner-only — needs 644 so profile.d script can grep exempt_users"
  missing:
    - "chmod 711 /var/lib/ds01/bare-metal-grants/ (traverse without listing)"
    - "chmod 644 config/resource-limits.yaml"
    - "Add both to deploy.sh permissions manifest"

- truth: "GPU allocation pipeline allocates GPUs for regular users"
  status: failed
  reason: "gpu-availability-checker only queries MIG, gpu_allocator_v2 doesn't load .members files"
  severity: blocker
  test: 12
  root_cause: "get_available_gpus() only calls MIG query — _get_full_gpus_available() exists but not called in default path. _load_config() doesn't merge .members files like get_resource_limits.py does."
  artifacts:
    - path: "scripts/docker/gpu-availability-checker.py"
      issue: "get_available_gpus() skips full GPU detection"
    - path: "scripts/docker/gpu_allocator_v2.py"
      issue: "_load_config() doesn't load groups/*.members"
  missing:
    - "Include full GPUs in available pool when MIG disabled"
    - "Port .members file loading from get_resource_limits.py"

- truth: "deploy.sh deploys all commands correctly"
  status: failed
  reason: "mlc-create deployed as file copy (not symlink), Python dependencies not deployed alongside"
  severity: major
  test: 13
  root_cause: "deploy.sh copies mlc-create-wrapper.sh but doesn't deploy gpu_allocator_v2.py etc. to /usr/local/bin/ — SCRIPT_DIR resolves wrong"
  artifacts:
    - path: "scripts/system/deploy.sh"
      issue: "Missing deploy_cmd calls for Python dependencies"
  missing:
    - "Add symlink deployment for gpu_allocator_v2.py, get_resource_limits.py, gpu-state-reader.py, mlc-patched.py"

- truth: "File permissions allow non-root operation of ds01 tools"
  status: failed
  reason: "Systemic: scripts 700, config 600, state dirs 700, lib 700 — non-admin users locked out"
  severity: blocker
  test: 14
  root_cause: "No permissions enforcement in deploy pipeline. Files inherit restrictive umask from datasciencelab user."
  artifacts:
    - path: "scripts/system/deploy.sh"
      issue: "No chmod step for scripts, config, state dirs"
  missing:
    - "Add comprehensive permissions pass to deploy.sh (scripts 755, config 644, state dirs per-dir, lib 755)"
