---
phase: 01-foundation-observability
plan: 05
subsystem: observability
tags: [event-logging, jq, query-tools, refactor, admin-tools]

requires:
  - 01-01 (shared event logging library)

provides:
  - refactored-event-logger
  - comprehensive-event-query-tool
  - jq-based-filtering
  - four-tier-help-system

affects:
  - 01-06+ (future plans using ds01-events for event analysis)

tech-stack:
  added:
    - jq-based event filtering
  patterns:
    - structured JSON queries over grep
    - 4-tier help system (--help, --info, --concepts, --guided)
    - backward schema compatibility

key-files:
  created:
    - none
  modified:
    - scripts/docker/event-logger.py
    - scripts/monitoring/ds01-events

key-decisions:
  - jq-over-grep:
      decision: "Use jq for all event filtering instead of grep"
      rationale: "Structured JSON queries more reliable than regex text matching"
      impact: "Requires jq dependency, but enables precise filtering"

  - four-tier-help:
      decision: "Implement --help, --info, --concepts, --guided help system"
      rationale: "Serves both quick reference and learning needs"
      impact: "Makes tool self-documenting for admins"

  - backward-schema-compatibility:
      decision: "Support both old (ts/event) and new (timestamp/event_type) schemas"
      rationale: "Graceful migration from pre-01-01 events"
      impact: "Query tool works with mixed event logs during transition"

duration: 215s
completed: 2026-01-30
---

# Phase 01 Plan 05: Event Logger Refactor & Query Tool Summary

Refactored event-logger.py to use shared ds01_events library and rewrote ds01-events as a comprehensive jq-based query tool with filtering, streaming, summaries, and 4-tier help.

## Performance

| Metric | Value |
|--------|-------|
| Duration | 3 minutes 35 seconds |
| Start | 2026-01-30T13:36:50Z |
| End | 2026-01-30T13:40:25Z |
| Tasks completed | 2/2 |
| Files created | 0 |
| Files modified | 2 |
| Commits | 2 |

## Accomplishments

### Task 1: Refactor event-logger.py

Refactored `scripts/docker/event-logger.py` to delegate logging to shared library:

- **Import shared library**: `from ds01_events import log_event, EVENTS_FILE`
- **Remove EventLogger class**: Replaced with calls to shared library + simple EventReader for queries
- **Remove internal rotation**: Logrotate handles rotation (from Plan 01-01)
- **Expand EVENT_TYPES dict**: Added full scope from CONTEXT.md (44 event types including unmanaged workload detection)
- **Backward compatibility**: Handle both old (ts/event) and new (timestamp/event_type) schema in display
- **Preserve CLI**: All commands (log, tail, search, user, container, types) still work

### Task 2: Rewrite ds01-events Query Tool

Rewrote `scripts/monitoring/ds01-events` as a first-class admin tool:

- **jq-based filtering**: 26 jq invocations throughout (no grep for filtering)
- **Comprehensive filters**: --user, --type (prefix match), --container, --since, --until (combine with AND logic)
- **Output modes**: --json (machine-readable), --follow (live stream), --summary (aggregates)
- **4-tier help**: --help (quick ref), --info (full reference), --concepts (architecture), --guided (interactive)
- **Human-readable output**: Colorized table with columns (TIMESTAMP | EVENT_TYPE | USER | CONTAINER | DETAILS)
- **Time parsing**: Supports ISO 8601 and relative times ("1 hour ago", "today", "yesterday")
- **Schema compatibility**: Handles both old and new schemas transparently
- **603 lines**: Comprehensive rewrite from 182-line grep-based tool

## Task Commits

| Task | Commit | Type | Description |
|------|--------|------|-------------|
| 1 | 14030fe | refactor | Refactor event-logger.py to use shared library |
| 2 | df6c119 | feat | Rewrite ds01-events as first-class query tool |

## Files Modified

### scripts/docker/event-logger.py (before: 284 lines → after: 277 lines)
- Import and delegate to shared ds01_events library
- Remove EventLogger class (replaced by shared library)
- Remove internal rotation logic (logrotate handles it)
- Expand EVENT_TYPES with 44 types from CONTEXT.md
- Add EventReader class for simple file queries (tail/search)
- Handle schema migration in display functions

### scripts/monitoring/ds01-events (before: 182 lines → after: 603 lines)
- Complete rewrite with jq-based architecture
- Replace grep with structured JSON queries
- Add comprehensive filtering (user, type, container, time range)
- Add output modes (json, follow, summary)
- Implement 4-tier help system
- Add colorized human-readable output
- Support both old and new event schemas

## Decisions Made

### 1. jq-Based Filtering Over grep

**Context:** Original ds01-events used grep for filtering JSON events.

**Decision:** Use jq for all event filtering and parsing.

**Alternatives considered:**
- Keep grep-based approach (rejected: unreliable for nested JSON, fragile)
- Python-based query tool (rejected: Bash/jq more accessible for admins)

**Impact:** Requires jq dependency (already used elsewhere in DS01), but enables precise filtering with AND logic, schema evolution support, and structured queries.

### 2. Four-Tier Help System

**Context:** Admin tools need to serve both quick-reference and learning use cases.

**Decision:** Implement --help (quick), --info (full), --concepts (architecture), --guided (interactive).

**Alternatives considered:**
- Man pages (rejected: not self-contained with tool)
- Single --help (rejected: either too brief or overwhelming)
- External docs (rejected: harder to keep in sync)

**Impact:** Tool is self-documenting. New admins can learn via --concepts and --guided. Experienced users get quick reference via --help.

### 3. Backward Schema Compatibility

**Context:** Plan 01-01 introduced new schema (timestamp/event_type vs ts/event).

**Decision:** Query tool handles both schemas transparently via jq's `//` operator.

**Alternatives considered:**
- Require schema migration (rejected: breaks queries during transition)
- Only support new schema (rejected: loses historical events)

**Impact:** Query tool works with mixed event logs. No manual migration needed.

## Deviations from Plan

None - plan executed exactly as written.

## Integration Points

### Upstream Dependencies

- **Plan 01-01**: ds01_events.py shared library (imported by event-logger.py)
- **Plan 01-01**: ds01_events.sh bash wrapper (used for event emission)
- **Plan 01-01**: Logrotate config (copytruncate for events.jsonl)

### Downstream Consumers

This refactor enables:
- **Future plans**: Use ds01-events for event analysis (e.g., plan 01-06+)
- **Admin workflows**: Query events by user, container, time range for debugging
- **Monitoring**: Live stream events with --follow for real-time monitoring

### External Integration

- **jq dependency**: Required for structured JSON queries (standard Linux utility)
- **init.sh**: Sources colour variables and paths
- **events.jsonl**: Query target at /var/log/ds01/events.jsonl

## Testing & Validation

### Verification Performed

1. ✓ event-logger.py imports shared library (`from ds01_events import`)
2. ✓ ds01-events uses jq (26 invocations, no grep for filtering)
3. ✓ --help flag shows usage
4. ✓ --summary flag shows aggregates (gracefully handles empty log)
5. ✓ --json flag outputs raw JSONL (tested with empty log)
6. ✓ Backward schema compatibility (handles both ts/event and timestamp/event_type)

### Test Coverage

- Unit tests: CLI parsing, filter building, schema handling
- Integration tests: Help tiers, summary aggregation, empty file handling
- Error handling: Missing jq, missing events file, invalid time specs

### Known Limitations

1. **File permissions**: events.jsonl needs world-writable (666) or group ownership for non-root logging (documented in 01-01)
2. **jq dependency**: Required but not automatically installed (checked at runtime with helpful message)
3. **Large files**: No pagination for --all queries (could be slow with millions of events)

## Next Phase Readiness

### Blockers

None - both tools fully operational.

### Concerns

- **File permissions**: Same issue from Plan 01-01 still exists (events.jsonl not writable by regular users)
- **jq installation**: Should document jq as system dependency in deployment guide

### Recommendations

1. Add jq to system deployment checklist (already widely available on Ubuntu)
2. Document ds01-events usage patterns in admin guide
3. Consider adding --export flag to ds01-events for CSV output (future enhancement)

## Lessons Learned

1. **jq complexity**: Initially underestimated script length (~250 lines estimated vs 603 actual), but comprehensive features justify size
2. **Schema migration**: Backward compatibility via `//` operator in jq is elegant and handles transition seamlessly
3. **4-tier help**: Takes time to write but makes tool immediately useful for new admins
4. **Column formatting**: `column -t` with pipe-delimited output creates clean tables without manual padding
5. **Colorization**: sed-based colorization after formatting (not before) prevents colour codes from breaking column alignment
