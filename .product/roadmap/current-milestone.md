# M1: Full Visibility & Control

DS01 sees and controls everything on the GPUs. Lifecycle works reliably. Users can't interfere with each other. Resource limits enforced comprehensively.

## Goal

Transform DS01 from partial visibility to full control over GPU resources. Build comprehensive detection of all GPU workloads, close enforcement bypass paths, extend resource limits, fix lifecycle bugs, and establish user isolation.

## Phases

| # | Phase | Goal | Status |
|---|-------|------|--------|
| 1 | Foundation & Observability | Event logging, monitoring stability, audit trail | Complete |
| 2 | Awareness Layer | Detect all GPU workloads regardless of launch method | Complete |
| 2.1 | GPU Access Control Research | Research HPC GPU access patterns, redesign bare metal restriction | Complete |
| 3 | Access Control | Bare metal restriction, user isolation, bypass prevention | Complete |
| 3.1 | Hardening & Deployment | Permissions manifest, GPU allocator bugs, deployment fixes | Complete |
| 3.2 | Architecture Audit | Validate phases 1-3.1 against SLURM/K8s/HPC patterns | Complete |
| 4 | Resource Enforcement | Per-user aggregate CPU, memory, GPU, pids via cgroup v2 | Complete |
| 5 | Lifecycle Bug Fixes | Container retirement, cleanup race conditions, GPU leak fixes | Complete |
| 6 | Lifecycle Enhancements | Per-group policies, exemptions, multi-signal idle detection | Complete |
| 7 | Label Standards | Migrate to ds01.* namespace with backward compatibility | Complete |
| 8 | User Notifications | Timeout warnings, quota alerts, TTY + container file delivery | Complete |
| 9 | Command Bug Fixes | Fix container-stats, image-create, image-update, user-setup | Not started |
| 10 | Integration & Validation | End-to-end testing, full coverage verification | Not started |

## Current Position

- **Progress:** 39 of ~41 plans executed (97%)
- **Phases complete:** 11 of 13 (phases 1-8 including inserted phases)
- **Remaining:** Phase 9 (command bug fixes), Phase 10 (integration validation)
- **Version:** 1.4.0

## What's Done

- **Detection:** All GPU workloads detected — DS01 containers, docker-compose, VS Code dev containers, raw docker, host GPU processes.
- **Access control:** User isolation via Docker wrapper. Bare metal GPU access restricted (video group). Three-layer GPU access architecture.
- **Resource enforcement:** Per-user aggregate limits via systemd cgroup v2 slices. Per-container limits via Docker flags. Two-layer enforcement.
- **Lifecycle:** Multi-signal idle detection (GPU + CPU + network). Two-level escalation warnings. Per-group policies with exemptions. Configurable SIGTERM grace periods.
- **Labels:** Clean ds01.* namespace with aime.mlc.* backward compatibility.
- **Notifications:** TTY + container file delivery. Idle/runtime escalation. Quota alerts with 4-hour cooldown.
- **Logging:** JSONL event log with 4KB atomic writes. Structured events queryable via ds01-events.
- **CI/CD:** Semantic versioning via GitHub Actions.

## What Remains

**Phase 9 — Command Bug Fixes:**
- `container-stats --filter` returns "unknown flag" error
- `image-create` line 1244 "creation: command not found"
- `image-update` rebuild flow broken after Dockerfile modification
- `user-setup` doesn't read user's existing images

**Phase 10 — Integration & Validation:**
- End-to-end testing of all M1 capabilities
- Verify all 39 requirements (test results documented)
- Documentation updates for new capabilities

## Execution Metrics

- **Total execution time:** 143 minutes across 39 plans
- **Average per plan:** 3.6 minutes
- **Inserted phases:** 3 (2.1, 3.1, 3.2) — responsive to discoveries during execution
