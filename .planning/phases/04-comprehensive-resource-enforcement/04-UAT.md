---
status: complete
phase: 04-comprehensive-resource-enforcement
source: 04-01-SUMMARY.md, 04-02-SUMMARY.md, 04-03-SUMMARY.md, 04-04-SUMMARY.md, 04-05-SUMMARY.md
started: 2026-02-06T15:30:00Z
updated: 2026-02-06T16:00:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Aggregate config queryable per user
expected: `python3 scripts/docker/get_resource_limits.py <username> --aggregate` returns JSON with cpu_quota, memory_max, memory_high, tasks_max, gpu_limit. Admin returns null.
result: pass
note: Verified automatically — h.baker returns {"cpu_quota":"24000%","memory_max":"320G","memory_high":"288G","tasks_max":327680,"gpu_limit":6}, datasciencelab returns null

### 2. Generator produces correct systemd drop-ins
expected: `python3 scripts/system/generate-user-slice-limits.py --dry-run --verbose` shows correct CPUQuota/MemoryMax/MemoryHigh/TasksMax per group tier for all users
result: pass
note: Verified automatically — 81 users, students get 9600%/96G/86G/12288, researchers get 24000%/320G/288G/327680, faculty get 32000%/640G/576G/327680, admin skipped

### 3. GPU aggregate limit queryable
expected: `python3 scripts/docker/get_resource_limits.py <username> --aggregate-gpu-limit` returns correct GPU limit (student=3, researcher=6, faculty=8, admin=unlimited)
result: pass
note: Verified automatically — student 188945=3, researcher h.baker=6, admin datasciencelab=unlimited

### 4. Cgroup driver is systemd
expected: Docker daemon uses systemd cgroup driver (required for cgroup v2 enforcement)
result: pass
note: Verified automatically via integration test — Docker uses systemd cgroup driver

### 5. Integration test suite passes (non-root)
expected: Config validation, generator dry-run, and cgroup driver tests pass
result: pass
note: 5/5 non-root tests pass after fixing inverted logic bug and set -e arithmetic issue

### 6. Deploy and verify systemd drop-ins exist on disk
expected: After `sudo deploy`, files exist at `/etc/systemd/system/ds01-*-*.slice.d/10-resource-limits.conf` with correct CPUQuota/Memory/Tasks values
result: pass
note: Verified via sudo cat — student 188945 has CPUQuota=9600%, MemoryMax=96G, MemoryHigh=86G, TasksMax=12288

### 7. Login greeting shows quota at SSH login
expected: SSHing in as a non-admin user shows quota summary (GPUs, Memory, CPUs, Containers) as part of login message
result: pass
note: User confirmed — banner shows welcome, group, and quota line

### 8. check-limits shows aggregate resource usage
expected: Running `check-limits` as a non-admin user shows aggregate resource section with memory/GPU/tasks usage and progress bars
result: issue
reported: "Login greeting shows GPUs 6 but check-limits shows 0/4 GPUs — check-limits caps to physical GPU count, greeting doesn't. Also: MIG vs GPU accounting is a systemic confusion that needs robust resolution."
severity: major

### 9. Docker wrapper blocks container when quota exceeded
expected: Creating a container requesting more memory than the user's aggregate limit shows a clear denial message with current usage, requested amount, and limit
result: issue
reported: "docker run --memory=500g hello-world succeeds with no denial. Root cause: system runs cgroup v1 hybrid (kernel 5.15). Two bugs: (1) wrapper uses /sys/fs/cgroup/ds01.slice/ but memory stats at /sys/fs/cgroup/memory/ds01.slice/ on v1, (2) missing group intermediate slice in path. Both cause fail-open, no enforcement."
severity: blocker

### 10. PSI monitoring cron job deployed and collecting
expected: After deploy, `/etc/cron.d/ds01-resource-monitor` exists, and after ~1 min, entries appear in `/var/log/ds01/resource-stats.log`
result: issue
reported: "Cron job deployed to /etc/cron.d/ correctly, but resource-stats.log is empty. Same root cause as test 9: monitoring script uses /sys/fs/cgroup/ds01.slice which doesn't exist on cgroup v1 hybrid. Finds no slices, writes nothing."
severity: blocker

### 11. Integration test suite passes (with sudo)
expected: `sudo testing/integration/test_resource_enforcement.sh` runs all 11 tests — slice existence, memory enforcement, GPU limits, PSI files, monitoring script, cron deployment
result: skipped
reason: Known cgroup v1/v2 path issue will cause slice/memory/PSI tests to fail. Will re-run after cgroup v2 migration.

## Summary

total: 11
passed: 8
issues: 3
pending: 0
skipped: 1

## Gaps

- truth: "Docker wrapper blocks container creation when aggregate memory quota exceeded"
  status: failed
  reason: "docker run --memory=500g hello-world succeeds. System runs cgroup v1 hybrid (kernel 5.15). Wrapper builds path /sys/fs/cgroup/ds01.slice/ds01-{group}-{user}.slice but actual path is /sys/fs/cgroup/memory/ds01.slice/ds01-{group}.slice/ds01-{group}-{user}.slice. Directory check fails → fail-open → no enforcement."
  severity: blocker
  test: 9
  root_cause: "Two bugs: (1) wrong cgroup base path for v1 hybrid, (2) missing group intermediate slice in path construction. Affects docker-wrapper.sh check_aggregate_quota(), collect-resource-stats.sh, and check-limits cgroup reads."
  artifacts:
    - path: "scripts/docker/docker-wrapper.sh"
      issue: "Line 543: cgroup_path uses /sys/fs/cgroup/ds01.slice/ (wrong on v1 hybrid)"
    - path: "scripts/monitoring/collect-resource-stats.sh"
      issue: "Line 29: CGROUP_ROOT uses /sys/fs/cgroup/ds01.slice (wrong on v1 hybrid)"
  missing:
    - "Migrate to cgroup v2 unified (systemd.unified_cgroup_hierarchy=1 in GRUB)"
    - "Fix cgroup path to include group intermediate slice"
    - "After v2 migration: /sys/fs/cgroup/ds01.slice/ds01-{group}.slice/ds01-{group}-{user}.slice/"

- truth: "PSI monitoring collects resource pressure metrics per user"
  status: failed
  reason: "Cron job deployed but resource-stats.log empty. Same cgroup path bug — monitoring script can't find any user slices."
  severity: blocker
  test: 10
  root_cause: "Same as test 9 — wrong cgroup base path in collect-resource-stats.sh"
  artifacts:
    - path: "scripts/monitoring/collect-resource-stats.sh"
      issue: "Line 29: CGROUP_ROOT=/sys/fs/cgroup/ds01.slice doesn't exist on v1 hybrid"
  missing:
    - "Fix after cgroup v2 migration"

- truth: "Login greeting GPU count matches check-limits GPU count"
  status: failed
  reason: "Login greeting shows GPUs 6 (raw aggregate gpu_limit) but check-limits shows 0/4 (capped to physical GPU count). MIG vs GPU accounting is systemic confusion."
  severity: major
  test: 8
  root_cause: "Login greeting reads --max-gpus (aggregate gpu_limit=6) without capping to system_total. check-limits caps at line 197-198. Also: gpu_limit represents MIG slots not physical GPUs but displayed as 'GPUs'."
  artifacts:
    - path: "config/deploy/profile.d/ds01-quota-greeting.sh"
      issue: "Line 38: reads --max-gpus without capping to physical GPU count"
    - path: "scripts/user/helpers/check-limits"
      issue: "Line 197: correctly caps max_gpus to system_total"
  missing:
    - "Cap GPU count in login greeting to min(gpu_limit, physical_gpus)"
    - "Systemically resolve MIG slot vs physical GPU accounting and display"
