# Roadmap: DS01 Infrastructure - Milestone 1

## Overview

Transform DS01 from partial visibility to full control over GPU resources. Build comprehensive detection of all GPU workloads (managed containers, unmanaged containers, host processes), close enforcement bypass paths, extend resource limits to complete spectrum (CPU, memory, IO, disk), fix lifecycle bugs causing GPU allocation leaks, and establish user isolation without OPA complexity. The journey follows awareness-first architecture: see everything first, then enforce comprehensively.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [x] **Phase 1: Foundation & Observability** - Event logging, monitoring stability, audit trail
- [x] **Phase 2: Awareness Layer** - Detect all GPU workloads (containers, host processes, unmanaged)
- [x] **Phase 2.1: GPU Access Control Research** - Research HPC/data centre GPU access patterns, redesign bare metal restriction based on industry practice (INSERTED)
- [ ] **Phase 3: Access Control** - Bare metal restriction, user isolation, bypass prevention
- [ ] **Phase 3.1: Hardening & Deployment Fixes** - Permissions manifest, GPU allocator bugs, complete Phase 3 deployment (INSERTED)
- [ ] **Phase 3.2: Architecture Audit & Code Quality** - Validate Phases 1–3.1 against HPC/industry standards, refactor, dead code removal (INSERTED)
- [x] **Phase 4: Comprehensive Resource Enforcement** - Per-user aggregate CPU, memory, GPU, pids enforcement via cgroup v2
- [x] **Phase 5: Lifecycle Bug Fixes** - Container retirement, cleanup race conditions, GPU allocation leaks
- [ ] **Phase 6: Lifecycle Enhancements** - Tuning, overrides, reliability improvements
- [ ] **Phase 7: Label Standards & Migration** - Consistent ds01.* namespace, backward compatibility
- [ ] **Phase 8: User Notifications** - Timeout warnings, quota alerts, terminal delivery
- [ ] **Phase 9: Command Bug Fixes** - container-stats, image-create, image-update, user-setup
- [ ] **Phase 10: Integration & Validation** - End-to-end testing, full coverage verification, documentation

## Phase Details

### Phase 1: Foundation & Observability
**Goal**: Observability infrastructure works reliably before adding complexity. Event logging functional, monitoring stable, alerts configured.
**Depends on**: Nothing (first phase)
**Requirements**: LOG-01, LOG-02, LOG-03, LOG-04, CICD-01
**Success Criteria** (what must be TRUE):
  1. Event log records all container lifecycle events (create, start, stop, remove) with timestamps and user attribution
  2. Event log records GPU allocation and release events in structured JSON format
  3. DCGM exporter runs reliably without crashing for 7+ days
  4. Alertmanager email configuration functional (test notification delivered)
  5. Admin can query event log for audit purposes via CLI or log viewer
  6. Automated semantic versioning via CI pipeline produces correct version tags on merge to main
**Plans**: 6 plans

Plans:
- [x] 01-01-PLAN.md — Shared event logging library (Python + Bash) and logrotate fix
- [x] 01-02-PLAN.md — DCGM exporter stability (systemd service with restart/stop handling)
- [x] 01-03-PLAN.md — Alertmanager dual-channel alerting (email + Teams) and alert rules
- [x] 01-04-PLAN.md — CI/CD pipeline (semantic-release replacing commitizen, ruff linting)
- [x] 01-05-PLAN.md — Refactor event-logger.py and rewrite ds01-events query tool
- [x] 01-06-PLAN.md — Instrument existing scripts with event logging calls

### Phase 2: Awareness Layer
**Goal**: System detects ALL GPU workloads regardless of how they were created. Zero blind spots.
**Depends on**: Phase 1
**Requirements**: DETECT-01, DETECT-02, DETECT-03, DETECT-04, DETECT-05, DETECT-06
**Success Criteria** (what must be TRUE):
  1. System detects containers launched via raw docker run (bypassing DS01 commands) within 60 seconds
  2. System detects VS Code dev containers and docker-compose containers within 60 seconds
  3. System detects host GPU processes (outside containers) and attributes them to a user via /proc
  4. Admin can query unified inventory showing all GPU workloads (DS01-managed, unmanaged containers, host processes) from single command
  5. Detection handles containers created via Docker API without DS01 labels
**Plans**: 3 plans

Plans:
- [x] 02-01-PLAN.md — Core workload detection scanner (container classification, host GPU process detection, inventory persistence)
- [x] 02-02-PLAN.md — Systemd timer/service units and deployment integration
- [x] 02-03-PLAN.md — ds01-workloads unified query command (table/wide/by-user/JSON output)

### Phase 2.1: GPU Access Control Research (INSERTED)
**Goal**: Research how HPCs, data centres, and multi-user GPU systems handle host vs container GPU access restriction. Audit current Phase 3 approach against industry practice. Produce a design document grounding the access control implementation in proven patterns.
**Depends on**: Phase 2
**Requirements**: ACCESS-01 (research-informed redesign)
**Success Criteria** (what must be TRUE):
  1. Research document covers how SLURM, Kubernetes, and bare-metal GPU clusters restrict host GPU access
  2. Current Phase 3 approach (device permissions, video group, nvidia wrappers) audited against findings
  3. Design decision documented: chosen approach with rationale, rejected alternatives with reasons
  4. Phase 3 plans updated or replaced to reflect research-informed design
  5. `container deploy` works end-to-end for a regular user (the bug that triggered this research is resolved)
**Plans**: 2 plans

Plans:
- [x] 02.1-01-PLAN.md — Design document + deployment verification (checkpoint: human-verify)
- [x] 02.1-02-PLAN.md — Update Phase 3 plan 03-03 + profile.d exemption logic

### Phase 3: Access Control (Code Complete)
**Goal**: Users cannot bypass DS01 controls or interfere with each other. Bare metal GPU access restricted, user isolation enforced.
**Depends on**: Phase 2
**Requirements**: ACCESS-01, ACCESS-02, ACCESS-03, ACCESS-04, ACCESS-05
**Success Criteria** (what must be TRUE):
  1. Users removed from video group by default (bare metal GPU access restricted)
  2. Designated users can be granted bare metal GPU access via configuration override
  3. Users cannot see other users' containers via docker ps or similar commands
  4. Users cannot exec into, stop, or remove other users' containers
  5. User isolation enforced via Docker wrapper authorization without requiring OPA
**Plans**: 3 plans (2 complete, 1 superseded → absorbed into Phase 3.1)

Plans:
- [x] 03-01-PLAN.md — Bare metal GPU restriction (nvidia-* wrappers, video group, admin CLI)
- [x] 03-02-PLAN.md — Docker wrapper container isolation (user filtering, ownership verification)
- [~] 03-03-PLAN.md — ~~Deployment integration~~ **SUPERSEDED** → absorbed into Phase 3.1 (never executed; deployment scope expanded after UAT audit)

### Phase 3.1: Access Control Completion & Hardening (INSERTED)
**Goal**: Complete Phase 3 deployment, fix design-implementation drift, fix systemic permissions/allocator bugs, and deliver a coherent, design-aligned access control system. Absorbs Phase 3 plan 03-03 scope plus all UAT audit fixes.
**Depends on**: Phase 3 (plans 03-01, 03-02)
**Requirements**: ACCESS-01 through ACCESS-05 (deployment), cross-phase audit gaps (permissions, GPU allocator, deploy pipeline)
**Success Criteria** (what must be TRUE):
  *Permissions & deploy pipeline:*
  1. Deterministic permissions manifest in deploy.sh — all scripts 755, config 644, state dirs per-policy, lib 755
  2. Non-admin user (h.baker) can run ds01-events, ds01-workloads, and other deployed commands
  3. deploy.sh self-bootstrap fixed — single run always applies all changes (no "run twice" requirement)
  4. deploy.sh deploys mlc-create as symlink with Python dependencies accessible
  5. All profile.d scripts deployed with correct permissions (0644, not 0600)
  *GPU allocator fixes:*
  6. GPU availability checker detects full GPUs when MIG is disabled (4x A100)
  7. GPU allocator loads .members files for correct group resolution
  *Bare metal access control (03-03 + design alignment):*
  8. Udev rules removed (99-ds01-nvidia.rules deleted, device permissions at 0666 defaults)
  9. Video group restricted to exempt users only (non-exempt users removed)
  10. Video group exemption logic in profile.d script works (grants + exempt_users + video group check)
  11. GPU notice library (.so) deployed with correct permissions for LD_PRELOAD
  12. MOTD updated to mention container-only GPU policy
  13. Docker wrapper isolation in enforcing mode (not monitoring)
  *End-to-end validation:*
  14. Exempt users bypass CUDA_VISIBLE_DEVICES block (grant dir traversable, config readable)
  15. container deploy works end-to-end for a regular user (h.baker)
  16. Event logging writable by non-root users (events.jsonl group-writable)
  17. Cross-phase UAT re-run: all 8 previously-found issues resolved
**Plans**: 4 plans

Plans:
- [ ] 03.1-01-PLAN.md — Deploy.sh permissions manifest, self-bootstrap, profile.d deployment, event log fix
- [ ] 03.1-02-PLAN.md — GPU allocator/checker fail-open hardening, verify full GPU + .members fixes
- [ ] 03.1-03-PLAN.md — Bare metal deployment: udev removal, video group restriction, nvidia wrappers, enforcing mode
- [ ] 03.1-04-PLAN.md — End-to-end validation script + human verification checkpoint

### Phase 3.2: Architecture Audit & Code Quality (INSERTED)
**Goal**: Validate all Phases 1–3.1 architecture and design decisions against SLURM/Kubernetes/HPC industry standards. Secondary: dead code removal, refactoring, and simplification applying Occam's Razor. Architecture validation takes priority over code polish.
**Depends on**: Phase 3.1
**Requirements**: Cross-cutting (architecture validation of all prior work)
**Success Criteria** (what must be TRUE):
  1. Every architectural decision from Phases 1–3.1 validated against SLURM/K8s/HPC best practices with pass/fail verdict
  2. Critical and high severity code quality issues identified and fixed
  3. Dead code removed, confirmed duplicate logic consolidated
  4. Planning documents (ROADMAP.md, STATE.md) reflect current reality
  5. Structured backlog of deferred items produced with severity and suggested phase
  6. Architecture documentation updated to reflect post-audit state
**Plans**: 4 plans

Plans:
- [x] 03.2-01-PLAN.md — Comprehensive audit: architecture validation, code quality review, planning doc assessment
- [x] 03.2-02-PLAN.md — Code refactoring: fix Critical+High issues, dead code removal
- [x] 03.2-03-PLAN.md — Config consolidation: SSOT hierarchy (deploy/runtime/state), generative templates
- [x] 03.2-04-PLAN.md — Architecture documentation updates, STATE.md/ROADMAP.md sync, deferred backlog capture

### Phase 4: Comprehensive Resource Enforcement
**Goal**: Per-user aggregate CPU, memory, GPU, and pids limits enforced via systemd cgroup v2 user slices. Existing per-container limits kept as second layer. Login quota display. Unified GPU quota in resource framework. (IO and disk deferred — infrastructure prerequisites not met.)
**Depends on**: Phase 2
**Requirements**: ENFORCE-01, ENFORCE-02, ENFORCE-05, ENFORCE-06 (ENFORCE-03 IO and ENFORCE-04 disk deferred)
**Success Criteria** (what must be TRUE):
  1. CPU limits enforced per user via systemd cgroup slices (measurable via cgroup stats)
  2. Memory limits enforced per user via systemd cgroup slices (containers OOM-killed when exceeded)
  3. GPU allocation limits enforced for all container types (not just DS01-managed)
  4. Resource limits configurable per user and per group via existing resource-limits.yaml
  5. Users see quota summary at SSH login
  6. PSI monitoring collects resource pressure metrics per user
**Plans**: 5 plans

Plans:
- [x] 04-01-PLAN.md — Config extension (aggregate section) and systemd slice drop-in generator
- [x] 04-02-PLAN.md — Docker wrapper cgroup driver verification and aggregate quota enforcement
- [x] 04-03-PLAN.md — GPU quota unification into aggregate resource framework
- [x] 04-04-PLAN.md — Login quota greeting and check-limits extension
- [x] 04-05-PLAN.md — PSI monitoring, OOM event logging, and integration tests

### Phase 5: Lifecycle Bug Fixes
**Goal**: Container retirement works reliably. Cleanup scripts handle all container states. GPU allocations released without leaks.
**Depends on**: Phase 1, Phase 2
**Requirements**: LIFE-01, LIFE-02, LIFE-03, LIFE-04, LIFE-05
**Success Criteria** (what must be TRUE):
  1. Idle timeout enforced for all container types including dev containers and unmanaged containers
  2. Max runtime enforced for all container types
  3. Containers in "created" state (never started) detected and cleaned up within 30 minutes
  4. Cleanup scripts handle containers without DS01/AIME labels using multiple detection methods
  5. GPU allocations released reliably when containers stop (verified via gpu_allocator.py status showing no leaks)
**Plans**: 4 plans

Plans:
- [x] 05-01-PLAN.md — GPU idle detection, grace period, devcontainer exemption, wall notifications
- [x] 05-02-PLAN.md — Max runtime wall notifications, 60s SIGTERM grace
- [x] 05-03-PLAN.md — Created-state cleanup, unlabelled container handling
- [x] 05-04-PLAN.md — Post-removal GPU health verification, cron schedule fix

### Phase 6: Lifecycle Enhancements
**Goal**: Lifecycle enforcement tuned for real-world usage patterns. Per-user overrides for research workflows.
**Depends on**: Phase 5
**Requirements**: LIFE-06, LIFE-07, LIFE-08
**Success Criteria** (what must be TRUE):
  1. CPU idle threshold tuned from < 1% to 2-5% (fewer false positives for dataset loading)
  2. Container-stop timeout increased from 10s to 60s (large containers stop gracefully)
  3. Admin can exempt specific users/containers from idle timeout via config toggle
  4. Admin can exempt specific users/containers from max runtime via config toggle
  5. Lifecycle overrides easy to enable/disable without code changes
**Plans**: TBD

Plans:
- [ ] 06-01: TBD during planning

### Phase 7: Label Standards & Migration
**Goal**: All containers use consistent ds01.* label namespace. Backward compatibility for existing containers.
**Depends on**: Nothing (independent)
**Requirements**: LABEL-01, LABEL-02
**Success Criteria** (what must be TRUE):
  1. All new containers created via DS01 commands receive ds01.* labels (not aime.mlc.*)
  2. Existing containers with aime.mlc.* labels continue working without modification
  3. Label migration path documented for manual container relabelling if needed
  4. Monitoring and cleanup scripts handle both ds01.* and aime.mlc.* label schemes
**Plans**: TBD

Plans:
- [ ] 07-01: TBD during planning

### Phase 8: User Notifications
**Goal**: Users receive timely alerts when containers approach limits or quotas. Notifications visible in terminal or container.
**Depends on**: Phase 5
**Requirements**: NOTIFY-01, NOTIFY-02, NOTIFY-03, NOTIFY-04
**Success Criteria** (what must be TRUE):
  1. User notified 15 minutes before container reaches idle timeout (wall message or container-visible file)
  2. User notified 30 minutes before container reaches max runtime
  3. User notified when GPU quota usage exceeds 80% of allocation
  4. Notifications delivered via terminal message (wall/write) or container-visible mechanism (e.g., /dev/shm)
**Plans**: TBD

Plans:
- [ ] 08-01: TBD during planning

### Phase 9: Command Bug Fixes
**Goal**: Known command bugs resolved. User-facing tools work correctly.
**Depends on**: Nothing (independent)
**Requirements**: FIX-01, FIX-02, FIX-03, FIX-04
**Success Criteria** (what must be TRUE):
  1. container-stats --filter command executes without "unknown flag" error
  2. image-create line 1244 "creation: command not found" error resolved
  3. image-update offers rebuild option after Dockerfile modification
  4. user-setup reads user's existing images correctly from Docker daemon
**Plans**: TBD

Plans:
- [ ] 09-01: TBD during planning

### Phase 10: Integration & Validation
**Goal**: All Milestone 1 capabilities verified end-to-end. Documentation updated. System ready for production use.
**Depends on**: Phases 1-9
**Requirements**: All v1 requirements (validation phase)
**Success Criteria** (what must be TRUE):
  1. All 38 v1 requirements tested and verified (test results documented)
  2. Unmanaged container (raw docker run) detected, tracked, and enforced within 60s
  3. Host GPU process (bare Python CUDA script) detected and attributed to user
  4. Cross-user container interference blocked (exec, stop, remove attempts rejected)
  5. Resource limits enforced across all dimensions (CPU, memory, IO, disk, GPU)
  6. Documentation updated with new capabilities (README, CLAUDE.md, user guides)
**Plans**: TBD

Plans:
- [ ] 10-01: TBD during planning

## Progress

**Execution Order:**
Phases execute in numeric order: 1 → 2 → **2.1** → 3 → **3.1** → **3.2** → 4 → 5 → 6 → 7 → 8 → 9 → 10

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation & Observability | 6/6 | ✓ Complete | 2026-01-30 |
| 2. Awareness Layer | 3/3 | ✓ Complete | 2026-01-30 |
| 2.1. GPU Access Control Research | 2/2 | ✓ Complete | 2026-01-31 |
| 3. Access Control | 2/3 | Code complete (03-03 → 3.1) | - |
| 3.1. Access Control Completion & Hardening | 3/3 | ✓ Complete | 2026-02-01 |
| 3.2. Architecture Audit & Code Quality | 4/4 | ✓ Complete | 2026-02-05 |
| 4. Comprehensive Resource Enforcement | 5/5 | ✓ Complete | 2026-02-06 |
| 5. Lifecycle Bug Fixes | 4/4 | ✓ Complete | 2026-02-11 |
| 6. Lifecycle Enhancements | 0/TBD | **Next** | - |
| 7. Label Standards & Migration | 0/TBD | Not started | - |
| 8. User Notifications | 0/TBD | Not started | - |
| 9. Command Bug Fixes | 0/TBD | Not started | - |
| 10. Integration & Validation | 0/TBD | Not started | - |
