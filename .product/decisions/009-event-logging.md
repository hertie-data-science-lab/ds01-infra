# ADR-009: JSONL Event Logging with PIPE_BUF Guarantee

**Status:** Accepted
**Date:** 2026-01-30

## Context

DS01 needs an audit trail of system events (container lifecycle, GPU allocation, enforcement actions). Multiple processes write events concurrently — the Docker wrapper, cron jobs, the ownership tracker daemon, and monitoring scripts.

The logging system must be:
- Concurrent-write safe (no interleaved events).
- Non-blocking (never delays the calling operation).
- Queryable (admin needs to search and filter events).
- Simple (no external dependencies like Elasticsearch or a database).

## Decision

Append-only JSONL (JSON Lines) format with a 4KB event size limit. Each event is a single JSON object on one line, written in a single `write()` syscall.

Key constraints:
- **4KB limit** exploits the POSIX PIPE_BUF guarantee: writes ≤ 4,096 bytes are atomic on Linux.
- Events exceeding 4KB are truncated (with a `.truncated` flag), not split.
- Writing never raises exceptions — returns `False` on failure (fail-open).
- Dual interface: Python (`from ds01_events import log_event`) and Bash (`log_event "type" ...`).
- Logrotate with `copytruncate` preserves open file descriptors.

## Rationale

PIPE_BUF atomicity eliminates the need for file locking on the event log. Multiple processes can write simultaneously without corruption. JSONL format is standard and queryable with `jq`, `grep`, and `awk`.

## Alternatives Considered

- **Structured logging to journald:** Good integration but harder to query historically and export.
- **SQLite event database:** Excellent for queries but requires file locking for concurrent writes. Adds complexity.
- **Syslog:** Standard but unstructured. Hard to include rich metadata (GPU UUIDs, container details).
- **External service (Elasticsearch, Loki):** Powerful but adds infrastructure dependency.

## Consequences

- **Positive:** Zero-dependency, concurrent-safe, queryable event log. Standard format supported by many tools.
- **Negative:** 4KB limit constrains event detail size (long container names or many GPU UUIDs may truncate). Plain files lack indexing (full scan for queries).
- **Mitigated by:** `ds01-events` CLI provides filtered queries. Logrotate manages file size. Truncation preserves event validity.
