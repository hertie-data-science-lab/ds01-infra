# ADR-005: Cgroup v2 with Systemd Slices for Aggregate Enforcement

**Status:** Accepted
**Date:** 2026-02-06

## Context

DS01 needs to enforce aggregate resource limits per user — a user's total CPU, memory, and pids consumption across all their containers must not exceed their group's allocation. Docker's per-container limits (`--cpus`, `--memory`) are necessary but insufficient: a user could create multiple containers to consume unlimited aggregate resources.

## Decision

Use cgroup v2 unified hierarchy with systemd slices for per-user aggregate enforcement:
- Root slice: `ds01.slice`
- Group slice: `ds01-{group}.slice`
- User slice: `ds01-{group}-{user}.slice` (with resource limits via drop-in files)
- Docker wrapper injects `--cgroup-parent=ds01-{group}-{user}.slice` on every container creation.

Aggregate limits calculated as: per-container limit × max_containers_per_user.

## Rationale

Systemd natively manages cgroup v2. Using systemd slices gives:
- Automatic cgroup creation and cleanup via `systemctl`.
- Drop-in configuration files (no custom cgroup scripting).
- Visibility via `systemd-cgtop` and standard tooling.
- Kernel-level enforcement — no user-space polling needed for CPU/memory.

## Alternatives Considered

- **Manual cgroup scripting:** Create cgroups via filesystem operations. Fragile, no automatic cleanup, reimplements what systemd already does.
- **Docker-only limits (per-container):** Insufficient — doesn't constrain aggregate usage across containers.
- **Kubernetes resource quotas:** Requires Kubernetes. DS01 is single-server Docker.
- **Cgroup v1:** Legacy, separate hierarchies per controller, more complex. Server migrated to v2.

## Consequences

- **Positive:** Kernel-level enforcement (cannot be bypassed from user space). Automatic cleanup on container removal. Standard tooling for monitoring.
- **Negative:** Requires cgroup v2 (necessitated GRUB migration from v1). Systemd slice names must be sanitised from LDAP usernames (@ and . characters).
- **Accepted trade-off:** Cgroup v2 migration was a one-time cost; the operational simplicity is permanent.
