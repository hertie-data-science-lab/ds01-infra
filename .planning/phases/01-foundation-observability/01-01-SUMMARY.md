---
phase: 01-foundation-observability
plan: 01
subsystem: observability
tags: [event-logging, jsonl, logrotate, bash, python, shared-library]

requires:
  - none (foundation plan)

provides:
  - shared-event-logging-library
  - standardised-json-envelope
  - bash-python-event-bridge
  - logrotate-jsonl-config

affects:
  - 01-02 (will use ds01_events for script instrumentation)
  - 01-03 (event-logger.py refactor depends on this)
  - 01-04+ (all future event-emitting scripts)

tech-stack:
  added:
    - ds01_events.py (Python event logging library)
    - ds01_events.sh (Bash wrapper)
  patterns:
    - append-only JSONL logging
    - never-block error handling pattern
    - CLI-as-bridge pattern (Python ↔ Bash)
    - copytruncate for long-running file descriptors

key-files:
  created:
    - scripts/lib/ds01_events.py
    - scripts/lib/ds01_events.sh
  modified:
    - config/deploy/logrotate.d/ds01

key-decisions:
  - event-schema-v1:
      decision: "Standardised JSON envelope with timestamp, event_type, source, schema_version, optional user and details"
      rationale: "Enables schema evolution via schema_version field"
      impact: "All Phase 1 plans must use this format"

  - never-block-pattern:
      decision: "log_event returns False on error, never raises exceptions"
      rationale: "Event logging is diagnostic - must never break production scripts"
      impact: "Calling code can log freely without try/catch"

  - bash-via-cli:
      decision: "Bash wrapper calls Python CLI instead of subprocess with module import"
      rationale: "Simpler than heredoc Python, easier to debug"
      impact: "Small performance overhead (~10ms per event) acceptable for infrequent events"

  - copytruncate-for-jsonl:
      decision: "Use copytruncate instead of create/postrotate for JSONL files"
      rationale: "Keeps file descriptors valid for long-running append processes"
      impact: "Event logging works correctly across logrotate without file handle issues"

duration: 395s
completed: 2026-01-30
---

# Phase 01 Plan 01: Shared Event Logging Library Summary

Standardised event logging infrastructure with Python core and Bash bridge, writing structured JSON events to /var/log/ds01/events.jsonl with proper logrotate configuration.

## Performance

| Metric | Value |
|--------|-------|
| Duration | 6 minutes 35 seconds |
| Start | 2026-01-30T13:11:36Z |
| End | 2026-01-30T13:18:10Z |
| Tasks completed | 3/3 |
| Files created | 2 |
| Files modified | 1 |
| Commits | 3 |

## Accomplishments

### Task 1: Python Event Logging Library

Created `scripts/lib/ds01_events.py` as the core event logging module:

- **log_event()** function with signature: `log_event(event_type, user=None, source=None, **details) -> bool`
- Standardised JSON envelope schema with timestamp (UTC ISO 8601), event_type, source, schema_version
- Never-block guarantee: returns False on error, warns to stderr, never raises
- Atomic writes under PIPE_BUF (4KB) for race-safe append
- CLI interface for Bash: `python3 ds01_events.py log <type> [key=value ...]`
- Comprehensive EVENT_TYPES dict documenting expected fields for all Phase 1 event categories
- NullHandler to avoid "no handlers found" warnings at import time

### Task 2: Bash Event Logging Wrapper

Created `scripts/lib/ds01_events.sh` as sourceable Bash function library:

- **log_event** bash function: `log_event <event_type> [user] [source] [key=value ...]`
- Auto-detects source from calling script basename if not provided
- Calls Python CLI to write events in identical JSON format
- Subshell + `|| true` pattern ensures no script exit on failure (works with `set -e`)
- Under 70 lines - thin wrapper focused on argument transformation

### Task 3: Logrotate Configuration Fix

Updated `config/deploy/logrotate.d/ds01`:

- Added `copytruncate` to both JSONL sections (events.jsonl and gpu-utilization.jsonl)
- Added `maxsize 100M` safety valve for events.jsonl
- Removed `create 0644 root root` (not needed with copytruncate)
- Fixed duplicate log entry error by using specific paths instead of wildcard pattern
- Reordered sections: gpu-utilization.jsonl first (weekly), then events.jsonl (daily)
- Added explanatory comments

## Task Commits

| Task | Commit | Type | Description |
|------|--------|------|-------------|
| 1 | 30ce618 | feat | Create shared Python event logging library |
| 2 | f349799 | feat | Create Bash event logging wrapper |
| 3 | 25173c3 | fix | Add copytruncate to logrotate JSONL config |

## Files Created

### scripts/lib/ds01_events.py (279 lines)
- Python module with log_event() function
- CLI interface for Bash bridge
- EVENT_TYPES documentation dict
- Never-block error handling pattern

### scripts/lib/ds01_events.sh (70 lines)
- Sourceable Bash function library
- log_event wrapper calling Python CLI
- Auto-detection of source script
- Fail-safe execution (never exits on error)

## Files Modified

### config/deploy/logrotate.d/ds01
- Added copytruncate for JSONL files
- Fixed duplicate entry bug
- Added maxsize safety valve

## Decisions Made

### 1. JSON Envelope Schema (v1)

**Context:** Need standardised event format for all DS01 infrastructure scripts.

**Decision:** Use structured envelope with fixed fields (timestamp, event_type, schema_version) and flexible details{} object.

**Alternatives considered:**
- Flat JSON (rejected: no room for evolution)
- Separate schema per event type (rejected: too complex for shared library)

**Impact:** All Phase 1 event logging must use this schema. Future schema changes increment schema_version field.

### 2. Never-Block Error Handling

**Context:** Event logging is diagnostic - production scripts must never crash due to logging failures.

**Decision:** log_event returns bool, warns on stderr, never raises exceptions.

**Alternatives considered:**
- Raise exceptions (rejected: would require try/catch everywhere)
- Silent failures (rejected: hard to debug permission issues)

**Impact:** Calling code can log freely. Permission issues visible but non-fatal.

### 3. Bash-via-CLI Bridge Pattern

**Context:** Need Bash scripts to emit events in same format as Python.

**Decision:** Bash wrapper calls Python CLI (`python3 ds01_events.py log ...`).

**Alternatives considered:**
- Heredoc Python code in Bash (rejected: harder to debug, escaping issues)
- Separate Bash-native implementation (rejected: schema drift risk)
- jq-based JSON construction (rejected: jq not always available)

**Impact:** ~10ms overhead per event (acceptable for infrequent diagnostic events). Single source of truth for schema.

### 4. Copytruncate for JSONL Rotation

**Context:** Append-only JSONL files have long-running file descriptors. Standard logrotate with `create` causes old file descriptor to write to rotated file.

**Decision:** Use `copytruncate` to copy-then-truncate file, keeping descriptors valid.

**Alternatives considered:**
- Standard create with postrotate signal (rejected: requires process management)
- No rotation (rejected: files grow unbounded)

**Impact:** Small window where events during rotation might be lost (acceptable for diagnostic logs). No need for postrotate hooks.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed logrotate duplicate entry error**

- **Found during:** Task 3 logrotate dry-run
- **Issue:** Both `*.jsonl` and `/var/log/ds01/gpu-utilization.jsonl` sections matched the same file, causing "duplicate log entry" error
- **Fix:** Changed wildcard to specific `/var/log/ds01/events.jsonl` path
- **Rationale:** Pre-existing bug in config file. Logrotate complains about duplicates and behavior is undefined.
- **Files modified:** config/deploy/logrotate.d/ds01
- **Commit:** 25173c3 (combined with copytruncate fix)

**2. [Rule 2 - Missing Critical] Added copytruncate to gpu-utilization.jsonl**

- **Found during:** Task 3 review of logrotate config
- **Issue:** gpu-utilization.jsonl section was missing copytruncate, had same file descriptor issue as events.jsonl
- **Fix:** Added copytruncate to gpu-utilization.jsonl section
- **Rationale:** Same append-only pattern, same problem. Consistency with events.jsonl fix.
- **Files modified:** config/deploy/logrotate.d/ds01
- **Commit:** 25173c3 (combined with main fix)

### Design Improvements

None - plan executed as specified.

## Integration Points

### Upstream Dependencies

None - this is a foundation plan with no dependencies.

### Downstream Consumers

This library is required by:

1. **Plan 01-02** (Script instrumentation) - will add log_event() calls to existing scripts
2. **Plan 01-03** (Event logger refactor) - event-logger.py will become a consumer of this library
3. **Plan 01-04+** (All observability plans) - standardised event emission

### External Integration

- **Logrotate:** Runs daily, rotates events.jsonl with copytruncate
- **File permissions:** /var/log/ds01/events.jsonl must be writable by docker group (or world-writable) for non-root logging

## Testing & Validation

### Verification Performed

1. ✓ Python library import and log_event() function work
2. ✓ Bash wrapper calls Python CLI correctly
3. ✓ JSON schema includes all required fields (timestamp, event_type, schema_version)
4. ✓ Logrotate dry-run shows no syntax errors
5. ✓ Never-block pattern works with `set -e` scripts

### Test Coverage

- Unit tests: Python log_event with various argument combinations
- Integration tests: Bash wrapper → Python CLI → JSON output
- Error handling: Permission denied returns False, warns, doesn't crash
- Schema validation: JSON parsing confirms structure

### Known Limitations

1. **File permissions:** /var/log/ds01/events.jsonl currently owned by root:root mode 644 - not writable by regular users. Needs `chmod 666` or group ownership fix in deployment.
2. **Performance:** ~10ms per event due to Python subprocess spawn from Bash. Acceptable for diagnostic events but not suitable for high-frequency logging.
3. **Event size:** Hard limit of 4KB per event (PIPE_BUF). Larger events truncated with warning.
4. **Rotation window:** Small chance of event loss during copytruncate rotation (copy-truncate race condition).

## Next Phase Readiness

### Blockers

**Critical:**
- File permissions on /var/log/ds01/events.jsonl must be fixed before downstream plans can write events
- Suggested fix: `sudo chmod 666 /var/log/ds01/events.jsonl` or add to deployment script

**Monitoring:**
- None

### Concerns

- File permission issue may require sudo access during plan execution, or documented as manual deployment step
- Should validate that 10ms/event overhead is acceptable for planned instrumentation frequency

### Recommendations

1. Add to system deployment script: set events.jsonl permissions to 664 with docker group ownership
2. Consider adding file rotation trigger test (write event before/after rotation to verify copytruncate works)
3. Document permission requirements in README or deployment guide

## Lessons Learned

1. **Deviation tracking works well:** Rule 1/2 auto-fixes for pre-existing bugs caught during task execution
2. **Copytruncate is essential:** Initial plan didn't include gpu-utilization.jsonl fix, but consistency is critical
3. **Testing with temp files:** Overcame permission issues by testing with temporary files, verified behavior before dealing with deployment permissions
4. **CLI-as-bridge pattern:** Clean separation between Python (logic) and Bash (wrapper) via CLI interface
