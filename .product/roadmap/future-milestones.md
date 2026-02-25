# Future Milestones

Milestones beyond M1. Each has defined goals and trigger conditions for starting.

## M2: Observability & Analytics

**Goal:** Prometheus/Grafana properly designed and stable. Lab manager gets an operational picture. Historical usage data for understanding demand and impact.

**Key deliverables:**
- Stabilise monitoring stack (DCGM exporter reliability, DS01 exporter metrics)
- Operational dashboards (real-time GPU usage, container activity, per-user breakdown)
- Historical usage analytics (1 week, 1 month, 1 year visualisations)
- Green computing metrics (energy tracking, carbon estimates)
- GPU hardware health monitoring (ECC errors, thermal throttling)
- Email/Teams alerting for critical issues
- User self-service analytics (own GPU-hours, efficiency, quota usage)

**Trigger:** M1 complete. Monitoring stack already deployed (Prometheus, Grafana, DCGM running as containers).

**Dependency:** SMTP credentials from IT for email alerting.

## M3: Server Hygiene & Operations

**Goal:** Cleanup automation, dependency management, Linux best practices, operational maturity.

**Key deliverables:**
- Departed user cleanup automation (semester transitions)
- Disk space optimisation (image/cache cleanup, stale containers)
- Cron → systemd timer migration (better dependency management)
- Backup and disaster recovery strategy
- Container image management (base updates, size limits)
- CI/CD expansion (automated testing on commits, GitHub Pages docs)
- Data directory structure with proper ACLs (/collaborative, /readonly, /scratch)

**Trigger:** M2 complete (need observability to measure hygiene improvements).

## M4: SLURM & Job Scheduling

**Goal:** Batch job scheduling for long-running training. Fair queuing when GPUs are contested.

**Key deliverables:**
- SLURM installation alongside DS01
- Clear interactive (DS01) vs batch (SLURM) boundary
- Queue management and fair-share scheduling
- Multi-node architecture readiness

**Trigger:** Demand signal — when GPU contention becomes a regular problem and interactive-only access is insufficient. Currently low urgency (4 GPUs, manageable user count).

## M5: Cloud Integration

**Goal:** Elastic capacity and cloud deployment when demand materialises.

**Key deliverables:**
- Cloud bursting (spin up cloud GPUs when local queue is long)
- SLURM cloud plugins (AWS/GCP integration)
- Cost controls (budget limits, user allocation)
- Portable containers (DS01 containers run on cloud ML platforms)
- Hybrid workflows (train locally, deploy to cloud)

**Trigger:** Budget allocation + sustained queue pressure. Currently no budget allocated for cloud resources.

## M6: Research Tooling & User Experience

**Goal:** Advanced tooling and interfaces for researchers.

**Key deliverables:**
- MLflow integration (experiment tracking, central server)
- JupyterHub (Jupyter as native interface, DS01 as spawner)
- Security hardening (container vulnerability scanning, secrets management)
- Web UI for lab manager (dashboards without SSH)

**Trigger:** User demand for specific tooling. Currently low urgency.

## Milestone Ordering Rationale

**Control → Observability → Hygiene → Scheduling → Cloud → Tooling**

You can't monitor what you can't see (M1 before M2). You can't clean what you can't track (M2 before M3). You don't need scheduling until resources are contested (M3 before M4). You don't need cloud until local capacity is exhausted (M4 before M5). Tooling builds on a stable, well-observed platform (last).
