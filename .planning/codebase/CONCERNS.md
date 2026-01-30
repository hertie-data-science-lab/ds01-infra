# Codebase Concerns

**Analysis Date:** 2026-01-26

## Critical Production Issues

### Host GPU Process Detection (GAP IN TRACKING)

**Issue:** DS01 doesn't capture non-container GPU processes

- **Files:** `monitoring/exporter/ds01_exporter.py`, `scripts/monitoring/detect-bare-metal.py`
- **Problem:** Users with SSH access and docker/video group membership can bypass container system and use GPUs directly. DS01 exporter only queries Docker for `ds01.*` labelled containers, leaving 10-14GB of GPU memory untracked.
- **Audit evidence (2026-01-16):** Found user `248835@hertie-school.lan` running 2 Jupyter kernels directly on host:
  - GPU 0: 4.4GB used (PID 1879486, bloom_test venv)
  - MIG 2.0: 9.8GB used (PID 2502049, bloom_test venv)
  - 0 DS01 containers with GPU assignments but ~14GB in use
- **Impact:** Cannot attribute GPU usage to users, potential fairness violations, hidden resource exhaustion
- **Current mitigation:** DCGM sees GPU activity (shows in Grafana), but no user attribution
- **Fix approach:**
  - Add host GPU process monitor: cross-reference `nvidia-smi --query-compute-apps` PIDs with Docker container cgroups
  - Flag any PID not in a container as "untracked host process"
  - Add `ds01_untracked_gpu_processes` metric to exporter
  - Query PIDs via `/proc/<pid>/loginuid` to map to users
  - Consider enforcement: remove users from `video` group, use udev rules, or systemd device policies
- **Priority:** HIGH - blocks accurate billing/fairness

---

## Security Vulnerabilities

### Debug Output in Production Code (LDAP credentials risk)

**Issue:** DS01 DEBUG output not cleaned up from mlc-patched.py

- **Files:** `scripts/docker/mlc-patched.py` (lines 1496-1532)
- **Problem:** 37 lines of verbose debug output created for LDAP/username sanitization troubleshooting. Debug statements embed usernames, UIDs, GIDs, and group creation attempts in stderr. If stdout/stderr captured in logs, sensitive user provisioning details exposed.
- **Symptoms:** Lines like `echo 'DS01 DEBUG Step 1: Checking for GID 1023 conflicts'` appear in container creation output
- **Current state:** Code checks for `'DS01 DEBUG' in line` and filters in some contexts (`scripts/docker/mlc-patched.py:2269, 2277`) but filtering is inconsistent
- **Risk:** Accidental credential/PII exposure if logs not properly redacted
- **Fix approach:** Remove 37 DEBUG lines entirely (lines 1496-1532), keep only production error messages
- **Priority:** MEDIUM - cleanup needed before wider deployment

---

### shell=True Usage in Subprocess Calls

**Issue:** `shell=True` in subprocess.Popen/run allows shell injection

- **Files:**
  - `scripts/docker/mlc-patched.py` (lines 1025, 2565, 2571)
  - `aime-ml-containers/mlc.py` (lines 896, 2090, 2095)
- **Problem:** When `shell=True` is used with user input (container names, image names), shell metacharacters could be injected
- **Current data flow:** Container/image names come from mlc arguments, but these are typically validated upstream. However, principle suggests avoiding `shell=True`.
- **Risk:** Medium - depends on input validation being thorough
- **Fix approach:** Use `shell=False` with list arguments instead of shell strings. Most mlc.py calls can be refactored.
- **Priority:** MEDIUM - refactor when touching subprocess code

---

## Test Coverage Gaps

### Dev Container Integration Not Fully Tested

**Issue:** Dev container workflow gaps not covered by tests

- **Files:** `testing/` directory, specifically missing `testing/*/test_devcontainer*`
- **What's not tested:**
  - Dev container GPU allocation via docker-wrapper.sh rewriting `--gpus all` to specific device
  - Dev container appears in `container ls` output correctly
  - Cleanup scripts handling dev containers appropriately (do they detect via `devcontainer.*` labels?)
  - Metrics collection for dev containers
  - Multiple dev container opens getting different GPUs based on availability
  - `shutdownAction` properly releasing GPU when VS Code closes
- **Impact:** Undetected regressions when dev container behavior changes
- **Fix approach:**
  - Add integration tests for dev container GPU allocation
  - Test `docker-wrapper.sh` label injection for devcontainers
  - Verify cleanup scripts handle devcontainer.* labels
  - Test metrics collection includes dev containers
- **Priority:** HIGH - dev containers are experimental but user-facing

---

### Bare Metal Container Ownership Detection Not Unit Tested

**Issue:** Container owner detection has multiple fallback strategies but coverage is incomplete

- **Files:** `scripts/docker/container-owner-tracker.py` (lines 108-200+), `scripts/docker/sync-container-owners.py`
- **Strategies (detection priority):**
  1. `ds01.user` label (injected by docker-wrapper.sh)
  2. `aime.mlc.USER` label (from mlc-patched.py)
  3. Container name pattern `name._.uid` (AIME convention)
  4. Bind mount paths `/home/{user}/...`
  5. `devcontainer.local_folder` label
  6. Docker Compose working directory
- **What's not tested:**
  - Fallback order when primary strategies fail
  - Edge case: user has multiple homes, picks wrong one
  - Race condition: container created between label-injection and owner-tracker events
  - Stale ownership data when containers recreated
- **Impact:** Dashboard shows wrong container owner, potential access control bypass
- **Priority:** MEDIUM - core functionality but edge cases untested

---

## Performance & Scalability Issues

### Large File Parsing: mlc-patched.py Complexity

**Issue:** File size and dependencies create coupling complexity

- **Files:** `scripts/docker/mlc-patched.py` (2,845 lines - largest single file)
- **Problem:** 97.8% of file is AIME's mlc.py, 2.2% is DS01 patches. Maintaining fork is high-effort when AIME updates.
- **Current state:** Lives at `/opt/ds01-infra/scripts/docker/`, copies to `/usr/local/bin/mlc`
- **Dependencies:** Imports username sanitization from `scripts/lib/username_utils.py` at runtime with fallback
- **Risk:** Version skew if AIME releases new mlc.py version; synchronization burden
- **Fix approach:**
  - Contribute `--image` flag upstream to AIME (lines 1533-1580 contain complete feature)
  - Once upstream, reduce to thin wrapper or drop patch entirely
  - Short-term: document version (v2.1.2) and update check
- **Priority:** LOW - works as-is, but technical debt for long-term

---

### Exception Handling: Bare `except:` Clauses

**Issue:** Overly broad exception handlers hide bugs and swallow errors

- **Files:**
  - `scripts/monitoring/gpu-status-dashboard.py` (lines 49, 70, 92) - `except:` with silent `return []`
  - `scripts/monitoring/validate-state.py` (lines 47, 92, 141, 225, 250)
  - `scripts/monitoring/mig-utilization-monitor.py` (multiple bare `except:` blocks)
- **Problem:** `except:` catches SystemExit, KeyboardInterrupt, and other non-Exception types. Silent failures return empty lists, causing downstream code to process incomplete data.
- **Example:** `gpu-status-dashboard.py:49-50` catches all exceptions from nvidia-smi and returns `[]`, making failures indistinguishable from "no GPUs"
- **Impact:** Hard to debug, metrics gaps appear as "no data" rather than "error occurred"
- **Fix approach:**
  - Replace `except:` with `except Exception as e:`
  - Add specific exception types where possible (`json.JSONDecodeError`, `subprocess.CalledProcessError`)
  - Log exception details before returning empty/None
  - Return explicit error indicators (e.g., `{"error": "nvidia-smi failed"}`) instead of silent empty
- **Priority:** MEDIUM - affects debugging and observability

---

## Architectural Fragility

### Docker Wrapper Label Injection Order Matters

**Issue:** Docker wrapper `docker-wrapper.sh` injects labels in specific order, fragile to changes

- **Files:** `scripts/docker/docker-wrapper.sh` (lines 90-127, 160-200)
- **Problem:** Wrapper detects ownership via label presence (lines 91-105), then injects labels if missing (lines 160-200). If detection logic and injection get out of sync, containers created without owner labels.
- **Current checks:**
  1. `has_owner_label()` - looks for `--label=ds01.user=*`
  2. `get_devcontainer_owner()` - extracts from `devcontainer.local_folder`
  3. Falls back to `CURRENT_USER`
- **Fragility:** If docker-wrapper.sh changes argument parsing format or label variable names, injection could fail silently
- **Impact:** Containers created without ownership labels, dashboard shows "unknown" owner
- **Fix approach:**
  - Add validation: verify labels were injected post-docker-run
  - Log injected labels for audit
  - Test label injection with various argument formats (quoted, unquoted, concatenated)
  - Consider moving to Docker daemon config (engine labels) instead of per-command injection
- **Priority:** MEDIUM - works in happy path, edge cases fragile

---

### Race Conditions in GPU Allocation

**Issue:** GPU allocator uses file locking but lock timeout is short

- **Files:** `scripts/docker/gpu_allocator_v2.py` (lines 74-80), `scripts/docker/container-owner-tracker.py` (lines 44-68)
- **Problem:** Both use `fcntl.flock()` with 10-second timeout for exclusive lock. If `docker run` is slow (pulling image, creating container), multiple allocation requests could pile up and timeout.
- **Current behavior:** `gpu_allocator_v2.py:_acquire_lock()` locks, allocates, logs, unlocks. If container creation takes >10s and another allocation happens, second process times out.
- **Impact:** Allocation failure, container creation aborts, user sees "Could not acquire lock" error
- **Likelihood:** Increases under high load or slow storage
- **Fix approach:**
  - Increase timeout to 30-60 seconds with exponential backoff
  - Add retry logic with jitter to prevent thundering herd
  - Log lock acquisition time to detect contention
  - Consider moving to Redis/etcd for distributed lock if load increases
- **Priority:** MEDIUM - affects reliability under load

---

## Configuration & Documentation Issues

### TODO-NOT-IMPLEMENTED Fields in resource-limits.yaml

**Issue:** Incomplete feature definitions create user confusion

- **Files:** `config/resource-limits.yaml` (lines 32, 42, 47, 134, 138, 143, 150, 159)
- **Incomplete features:**
  - `gpu_memory` - marked TODO-NOT-IMPLEMENTED (line 32)
  - `io_read_bps`, `io_write_bps` - I/O limits with no enforcement code (lines 42-45)
  - `storage_workspace`, `storage_data`, `storage_tmp` - storage quotas not set up (lines 47-50)
  - Strategy settings - hardcoded to least_allocated/dynamic (line 134)
  - MIG auto-detection - "informational only" comment (line 138)
  - Reservation system - marked TODO-NOT-IMPLEMENTED (line 150)
  - Policy enforcement - marked TODO-NOT-IMPLEMENTED (line 159)
- **Impact:** Users set config values that are silently ignored; admins think features are enabled when they're not
- **Fix approach:**
  - Remove TODO-NOT-IMPLEMENTED fields from YAML
  - Add enforcement code for configured features, or
  - Document which fields are actually active (separate IMPLEMENTED section)
  - Create ticket for each unimplemented feature with estimated effort
- **Priority:** MEDIUM - affects configuration trust

---

## Known Bugs & Workarounds

### Container-Stats Filter Flag Bug

**Issue:** `container-stats --filter` command fails

- **Files:** `scripts/user/atomic/container-stats` (unknown exact line - not located)
- **Problem:** "unknown flag: --filter" error when users run `container-stats --filter <criteria>`
- **Symptoms:** Help text mentions `--filter` but implementation doesn't support it
- **Workaround:** Use `container ls | grep <criteria>` then query stats individually
- **Impact:** MINOR - help is inaccurate, feature works partially
- **Fix approach:** Either implement `--filter` support or remove from help text
- **Priority:** LOW - cosmetic but confusing

---

### Empty Event Log

**Issue:** `/var/log/ds01/events.jsonl` has 0 lines

- **Files:** `scripts/docker/event-logger.py`, container event capture system (unknown)
- **Problem:** Events should be logged but file is empty. Either:
  - Event logging not started (daemon not running)
  - Event logger has permissions issue
  - Events are being dropped
- **Impact:** Cannot audit container creation/deletion, no event history for debugging
- **Diagnosis needed:** Check `systemctl status ds01-event-logger`, check file permissions, check if `event-logger.py` is running
- **Fix approach:** Verify daemon is running, check logs in `/var/log/ds01/event-logger.log` (if exists), restart service
- **Priority:** MEDIUM - affects audit trail

---

## Monitoring & Observability Issues

### Event Log Integration Incomplete

**Issue:** Multiple event logging systems but no central aggregation

- **Files:**
  - `scripts/docker/event-logger.py` - append-only JSON log
  - `scripts/monitoring/ds01-events` - query tool
  - `/var/log/ds01/events.jsonl` - central log file
  - `/var/log/ds01/cron.log` - separate cron logs
  - `/var/log/ds01/gpu-allocations.log` - GPU allocation history
- **Problem:** Events scattered across multiple files. `ds01-events` query tool should unify these, but currently only reads main events.jsonl. GPU allocation and cron events are separate.
- **Impact:** Difficult to correlate events across systems; user changes GPU allocation but no corresponding event entry
- **Fix approach:**
  - Extend `ds01-events` tool to query all log types
  - Add event type filtering (container, gpu, cron, etc.)
  - Implement JSON output for programmatic queries
  - Add event retention policy (rotate at 1GB or 90 days)
- **Priority:** MEDIUM - affects troubleshooting

---

## Documentation & Maintenance Issues

### Stale/Empty Admin Documentation

**Issue:** Several admin docs are empty placeholders

- **Files:**
  - `docs-admin/installation.md` (0 bytes)
  - `docs-admin/maintenance.md` (0 bytes)
  - `docs-admin/setup-checklist.md` (123 bytes - just header)
  - `docs-admin/system-config.md` (123 bytes - just header)
- **Problem:** Admin reading docs expects these files to contain critical information but finds empty templates
- **Impact:** MINOR - information exists elsewhere (README.md, CLAUDE.md) but discoverability poor
- **Fix approach:**
  - Either populate these files with content from README/CLAUDE docs, or
  - Remove empty files and update references
  - Consolidate admin docs into README or create admin-specific handbook
- **Priority:** LOW - documentation quality issue

---

### TODO Comments Scattered Across Codebase

**Issue:** 140+ TODO comments indicate incomplete work

- **Locations:**
  - `TODO.md` - main task list (comprehensive, 204 lines)
  - `scripts/docker/mlc-patched.py` - DEBUG cleanup TODOs
  - `config/resource-limits.yaml` - unimplemented features
  - `scripts/maintenance/setup-scratch-dirs.sh` - TODO on line 5
  - `docs-admin/gpu-allocation-implementation.md` - deleted content TODOs
  - Multiple script comments about incomplete features
- **Problem:** Mix of strategic TODOs (in TODO.md) and tactical TODOs (in code). No prioritization system for code-level TODOs.
- **Impact:** Code review harder when intent unclear; maintenance burden when merging
- **Fix approach:**
  - Keep TODO.md as single source of truth for strategic items
  - Code TODOs should reference TODO.md line numbers (e.g., "See TODO.md:50")
  - Or: remove all code TODOs and rely on TODO.md only
  - Use issue tracker (GitHub Issues) for tracked work instead of comments
- **Priority:** LOW - organizational improvement

---

## Dependency Management

### Submodule Dependency: aime-ml-containers

**Issue:** DS01 depends on external AIME MLC submodule

- **Files:** `aime-ml-containers/` directory (gitmodule)
- **Problem:** DS01 patches mlc.py (copy to `/usr/local/bin/mlc`), but if AIME updates with breaking changes, patches may fail. No version pinning or CI check.
- **Current version:** mlc v2.1.2 (documented in mlc-patched.py header)
- **Risk:** Upstream updates could break container creation
- **Fix approach:**
  - Pin AIME version in `.gitmodules` or document required version
  - Add CI check: validate mlc-patched.py applies cleanly to vendored mlc.py
  - Consider contributing `--image` flag upstream to eliminate patch
- **Priority:** LOW - works as-is, but maintenance burden

---

## Summary of Priorities

| Priority | Count | Key Issues |
|----------|-------|-----------|
| **CRITICAL** | 1 | Host GPU process detection gap - cannot track uncontainerized GPU use |
| **HIGH** | 2 | Dev container test coverage, TODO-NOT-IMPLEMENTED config fields |
| **MEDIUM** | 6 | Debug output cleanup, bare `except:` clauses, race conditions, event log integration, container owner detection, docker-wrapper fragility |
| **LOW** | 4 | Documentation gaps, mlc.py fork complexity, cosmetic bugs, dependency management |

---

*Concerns audit: 2026-01-26*
