# ADR-004: Fail-Open Design Philosophy

**Status:** Accepted
**Date:** 2026-01-30

## Context

DS01 operates as infrastructure on a shared GPU server. Infrastructure failures (broken config, stuck lock, missing state file) must not block user operations. A researcher who can't create a container because the event logger crashed is worse off than having a temporarily unlogged container.

## Decision

All DS01 infrastructure errors fail toward "allow" rather than "deny". Specific implementations:

- **Lock timeout (5s):** Proceed without lock, log warning.
- **Config read failure:** Use safe defaults for the user's group.
- **Event logging failure:** Skip the log entry, continue the operation.
- **Ownership detection failure:** Mark container as "unknown" owner, allow it.
- **Cgroup doesn't exist:** Allow container creation, cgroup will be created.
- **GPU allocator failure:** Show error to user but don't crash the wrapper.

Emergency escape hatches:
- `DS01_WRAPPER_BYPASS=1` — skip all wrapper logic.
- `DS01_ISOLATION_MODE=monitoring` — log denials but allow operations.
- `DS01_ISOLATION_MODE=disabled` — no ownership checks.

## Rationale

DS01 manages a research computing resource, not a banking system. The cost of blocking a researcher's work due to an infrastructure bug is higher than the cost of temporarily reduced enforcement. Enforcement gaps are detectable (dashboards, event logs) and correctable; lost research time is not.

## Alternatives Considered

- **Fail-closed:** Deny operations on any infrastructure error. Rejected — a single broken config file would shut down the entire server's container creation.
- **Degraded mode with user notification:** Allow but prominently warn. Partially adopted — warnings are logged and visible in dashboards, but not surfaced to users (to avoid confusion).

## Consequences

- **Positive:** Server remains functional even when DS01 components fail. Admin can fix issues gradually without emergency pressure.
- **Negative:** Silent failures can accumulate if monitoring isn't checked. An unnoticed broken config could run for hours with default limits.
- **Mitigated by:** Event logging, periodic sync jobs, and admin dashboards that surface anomalies.
