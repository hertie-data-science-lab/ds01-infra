---
status: testing
phase: 05-lifecycle-bug-fixes
source: 05-01-SUMMARY.md, 05-02-SUMMARY.md, 05-03-SUMMARY.md, 05-04-SUMMARY.md
started: 2026-02-11T18:30:00Z
updated: 2026-02-11T18:30:00Z
---

## Current Test

number: 1
name: Phase 5 lifecycle policies in config
expected: |
  resource-limits.yaml contains Phase 5 policies: gpu_idle_threshold (5), grace_period (30m), keepalive_max_duration (24h), sigterm_grace_seconds (60), created_container_timeout (30m). Devcontainer idle_timeout is null.
awaiting: user response

## Tests

### 1. Phase 5 lifecycle policies in config
expected: resource-limits.yaml contains Phase 5 policies: gpu_idle_threshold (5), grace_period (30m), keepalive_max_duration (24h), sigterm_grace_seconds (60), created_container_timeout (30m). Devcontainer idle_timeout is null.
result: [pending]

### 2. GPU-aware idle detection
expected: check-idle-containers.sh queries nvidia-smi for GPU utilization per container UUID. GPU active = NOT idle regardless of CPU. GPU idle + CPU idle = IDLE. Falls back to CPU-only if nvidia-smi fails.
result: [pending]

### 3. 30-minute startup grace period
expected: Containers younger than 30 minutes (from Docker StartedAt) skip idle detection entirely. Grace period read from config policies.grace_period.
result: [pending]

### 4. Dev container exemption from idle timeout
expected: Containers identified as devcontainers (via labels or name patterns) skip idle detection entirely. Only subject to max_runtime (168h), not idle timeout.
result: [pending]

### 5. Wall notifications replace file-based warnings
expected: Idle warnings and max runtime warnings use wall terminal broadcasts. No file creation in user directories (.ds01-idle-warning, .idle-warning.txt, .ds01-runtime-warning removed). Both check-idle-containers.sh and enforce-max-runtime.sh use wall.
result: [pending]

### 6. 60-second SIGTERM grace period
expected: docker stop commands use -t 60 (not -t 10) in both idle detection and max runtime enforcement. Value read from policies.sigterm_grace_seconds with 60s default.
result: [pending]

### 7. Created-state container cleanup
expected: cleanup-stale-containers.sh detects containers in "created" state (never started) via docker ps --filter status=created. Removes them after 30m (from policies.created_container_timeout). Releases GPU allocation before removal. Skips infrastructure containers.
result: [pending]

### 8. Universal container cleanup (no label filter)
expected: cleanup-stale-containers.sh processes ALL stopped containers (docker ps --filter status=exited), not just AIME-labelled ones. Uses ownership fallback chain: ds01.user -> aime.mlc.USER -> devcontainer.local_folder -> name pattern -> unknown.
result: [pending]

### 9. Cron schedule collision fix
expected: ds01-maintenance cron file has lifecycle jobs at distinct times with no collisions. Expected: GPU cleanup :05, idle check :20, runtime enforce :35, container cleanup :50.
result: [pending]

### 10. GPU health verification (SLURM epilog pattern)
expected: cleanup-stale-gpu-allocations.sh has verify_gpu_health() that: queries nvidia-smi --query-compute-apps for orphaned processes, kills them, checks if GPU is shared before reset, never resets shared GPUs (alerts admin instead).
result: [pending]

## Summary

total: 10
passed: 0
issues: 0
pending: 10
skipped: 0

## Gaps

[none yet]
