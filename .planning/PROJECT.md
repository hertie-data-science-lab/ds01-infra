# DS01 Infrastructure

## What This Is

A multi-user GPU container management platform for a university Data Science Lab, enabling students, researchers and faculty to deploy containerised ML workloads on shared NVIDIA A100 GPUs. Caters to varying experience levels: maximal abstraction for beginners (wizards, guided flows), full Docker/dev container control for advanced users. Built on AIME ML Containers with a 5-layer command hierarchy and universal Docker wrapper enforcement.

## Core Value

**Full control over GPU resources** — every GPU process tracked, attributed to a user, and controllable. No blind spots, no resource contention without visibility. If DS01 can't see it, it can't manage it — and the entire allocation model breaks down.

## Requirements

### Validated

- ✓ 5-layer command architecture (L0 Docker → L4 Wizards) — existing
- ✓ Universal Docker wrapper enforcement (cgroups, labels, GPU allocation) — existing
- ✓ Stateless GPU allocation with MIG support — existing
- ✓ Container lifecycle automation (idle timeout, max runtime, cleanup) — existing
- ✓ Monitoring stack deployed (Prometheus, Grafana, DCGM, DS01 Exporter) — existing
- ✓ Dev container integration via Docker wrapper — existing
- ✓ Resource limits configuration (YAML, groups, user overrides) — existing
- ✓ User onboarding wizards (user-setup, project-init, project-launch) — existing
- ✓ Per-user systemd cgroup containment (ds01.slice hierarchy) — existing
- ✓ Container type detection and classification — existing
- ✓ Admin dashboard and CLI tools — existing

### Active

#### Milestone 1: Full Visibility & Control

DS01 sees and controls everything on the GPUs. Lifecycle actually works. Users can't interfere with each other. Resource limits enforced comprehensively.

- [ ] Host GPU process detection — track non-container GPU usage with user attribution
- [ ] Bare metal access restriction — safely block direct GPU access outside containers (with user-specific overrides when needed)
- [ ] Unmanaged container awareness — detect and track containers launched via raw docker, VS Code dev containers, docker-compose (anything not via DS01 commands)
- [ ] Lifecycle bug fixes — containers escaping retirement, cleanup scripts not catching all cases
- [ ] Comprehensive resource enforcement — GPU, CPU, memory, IO, disk usage limits enforced per user
- [ ] User isolation — prevent users from interfering with each other's containers (replace failed OPA approach)
- [ ] Label standardisation — consistent `ds01.*` namespace across all containers
- [ ] User notifications — alert users when containers approaching retirement, quota limits, etc.

#### Milestone 2: Observability & Analytics

Prometheus/Grafana properly designed and stable. Lab manager gets operational picture. Historical usage for understanding demand and impact.

- [ ] Stabilise monitoring stack — fix exporters going down, reliable DCGM/DS01 exporter uptime
- [ ] Operational dashboards — real-time snapshot for lab manager (GPU usage, active containers, user activity)
- [ ] Historical usage analytics — visualise past usage (1 week, 1 month, 1 year, all-time) to quantify demand and impact
- [ ] Green computing metrics — carbon/energy tracking integrated into observability
- [ ] GPU hardware health — ECC errors, thermal throttling, hardware degradation monitoring
- [ ] Alerting — email/Teams notifications when problems occur
- [ ] Event logging — fix empty event log, comprehensive audit trail
- [ ] User self-service analytics — users can see their own GPU-hours, efficiency, quota usage

#### Milestone 3: Server Hygiene & Operations

Cleanup automation, dependency management, Linux best practices, operational maturity.

- [ ] Departed user cleanup — automated workflows for users who have left the university
- [ ] Disk space optimisation — cleanup old images, build caches, stale containers
- [ ] Dependency & library management — shared caches, clean up host-installed libs, fresh start
- [ ] Better use of Linux services — systemd timers, logrotate, tmpfiles.d, journald (replace fragile custom daemons)
- [ ] Backup & disaster recovery — /home dirs, docker volumes, config files, infra repo
- [ ] Onboarding/offboarding automation — semester transitions, bulk user provisioning
- [ ] Container image management — base image updates, shared registry, image size limits
- [ ] CI/CD for DS01 — automated testing on commits, expand beyond current 149 tests
- [ ] Automated semantic versioning — robust SemVer through CI pipeline (replace current fragile setup)
- [ ] Data directory structure — /collaborative, /readonly, /scratch, /data with proper ACLs
- [ ] README refresh — position as open source offering built on AIME/Docker/Prometheus/Grafana
- [ ] ds01-hub documentation site — publish as GitHub Pages

#### Milestone 4: SLURM & Job Scheduling

Batch job scheduling for long-running training, fair queuing when GPUs are contested.

- [ ] Batch job scheduling — SLURM alongside DS01 for long-running workloads
- [ ] Queue management — fair scheduling when GPUs are contested
- [ ] DS01/SLURM boundary — clear separation of interactive vs batch
- [ ] Multi-node readiness — architecture supports scaling to additional servers

#### Milestone 5: Cloud Integration

Elastic capacity and cloud deployment pathways when demand materialises.

- [ ] Cloud bursting — spin up cloud GPUs when local queue is long
- [ ] SLURM cloud plugins — AWS/GCP integration
- [ ] Cost controls — budget limits, user allocation
- [ ] Portable containers — ensure DS01 containers run on cloud ML platforms
- [ ] Cloud ML service integration — SageMaker, Vertex AI, Azure ML
- [ ] Hybrid workflows — train locally, deploy to cloud (or vice versa)

#### Milestone 6: Research Tooling & User Experience

Advanced tooling and interfaces for researchers.

- [ ] MLflow integration — experiment tracking, central server, quota integration
- [ ] JupyterHub — Jupyter as native interface, DS01 as spawner
- [ ] Security hardening — container vulnerability scanning, secrets management, network policies
- [ ] Web UI for lab manager — expose dashboards online (no SSH required)

### Out of Scope

- Kubernetes migration — design for compatibility, don't migrate yet
- MPS (Multi-Process Service) — using MIG for GPU sharing instead
- Triton inference server — lower priority for teaching lab
- Green computing gamification — future consideration
- AR/VR monitoring, voice control — not relevant
- Complex data pipelines (Airflow, Prefect) — not needed
- Feature stores — not needed
- Teaching-specific tools (auto-grading) — not in DS01's scope

## Context

**Existing system state (2026-01-30):**
- Monitoring stack deployed: Prometheus, Grafana, DCGM, Alertmanager all running
- DS01 Exporter as systemd service
- Event log empty (0 lines) — needs investigation
- OPA exists but disabled — Docker wrapper handles current enforcement; OPA attempt caused problems
- Some containers escaping lifecycle enforcement — active bug
- Three bypass paths undermining allocation: dev containers, raw docker, host GPU processes
- DCGM exporter has stability issues (crashes, needs restart)

**User population:**
- Department-scale: 30-200 users
- Mix of students (need abstraction), researchers (need control), faculty
- Domain users from AD/LDAP (username sanitisation handled)
- LDAP query access not yet available (scanning /home as workaround)

**Hardware:**
- On-premises NVIDIA A100s (4 GPUs) with MIG support
- Fixed infrastructure (no autoscaling currently)
- Single server

**Known bugs from TODO.md:**
- container-stats --filter returns "unknown flag" error
- image-create line 1244 bug ("creation: command not found")
- image-update rebuild flow broken
- user-setup doesn't read user's existing images
- Label mix of `ds01.*` and `aime.mlc.*`
- CPU idle threshold too strict (< 1%, consider 2-5%)
- Container-stop timeout too short (10s default)

**Dependencies/blockers:**
- SMTP credential needed from IT for email alerting (M2)
- Simon/Huy approval needed for open-sourcing (M3)
- LDAP query access blocked on IT (workaround: scanning /home)

**Codebase:** ~29K LOC, Python 3.10+ and Bash. See `.planning/codebase/` for architecture, structure, concerns analysis.

## Constraints

- **Backward compatible**: Existing containers must keep working
- **Minimal disruption**: Users actively using the system — changes must not break active workflows
- **No new heavy dependencies**: Prefer leveraging existing stack (systemd, Docker, Prometheus) over adding infrastructure
- **Single admin**: System administered by one person — automation and reliability are critical
- **First Linux server**: Admin is learning Linux server management — leverage established Linux patterns over custom solutions

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| MIG over MPS | Better isolation, A100 support | ✓ Good |
| Docker wrapper for universal enforcement | Intercepts all container creation without OPA complexity | ✓ Good |
| AIME ML Containers as base | 2.2% patch footprint, community images | ✓ Good |
| OPA abandoned for now | Hit implementation problems, Docker wrapper handles enforcement | ⚠️ Revisit — need alternative for user isolation |
| SLURM alongside (not replacing) DS01 | Clear interactive/batch separation | — Pending |
| DS01 must become aware of things it didn't create | Allocation model breaks if unmanaged containers exist | — Pending |
| Milestones ordered: control → observability → hygiene → SLURM → cloud → tooling | Can't monitor what you can't see; can't clean what you can't track | — Pending |

---
*Last updated: 2026-01-30 after initialization*
