---
status: complete
phase: 06-lifecycle-enhancements
source: [06-01-SUMMARY.md, 06-02-SUMMARY.md]
started: 2026-02-14T16:00:00Z
updated: 2026-02-14T16:15:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Per-group lifecycle policies in resource-limits.yaml
expected: resource-limits.yaml contains per-group policies subsections with cpu_idle_threshold (students 2%, researcher/faculty 3%), global gpu_idle_threshold, network_idle_threshold, idle_detection_window
result: pass

### 2. Lifecycle exemptions file structure
expected: config/runtime/lifecycle-exemptions.yaml exists with time-bounded exemption entries. At least one entry for Silke Kaiser with expires_on field and exemption_type.
result: pass

### 3. Get lifecycle policies CLI (student user)
expected: Running `python3 scripts/docker/get_resource_limits.py <student_user> --lifecycle-policies` outputs resolved lifecycle policies with cpu_idle_threshold=2 and group-specific thresholds
result: pass

### 4. Get lifecycle policies CLI (researcher user)
expected: Running `python3 scripts/docker/get_resource_limits.py <researcher_user> --lifecycle-policies` outputs resolved lifecycle policies with cpu_idle_threshold=3 (different from student)
result: pass

### 5. Check exemption for exempt user
expected: Running `python3 scripts/docker/get_resource_limits.py 204214@hertie-school.lan --check-exemption idle_timeout` returns exempt status (exit 0 or "exempt" in output)
result: pass

### 6. Check exemption for non-exempt user
expected: Running `python3 scripts/docker/get_resource_limits.py h.baker@hertie-school.lan --check-exemption idle_timeout` returns not-exempt status
result: pass

### 7. Multi-signal AND logic in idle detection
expected: check-idle-containers.sh implements AND logic for idle detection
result: skipped
reason: Code review, not UAT — enforcement logic runs via cron on live containers

### 8. Detection window with IDLE_STREAK tracking
expected: check-idle-containers.sh tracks IDLE_STREAK in state files
result: skipped
reason: Code review, not UAT — requires active containers to observe

### 9. Exempt user handling in idle detection
expected: Exempt users receive FYI-only warnings, not stopped
result: skipped
reason: Code review, not UAT — requires active containers and exempt user workloads

### 10. Variable SIGTERM grace by container type
expected: Container-type-specific SIGTERM grace periods
result: skipped
reason: Code review, not UAT — requires container stop events to observe

### 11. Exemption checking in max runtime enforcement
expected: enforce-max-runtime.sh checks exemption status before enforcement
result: skipped
reason: Code review, not UAT — requires long-running containers hitting runtime limits

## Summary

total: 11
passed: 6
issues: 0
pending: 0
skipped: 5

## Gaps

[none yet]
