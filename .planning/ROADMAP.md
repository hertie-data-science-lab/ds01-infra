# Roadmap: DS01 Infrastructure - Milestone 1

## Overview

Transform DS01 from partial visibility to full control over GPU resources. Build comprehensive detection of all GPU workloads (managed containers, unmanaged containers, host processes), close enforcement bypass paths, extend resource limits to complete spectrum (CPU, memory, IO, disk), fix lifecycle bugs causing GPU allocation leaks, and establish user isolation without OPA complexity. The journey follows awareness-first architecture: see everything first, then enforce comprehensively.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Foundation & Observability** - Event logging, monitoring stability, audit trail
- [ ] **Phase 2: Awareness Layer** - Detect all GPU workloads (containers, host processes, unmanaged)
- [ ] **Phase 3: Access Control** - Bare metal restriction, user isolation, bypass prevention
- [ ] **Phase 4: Comprehensive Resource Enforcement** - CPU, memory, IO, disk limits via cgroup v2
- [ ] **Phase 5: Lifecycle Bug Fixes** - Container retirement, cleanup race conditions, GPU allocation leaks
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
**Plans**: TBD

Plans:
- [ ] 01-01: TBD during planning

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
**Plans**: TBD

Plans:
- [ ] 02-01: TBD during planning

### Phase 3: Access Control
**Goal**: Users cannot bypass DS01 controls or interfere with each other. Bare metal GPU access restricted, user isolation enforced.
**Depends on**: Phase 2
**Requirements**: ACCESS-01, ACCESS-02, ACCESS-03, ACCESS-04, ACCESS-05
**Success Criteria** (what must be TRUE):
  1. Users removed from video group by default (bare metal GPU access restricted)
  2. Designated users can be granted bare metal GPU access via configuration override
  3. Users cannot see other users' containers via docker ps or similar commands
  4. Users cannot exec into, stop, or remove other users' containers
  5. User isolation enforced via Docker wrapper authorization without requiring OPA
**Plans**: TBD

Plans:
- [ ] 03-01: TBD during planning

### Phase 4: Comprehensive Resource Enforcement
**Goal**: CPU, memory, IO, and disk limits enforced per user across complete resource spectrum via cgroup v2.
**Depends on**: Phase 2
**Requirements**: ENFORCE-01, ENFORCE-02, ENFORCE-03, ENFORCE-04, ENFORCE-05, ENFORCE-06
**Success Criteria** (what must be TRUE):
  1. CPU limits enforced per user via systemd cgroup slices (measurable via cgroup stats)
  2. Memory limits enforced per user via systemd cgroup slices (containers OOM-killed when exceeded)
  3. IO bandwidth limits enforced per user (read/write) via cgroup v2 controllers
  4. Disk usage limits enforced per user via XFS project quotas or equivalent
  5. GPU allocation limits enforced for all container types (not just DS01-managed)
  6. Resource limits configurable per user and per group via existing resource-limits.yaml
**Plans**: TBD

Plans:
- [ ] 04-01: TBD during planning

### Phase 5: Lifecycle Bug Fixes
**Goal**: Container retirement works reliably. Cleanup scripts handle all container states. GPU allocations released without leaks.
**Depends on**: Phase 1, Phase 2
**Requirements**: LIFE-01, LIFE-02, LIFE-03, LIFE-04, LIFE-05
**Success Criteria** (what must be TRUE):
  1. Idle timeout enforced for all container types including dev containers and unmanaged containers
  2. Max runtime enforced for all container types
  3. Containers in "created" state (never started) detected and cleaned up within 24 hours
  4. Cleanup scripts handle containers without DS01/AIME labels using multiple detection methods
  5. GPU allocations released reliably when containers stop (verified via gpu_allocator.py status showing no leaks)
**Plans**: TBD

Plans:
- [ ] 05-01: TBD during planning

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
Phases execute in numeric order: 1 → 2 → 3 → 4 → 5 → 6 → 7 → 8 → 9 → 10

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Foundation & Observability | 0/TBD | Not started | - |
| 2. Awareness Layer | 0/TBD | Not started | - |
| 3. Access Control | 0/TBD | Not started | - |
| 4. Comprehensive Resource Enforcement | 0/TBD | Not started | - |
| 5. Lifecycle Bug Fixes | 0/TBD | Not started | - |
| 6. Lifecycle Enhancements | 0/TBD | Not started | - |
| 7. Label Standards & Migration | 0/TBD | Not started | - |
| 8. User Notifications | 0/TBD | Not started | - |
| 9. Command Bug Fixes | 0/TBD | Not started | - |
| 10. Integration & Validation | 0/TBD | Not started | - |
