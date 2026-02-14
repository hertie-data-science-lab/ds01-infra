---
status: fixing
trigger: "cgroup-v2-path-fixes"
created: 2026-02-06T00:00:00Z
updated: 2026-02-06T00:00:00Z
---

## Current Focus

hypothesis: Root causes already identified from UAT
test: Applying fixes to cgroup paths and GPU count capping
expecting: Docker wrapper enforcement, PSI monitoring, and login greeting all functional
next_action: Fix Bug 1-4 using check-limits pattern as reference

## Symptoms

expected: Docker wrapper blocks container creation when aggregate memory quota exceeded. PSI monitoring collects resource pressure metrics. Login greeting GPU count matches physical hardware.
actual: docker run --memory=500g hello-world succeeds (no denial). resource-stats.log is empty. Login greeting shows "GPUs 6" but check-limits shows "0/4 GPUs".
errors: No errors — all code paths fail-open. The cgroup directory checks return false (path doesn't exist), so enforcement is silently skipped.
reproduction: (1) `docker run --memory=500g hello-world` as non-admin user — succeeds instead of being blocked. (2) Check /var/log/ds01/resource-stats.log — empty. (3) SSH login shows wrong GPU count.
started: Since Phase 4 was implemented. The code was written assuming pure cgroup v2 but system runs v1 hybrid.

## Eliminated

(None yet - root causes pre-identified from UAT)

## Evidence

- timestamp: 2026-02-06 (from UAT)
  checked: cgroup filesystem structure
  found: Nested slices ds01.slice/ds01-{group}.slice/ds01-{group}-{user}.slice
  implication: Missing group intermediate slice in docker-wrapper.sh line 543

- timestamp: 2026-02-06 (from UAT)
  checked: PSI monitoring output
  found: /var/log/ds01/resource-stats.log is empty
  implication: Wrong cgroup paths in collect-resource-stats.sh + wrong iteration pattern

- timestamp: 2026-02-06 (from UAT)
  checked: Login greeting vs check-limits GPU count
  found: Greeting shows 6, check-limits shows 0/4
  implication: GPU count not capped to physical hardware in greeting

- timestamp: 2026-02-06 (from UAT)
  checked: check-limits cgroup detection
  found: Lines 139-151 have correct multi-path detection pattern
  implication: Use this as reference for other fixes

## Resolution

root_cause: Four cgroup path bugs - (1) missing group slice in docker-wrapper, (2) wrong base path + iteration in collect-resource-stats, (3) uncapped GPU count in greeting, (4) check-limits already correct
fix: Apply fixes to 3 files using check-limits pattern as reference
verification: Test docker wrapper enforcement, PSI collection, and login greeting
files_changed: []
