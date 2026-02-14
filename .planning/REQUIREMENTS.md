# Requirements: DS01 Infrastructure

**Defined:** 2026-01-30
**Core Value:** Full control over GPU resources — every GPU process tracked, attributed, controllable

## v1 Requirements

Requirements for Milestone 1: Full Visibility & Control. Each maps to roadmap phases.

### Detection & Awareness

- [x] **DETECT-01**: System detects all GPU-using processes on host (not just containers) and attributes them to a user via /proc
- [x] **DETECT-02**: System detects containers launched via raw `docker run` (bypassing DS01 commands) and tracks them
- [x] **DETECT-03**: System detects VS Code dev containers and docker-compose containers and tracks them
- [x] **DETECT-04**: System provides real-time inventory of all GPU workloads regardless of launch method
- [x] **DETECT-05**: System handles containers created via Docker API (not CLI) that don't receive DS01 labels
- [x] **DETECT-06**: Single unified inventory of all GPU workloads (DS01-managed containers, unmanaged containers, host processes) queryable from one place

### Access Control

- [ ] **ACCESS-01**: Bare metal GPU access is restricted by default (users removed from video group or device access controlled)
- [ ] **ACCESS-02**: User-specific overrides allow designated users bare metal GPU access when needed
- [ ] **ACCESS-03**: Users cannot see other users' containers via `docker ps` or similar commands
- [ ] **ACCESS-04**: Users cannot exec into, stop, or remove other users' containers
- [ ] **ACCESS-05**: User isolation works without OPA (via Docker wrapper authorisation or equivalent)

### Resource Enforcement

- [ ] **ENFORCE-01**: CPU limits enforced per user via systemd cgroup slices
- [ ] **ENFORCE-02**: Memory limits enforced per user via systemd cgroup slices
- [ ] **ENFORCE-03**: IO bandwidth limits enforced per user (read/write) via cgroup v2
- [ ] **ENFORCE-04**: Disk usage limits enforced per user (quota or equivalent)
- [ ] **ENFORCE-05**: GPU allocation limits enforced for all container types (not just DS01-managed)
- [ ] **ENFORCE-06**: Resource limits configurable per user and per group via existing YAML config

### Lifecycle Management

- [x] **LIFE-01**: Idle timeout enforced for all container types (including dev containers and unmanaged)
- [x] **LIFE-02**: Max runtime enforced for all container types
- [x] **LIFE-03**: Containers in "created" state (never started) are detected and cleaned up
- [x] **LIFE-04**: Cleanup scripts handle containers without DS01/AIME labels (using multiple detection methods)
- [x] **LIFE-05**: GPU allocations released reliably when containers stop (no leaked allocations)
- [x] **LIFE-06**: CPU idle threshold tuned (current < 1% too strict, adjust to 2-5%)
- [x] **LIFE-07**: Container-stop timeout increased (current 10s too short for large containers)
- [x] **LIFE-08**: Per-user lifecycle overrides — exempt specific users/containers from idle timeout and max runtime (easy to toggle on/off via config)

### Labels & Standards

- [ ] **LABEL-01**: All containers use `ds01.*` label namespace consistently (deprecate `aime.mlc.*`)
- [ ] **LABEL-02**: Label migration path for existing containers (backward compatible)

### User Notifications

- [ ] **NOTIFY-01**: Users notified when their container is approaching idle timeout
- [ ] **NOTIFY-02**: Users notified when their container is approaching max runtime
- [ ] **NOTIFY-03**: Users notified when their GPU quota is nearly exhausted
- [ ] **NOTIFY-04**: Notification delivery via terminal message (wall/write) or container-visible mechanism

### Event Logging

- [x] **LOG-01**: Event log records all container lifecycle events (create, start, stop, remove)
- [x] **LOG-02**: Event log records GPU allocation and release events
- [x] **LOG-03**: Event log records unmanaged workload detection events
- [x] **LOG-04**: Events stored in structured format (JSON) queryable for audit

### CI/CD Foundation

- [x] **CICD-01**: Automated semantic versioning through CI pipeline (robust, replaces current fragile commitizen setup)

### Bug Fixes

- [ ] **FIX-01**: container-stats --filter "unknown flag" error resolved
- [ ] **FIX-02**: image-create line 1244 "creation: command not found" resolved
- [ ] **FIX-03**: image-update rebuild flow offers rebuild after Dockerfile update
- [ ] **FIX-04**: user-setup reads user's existing images correctly

## v2 Requirements

Deferred to Milestone 2 (Observability & Analytics). Tracked but not in current roadmap.

### Monitoring Stability

- **MON-01**: DCGM exporter runs reliably without crashing (auto-restart, health checks)
- **MON-02**: DS01 exporter stable with comprehensive metrics
- **MON-03**: Prometheus scraping all targets reliably

### Dashboards

- **DASH-01**: Lab manager operational dashboard showing real-time GPU/container/user status
- **DASH-02**: Per-user self-service dashboard showing own GPU-hours, quota usage, efficiency

### Historical Analytics

- **HIST-01**: Usage data retained long-term via VictoriaMetrics (1 year minimum)
- **HIST-02**: Visualise usage patterns over 1 week, 1 month, 1 year, all-time
- **HIST-03**: Quantify total GPU-hours, number of users, demand patterns

### Green Computing

- **GREEN-01**: GPU power consumption tracked per user/container
- **GREEN-02**: Carbon footprint estimated based on energy usage and grid intensity
- **GREEN-03**: Green metrics visible in dashboards

### GPU Health

- **HEALTH-01**: ECC error monitoring with alerts
- **HEALTH-02**: Thermal throttling detection
- **HEALTH-03**: Hardware degradation trends visible

### Alerting

- **ALERT-01**: Email notifications for critical system issues
- **ALERT-02**: Teams notifications for critical system issues
- **ALERT-03**: Alert tuning (appropriate thresholds, no alert fatigue)

## v3 Requirements

Deferred to Milestone 3 (Server Hygiene & Operations).

### Cleanup & Maintenance

- **CLEAN-01**: Departed user cleanup automated (files, containers, images)
- **CLEAN-02**: Docker image/build cache cleanup automated (preserve active images)
- **CLEAN-03**: Disk space monitoring with proactive cleanup triggers

### Linux Best Practices

- **LINUX-01**: Cron jobs migrated to systemd timers (Persistent=true, dependency management)
- **LINUX-02**: Log rotation via logrotate (replace custom log management)
- **LINUX-03**: Temp file management via tmpfiles.d
- **LINUX-04**: Event logging integrated with journald

### Infrastructure

- **INFRA-01**: Backup strategy for /home, docker volumes, config files, infra repo
- **INFRA-02**: Disaster recovery plan documented and tested
- **INFRA-03**: Onboarding/offboarding automation for semester transitions
- **INFRA-04**: Container image management (base updates, size limits)
- **INFRA-05**: Data directory structure with ACLs (/collaborative, /readonly, /scratch, /data)
- **INFRA-06**: Dependency management — shared lib caches, clean up host-installed packages

### CI/CD & Release

- **CICD-TEST-01**: Automated test suite runs on every commit (GitHub Actions)
- **CICD-03**: ds01-hub documentation published as GitHub Pages
- **CICD-04**: README positioned as open source offering (with MIT license if approved)

## Out of Scope

Explicitly excluded. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Kubernetes migration | Design for compatibility, don't migrate yet |
| MPS (Multi-Process Service) | Using MIG for GPU sharing instead |
| Triton inference server | Lower priority for teaching lab |
| Green computing gamification | Perverse incentives, complexity without value |
| Fine-grained RBAC | Single admin can't maintain; two-tier (user/admin) sufficient |
| Per-user container registry | Storage/maintenance burden; use Docker Hub + bind mounts |
| Real-time WebSocket dashboards | Polling every 10-30s sufficient for this workload |
| Auto-scaling to cloud | No budget allocated; manual cloud bursting only when explicitly requested |
| Complex data pipelines | Airflow/Prefect not needed |
| Feature stores | Not needed |
| Teaching-specific tools | Auto-grading not in DS01's scope |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| LOG-01 | Phase 1 | Complete |
| LOG-02 | Phase 1 | Complete |
| LOG-03 | Phase 1 | Complete |
| LOG-04 | Phase 1 | Complete |
| DETECT-01 | Phase 2 | Complete |
| DETECT-02 | Phase 2 | Complete |
| DETECT-03 | Phase 2 | Complete |
| DETECT-04 | Phase 2 | Complete |
| DETECT-05 | Phase 2 | Complete |
| DETECT-06 | Phase 2 | Complete |
| ACCESS-01 | Phase 3 | Pending |
| ACCESS-02 | Phase 3 | Pending |
| ACCESS-03 | Phase 3 | Pending |
| ACCESS-04 | Phase 3 | Pending |
| ACCESS-05 | Phase 3 | Pending |
| ENFORCE-01 | Phase 4 | Pending |
| ENFORCE-02 | Phase 4 | Pending |
| ENFORCE-03 | Phase 4 | Pending |
| ENFORCE-04 | Phase 4 | Pending |
| ENFORCE-05 | Phase 4 | Pending |
| ENFORCE-06 | Phase 4 | Pending |
| LIFE-01 | Phase 5 | Complete |
| LIFE-02 | Phase 5 | Complete |
| LIFE-03 | Phase 5 | Complete |
| LIFE-04 | Phase 5 | Complete |
| LIFE-05 | Phase 5 | Complete |
| LIFE-06 | Phase 6 | Complete |
| LIFE-07 | Phase 6 | Complete |
| LIFE-08 | Phase 6 | Complete |
| LABEL-01 | Phase 7 | Pending |
| LABEL-02 | Phase 7 | Pending |
| NOTIFY-01 | Phase 8 | Pending |
| NOTIFY-02 | Phase 8 | Pending |
| NOTIFY-03 | Phase 8 | Pending |
| NOTIFY-04 | Phase 8 | Pending |
| FIX-01 | Phase 9 | Pending |
| FIX-02 | Phase 9 | Pending |
| FIX-03 | Phase 9 | Pending |
| FIX-04 | Phase 9 | Pending |
| CICD-01 | Phase 1 | Complete |

**Coverage:**
- v1 requirements: 39 total
- Mapped to phases: 39 (100%)
- Unmapped: 0

---
*Requirements defined: 2026-01-30*
*Last updated: 2026-01-30 after roadmap creation*
