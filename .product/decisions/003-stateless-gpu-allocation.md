# ADR-003: Stateless GPU Allocation via Docker Labels

**Status:** Accepted
**Date:** 2026-01-30

## Context

GPU allocation state (which GPUs are assigned to which containers) must be tracked accurately. Stale state causes double-allocation (two containers assigned the same GPU) or phantom allocations (GPUs marked as used when they're free).

## Decision

Docker container labels are the single source of truth for GPU allocation. The allocator reads current state from Docker on each operation via `gpu-state-reader.py` rather than maintaining a persistent state file.

File-level state (`gpu-state.json`) serves as a cache, not the authority. If the cache diverges from Docker labels, Docker wins.

## Rationale

Docker labels are inherently consistent with container lifecycle — when a container is removed, its labels disappear automatically. A persistent state file requires explicit cleanup and can drift from reality after crashes or manual Docker operations.

## Alternatives Considered

- **Database (PostgreSQL/SQLite):** Reliable but adds a dependency. Database crashes would block all GPU allocation. Overkill for 4 GPUs.
- **Persistent file as authority:** Simpler reads but requires careful cleanup. Crashes can leave orphaned entries. DS01 experienced this with early file-based state.
- **etcd/Redis:** Distributed state stores. Unnecessary for single-server deployment.

## Consequences

- **Positive:** State is always consistent with Docker reality. No orphaned allocations after crashes. Recoverable by inspecting running containers.
- **Negative:** Each allocation operation reads Docker state (slightly slower than file cache hit). File locking still needed for the brief allocation window between "read state" and "apply labels".
- **Mitigated by:** 5-second lock timeout with fail-open prevents the locking overhead from becoming a bottleneck.
