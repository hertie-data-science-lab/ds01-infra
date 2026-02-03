# Phase 1: Foundation & Observability - Context

**Gathered:** 2026-01-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Reliable observability infrastructure before adding complexity. Event logging functional with structured JSON, monitoring stack stable (DCGM 7+ days), Alertmanager configured with email + Teams webhook, audit query CLI enhanced, and automated semantic versioning via GitHub Actions CI pipeline.

</domain>

<decisions>
## Implementation Decisions

### Event Log Design
- **Comprehensive event scope**: Log container lifecycle (create/start/stop/remove), GPU alloc/release, user logins/sessions, auth events (Docker wrapper denials, permission checks), resource events (cgroup limit hits, OOM kills, quota warnings), errors, configuration changes, maintenance actions (cleanup runs, idle kills), and monitoring events (DCGM restarts, scrape failures)
- **Storage**: JSON lines file at `/var/log/ds01/events.jsonl` — append-only, logrotate-compatible, greppable with `jq`
- **Schema**: Standardised envelope per event — `timestamp`, `event_type`, `user`, `source`, `details{}` (Claude's discretion on exact field design)
- **Shared library**: Single logging library that all ds01 scripts import — Python module + bash function, both writing same format to same file (Claude decides implementation approach for bash/Python bridge)
- **Write mode**: Asynchronous / best-effort — actions proceed even if logging is slow
- **Failure mode**: Warn on stderr if event logging fails, but never block the original action
- **Rotation policy**: Claude's discretion based on expected volume

### Audit Query Interface
- **Tool**: Enhance existing `ds01-events` command (not a new command)
- **Output**: Human-readable table by default, `--json` flag for machine-readable
- **Live mode**: `--follow` flag for real-time event streaming
- **Help system**: Full 4-tier (--help, --info, --concepts, --guided)
- **Filters**: `--user`, `--type`, `--since`/`--until`, `--container` — all combine with AND logic
- **Result limit**: Last 50 events by default, `--limit N` to override, `--all` for everything
- **Summary mode**: `--summary` flag for aggregate view (counts by type, by user, time distribution)

### Alerting Behaviour
- **Alert triggers**: Monitoring stack health (DCGM down, Prometheus scrape failures, Grafana unreachable) + GPU issues (XID errors, temp warnings, allocation failures)
- **DCGM stability**: Simple down/up alerts only — no restart frequency tracking
- **Recipients**: Single admin email address for all alerts
- **Grouping**: Aggressive grouping — group by alert type, 5 min wait for related alerts to batch
- **Maintenance**: Configurable silences via Alertmanager UI for maintenance windows
- **Channels**: Email + Microsoft Teams webhook
- **Teams webhook**: Configure actual Teams incoming webhook connector (URL to be provided)

### CI/CD Versioning
- **Platform**: GitHub Actions
- **Versioning**: Semantic versioning (MAJOR.MINOR.PATCH) with hybrid bump determination — auto-suggest from conventional commits, manual approval before tagging
- **CI scope**: Ruff linting on PRs + version tagging on merge to main (no test suite in Phase 1)
- **Changelog**: Auto-generated CHANGELOG.md from conventional commit history on each version tag

### Claude's Discretion
- Log rotation policy (daily/weekly/size-based, retention period)
- Exact JSON event schema field names and structure
- Bash/Python logging bridge implementation (CLI wrapper vs bash function vs both)
- Alertmanager rule thresholds and timing details
- DCGM stability fix approach
- Version bump tooling choice (release-please, semantic-release, custom)
- Exact GitHub Actions workflow structure

</decisions>

<specifics>
## Specific Ideas

- Event log should be extensible — schema established in Phase 1 and instrumented progressively across the milestone as scripts are touched
- `ds01-events` should feel like a first-class admin tool, not a log file wrapper
- Teams webhook for alert notifications alongside email
- Hybrid versioning: CI suggests bump from commits, admin confirms before tag is created

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-foundation-observability*
*Context gathered: 2026-01-30*
