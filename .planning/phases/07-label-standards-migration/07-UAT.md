---
status: complete
phase: 07-label-standards-migration
source: 07-01-SUMMARY.md, 07-02-SUMMARY.md, 07-03-SUMMARY.md
started: 2026-02-16T16:10:00Z
updated: 2026-02-16T17:22:00Z
---

## Tests

### 1. New Container Gets ds01.* Labels
expected: Create a container via DS01 workflow. `docker inspect` shows ds01.user, ds01.managed=true, ds01.image etc. No aime.mlc.DS01_* labels present.
result: pass
reported: "Initially hung — two bugs found and fixed. (1) Backward-compat label check missing: old images have aime.mlc.DS01_HAS_USER_SETUP but code checked ds01.has_user_setup, causing unnecessary docker run user-setup. (2) That setup container had no ds01.managed label, triggering docker-wrapper GPU allocation loop. Both fixed. Container creates in ~6s with correct ds01.* labels."

### 2. Legacy Container Still Detected
expected: Legacy containers with aime.mlc.* labels appear in dashboard/container-list with correct ownership.
result: skipped
reported: "No legacy containers exist on system — all recently created."

### 3. Container Listing Shows Both Label Schemes
expected: Run container-list. Containers appear with correct ownership from ds01.user labels.
result: pass

### 4. Admin Dashboard Enumerates DS01 Containers
expected: Run ds01-dashboard. Containers filtered by ds01.managed=true, counts and GPU usage correct.
result: pass

### 5. User Enumeration Works
expected: Run ds01-users. All users with active containers listed correctly.
result: pass

### 6. Idle Detection Picks Up New Containers
expected: Run check-idle-containers.sh. New ds01.* containers detected and evaluated.
result: pass
reported: "Container test._.1722830498 (h.baker) correctly detected and within 30m grace period. Todo captured: show owner name in idle check output."

### 7. Label Schema Accessible to Developers
expected: config/label-schema.yaml shows complete namespace document with all ds01.* labels and migration mapping.
result: pass

## Summary

total: 7
passed: 6
issues: 0
pending: 0
skipped: 1

## Gaps

- truth: "Container creation via mlc-patched.py completes successfully"
  status: fixed
  root_cause: "Two issues: (1) Label check for skip_user_setup only looked at ds01.has_user_setup, not legacy aime.mlc.DS01_HAS_USER_SETUP — old images always ran user setup. (2) Internal docker run setup container had no ds01.managed label, docker-wrapper classified as 'docker' type, entered 3-min GPU allocation retry loop."
  fix: "(1) Backward-compat label check reads both ds01.* and aime.mlc.* labels. (2) DS01_WRAPPER_BYPASS=1 env for setup subprocess."
  artifacts: ["scripts/docker/mlc-patched.py"]
