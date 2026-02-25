# Functional Requirements

What DS01 must do, grouped by domain. Status reflects implementation state as of v1.4.0.

## Detection & Awareness

| ID | Requirement | Status | Phase |
|----|-------------|--------|-------|
| DETECT-01 | Detect all GPU-using processes on host and attribute to user via /proc | Implemented | 2 |
| DETECT-02 | Detect containers launched via raw `docker run` (bypassing DS01 commands) | Implemented | 2 |
| DETECT-03 | Detect VS Code dev containers and docker-compose containers | Implemented | 2 |
| DETECT-04 | Provide real-time inventory of all GPU workloads regardless of launch method | Implemented | 2 |
| DETECT-05 | Handle containers created via Docker API without DS01 labels | Implemented | 2 |
| DETECT-06 | Single unified inventory queryable from one place (`ds01-workloads`) | Implemented | 2 |

## Access Control

| ID | Requirement | Status | Phase |
|----|-------------|--------|-------|
| ACCESS-01 | Bare metal GPU access restricted by default (video group removal) | Implemented | 3, 3.1 |
| ACCESS-02 | User-specific overrides for bare metal GPU access via config | Implemented | 3, 3.1 |
| ACCESS-03 | Users cannot see other users' containers via `docker ps` | Implemented | 3 |
| ACCESS-04 | Users cannot exec/stop/remove other users' containers | Implemented | 3 |
| ACCESS-05 | User isolation via Docker wrapper (not OPA) | Implemented | 3 |

## Resource Enforcement

| ID | Requirement | Status | Phase |
|----|-------------|--------|-------|
| ENFORCE-01 | CPU limits enforced per user via systemd cgroup slices | Implemented | 4 |
| ENFORCE-02 | Memory limits enforced per user via systemd cgroup slices | Implemented | 4 |
| ENFORCE-03 | IO bandwidth limits enforced per user via cgroup v2 | Deferred | — |
| ENFORCE-04 | Disk usage limits enforced per user (quota or equivalent) | Deferred | — |
| ENFORCE-05 | GPU allocation limits enforced for all container types | Implemented | 4 |
| ENFORCE-06 | Resource limits configurable per user/group via YAML config | Implemented | 4 |

## Lifecycle Management

| ID | Requirement | Status | Phase |
|----|-------------|--------|-------|
| LIFE-01 | Idle timeout enforced for all container types (including dev containers) | Implemented | 5 |
| LIFE-02 | Max runtime enforced for all container types | Implemented | 5 |
| LIFE-03 | Containers in "created" state cleaned up within 30 minutes | Implemented | 5 |
| LIFE-04 | Cleanup handles containers without DS01/AIME labels | Implemented | 5 |
| LIFE-05 | GPU allocations released reliably when containers stop | Implemented | 5 |
| LIFE-06 | CPU idle threshold tuned to 2-5% (reduced false positives) | Implemented | 6 |
| LIFE-07 | Container-stop timeout configurable (60s default for GPU) | Implemented | 6 |
| LIFE-08 | Per-user lifecycle exemptions (idle timeout, max runtime) | Implemented | 6 |

## Labels & Standards

| ID | Requirement | Status | Phase |
|----|-------------|--------|-------|
| LABEL-01 | All containers use `ds01.*` label namespace | Implemented | 7 |
| LABEL-02 | Backward-compatible label migration (`aime.mlc.*` fallback) | Implemented | 7 |

## User Notifications

| ID | Requirement | Status | Phase |
|----|-------------|--------|-------|
| NOTIFY-01 | Users notified when container approaching idle timeout | Implemented | 8 |
| NOTIFY-02 | Users notified when container approaching max runtime | Implemented | 8 |
| NOTIFY-03 | Users notified when GPU quota nearly exhausted | Implemented | 8 |
| NOTIFY-04 | Notification delivery via TTY message + container file fallback | Implemented | 8 |

## Event Logging

| ID | Requirement | Status | Phase |
|----|-------------|--------|-------|
| LOG-01 | Event log records all container lifecycle events | Implemented | 1 |
| LOG-02 | Event log records GPU allocation and release events | Implemented | 1 |
| LOG-03 | Event log records unmanaged workload detection events | Implemented | 1 |
| LOG-04 | Events in structured JSON format, queryable for audit | Implemented | 1 |

## CI/CD

| ID | Requirement | Status | Phase |
|----|-------------|--------|-------|
| CICD-01 | Automated semantic versioning via CI pipeline | Implemented | 1 |

## Bug Fixes

| ID | Requirement | Status | Phase |
|----|-------------|--------|-------|
| FIX-01 | `container-stats --filter` "unknown flag" error resolved | Planned | 9 |
| FIX-02 | `image-create` line 1244 "creation: command not found" resolved | Planned | 9 |
| FIX-03 | `image-update` rebuild flow after Dockerfile modification | Planned | 9 |
| FIX-04 | `user-setup` reads user's existing images correctly | Planned | 9 |

## Summary

- **Total M1 requirements:** 39
- **Implemented:** 33 (85%)
- **Planned (Phase 9):** 4 (10%)
- **Deferred:** 2 (5%) — IO bandwidth (needs BFQ scheduler), disk quota (needs XFS migration)
