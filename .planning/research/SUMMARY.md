# Project Research Summary

**Project:** DS01 Infrastructure Milestone Enhancements
**Domain:** Multi-user GPU container management platform evolution
**Researched:** 2026-01-30
**Confidence:** HIGH

## Executive Summary

DS01 is a production GPU container management platform built on Docker + systemd cgroups + Prometheus, currently serving 30-200 university users. Research reveals the system has strong foundations (universal Docker wrapper, hierarchical cgroup enforcement, GPU allocation tracking) but three critical bypass paths undermine the core value proposition of full control: unmanaged containers, raw Docker access, and host GPU processes outside containers.

The recommended evolution path is **awareness-first architecture** - build comprehensive detection of all GPU-using workloads (containers and host processes) before extending enforcement. This differs from typical approaches that assume the platform created everything. Key technologies include Linux cgroups v2 for comprehensive resource enforcement (CPU, memory, IO, disk), nvidia-smi + /proc parsing for host process detection, Docker events API for real-time container tracking, and VictoriaMetrics for long-term historical analytics. The architecture extends existing 5-layer command hierarchy with a new awareness layer underneath, preserving backward compatibility.

Critical risks include: CVE-2025-23266 (NVIDIA Container Toolkit privilege escalation - patch immediately), enforcement bypass via --cgroup-parent overrides, container lifecycle cleanup race conditions causing GPU allocation leaks, and alert fatigue from poorly tuned monitoring. Mitigation strategies emphasize gradual rollout with feature flags, detection before enforcement, and conservative automation with mandatory dry-run modes. The system must remain operationally simple for a single administrator learning Linux, favouring systemd timers and standard Linux patterns over custom daemons.

## Key Findings

### Recommended Stack

Research prioritises Linux-native solutions that integrate with the existing Docker + systemd + Prometheus stack, avoiding heavy new infrastructure. The stack extends proven foundations rather than replacing them.

**Core technologies:**
- **cgroups v2 + systemd resource-control**: Comprehensive CPU, memory, IO, disk enforcement via systemd slice configuration - extends existing ds01.slice hierarchy without breaking it
- **VictoriaMetrics**: Long-term Prometheus storage with 10x better compression - simpler than Thanos, lower resource usage, no object storage dependency
- **Docker events API**: Real-time container lifecycle tracking replaces polling - foundation for event-driven enforcement and audit logging
- **nvidia-smi + pyNVML**: Authoritative GPU process detection and power consumption tracking - enables host process detection and carbon metrics
- **XFS project quotas**: Per-user disk space enforcement - native filesystem support, no separate quota files to corrupt
- **systemd timers**: Replace cron for lifecycle automation - persistent execution, dependency management, integrated logging

**What NOT to use:**
- Docker authorization plugins (OPA failed, fail-open by default when crashed)
- cgroups v1 (deprecated, fragmented hierarchy)
- Kubernetes (overkill for single server, massive complexity)
- Custom syslog setup (journald is systemd-native and sufficient)

### Expected Features

Research identifies table stakes (users expect these), differentiators (competitive advantage), and anti-features (commonly requested but problematic).

**Must have (table stakes):**
- Comprehensive GPU allocation enforcement - No bypass paths via dev containers, raw docker, or host processes
- Multi-tenancy isolation - Users cannot interfere with each other's containers
- Hierarchical resource quotas - CPU, memory, IO, disk limits enforced via cgroups
- Container lifecycle automation - Idle timeout, max runtime, reliable cleanup without race conditions
- User attribution - Every GPU process traceable to a user
- Audit trail - Event logging functional (currently empty at 0 lines)
- Basic monitoring dashboards - Grafana + Prometheus stable (DCGM currently crashes)
- User notifications - Alerts when containers stop, approach limits, or fail

**Should have (competitive advantage):**
- Full workload visibility - DS01 sees EVERYTHING on GPUs (managed containers, unmanaged containers, dev containers, host processes) - zero blind spots
- Universal enforcement - Docker wrapper intercepts ALL container creation including VS Code dev containers and docker-compose
- Historical usage analytics - Users see GPU-hours over week/month/year for impact reporting
- Green computing metrics - Carbon/energy tracking integrated into dashboards
- Beginner-to-expert UX - L4 wizards for beginners, L2 atomic commands for experts
- Intelligent cleanup - ML-aware idle detection understands dataset loading vs actual idleness

**Defer (v2+):**
- SLURM integration - Wait for actual batch job demand
- Dynamic quota borrowing - Complex, wait until utilisation consistently high
- JupyterHub native interface - Wait for user demand
- Cloud bursting - Wait for budget and queue pressure
- Multi-node support - Wait for second server

### Architecture Approach

Evolution maintains backward compatibility by adding an awareness layer underneath the existing 5-layer command hierarchy (L5 Wizards → L4 Orchestrators → L3 Atomic → L2 Docker Wrapper → L1 AIME → L0 Docker). The awareness layer discovers reality (all containers and host processes) before policy enforcement acts on it.

**Major components:**

1. **Awareness Layer (NEW)** - Discovery subsystem with three scanners: Container Scanner (docker ps -a + label inspection for managed/unmanaged classification), Host Process Scanner (nvidia-smi + /proc/<pid> for user attribution), Docker Events Listener (real-time lifecycle tracking). Outputs unified state files (/var/lib/ds01/containers.json, host-processes.json, gpu-allocations.json) consumed by enforcement and monitoring.

2. **Enforcement Layer (ENHANCED)** - Extends existing systemd cgroups from CPU/memory to IO/disk/tasks using resource-control directives. Docker wrapper adds authorization checks (prevent cross-user container operations). Lifecycle enforcement migrates from polling cron jobs to event-driven triggers. User isolation via wrapper authorization (simpler than failed OPA approach).

3. **Observability Layer (ENHANCED)** - Docker events daemon populates currently-empty event log. DCGM Exporter stability fixes (systemd restart policies, resource limits). DS01 Exporter adds unmanaged workload metrics. VictoriaMetrics for long-term storage (Prometheus keeps 7-day fast queries, Victoria stores 1+ year). Alertmanager email/Teams configuration. Operational dashboards for cleanup stats and lifecycle events.

**Key architectural properties:**
- Non-breaking: Existing L0-L5 hierarchy untouched, awareness sits underneath
- Discovery-first: System discovers reality then applies policy (vs assuming it created everything)
- Event-driven: Real-time Docker events replace polling where possible
- Backward compatible: Feature flags enable gradual rollout, old containers continue working

### Critical Pitfalls

Research identified 8 critical pitfalls with prevention strategies ranked by severity.

1. **NVIDIA Container Toolkit CVE-2025-23266 (CRITICAL)** - Three-line Dockerfile can escape container isolation and gain root on host via LD_PRELOAD exploitation. Affects all multi-tenant GPU systems. **Prevention:** Immediate upgrade to nvidia-ctk >= 1.17.8, or workaround via config.toml to disable cuda-compat-lib-hook. **Address:** IMMEDIATE before Milestone 1.

2. **Enforcement bypass via --cgroup-parent override (CRITICAL)** - Users can escape resource limits by placing containers outside ds01.slice hierarchy. Docker daemon doesn't reject overrides by default. **Prevention:** Docker wrapper must reject or override cgroup-parent flags before exec, add monitoring for containers outside ds01.slice. **Address:** M1 Phase 1 Foundation.

3. **Container lifecycle cleanup race conditions (HIGH)** - Containers escape retirement due to state transition races (Created state stuck indefinitely, restart between stop and cleanup, cleanup fails with "no such container"). Causes GPU allocation leaks. **Prevention:** Atomic state transitions using labels, comprehensive state filtering (created/running/paused/exited/dead), idempotent cleanup, single coordinator. **Address:** M1 Phase 1 Foundation.

4. **OPA fail-open trap (HIGH)** - Docker authorization plugins fail open when crashed/unavailable. Silent security degradation, users gain unrestricted access during outages. **Prevention:** If reconsidering OPA alternative, test fail modes first. Docker wrapper approach actually safer. **Address:** M1 Phase 2 User Isolation.

5. **Process detection without context creates false positives (MEDIUM)** - nvidia-smi shows host view, doesn't know container namespaces. Jupyter kernels, init scripts, DCGM exporter itself trigger alerts. **Prevention:** Multi-step correlation (nvidia-smi PID → /proc/PID/cgroup → container ID → user), whitelist infrastructure, 60s grace period, context-rich alerts. **Address:** M1 Phase 3 Process Detection.

6. **Backward compatibility breaks during gradual rollout (MEDIUM)** - Production system has existing state. New enforcement can kill active containers mid-rollout. **Prevention:** Feature flags, graceful degradation, canary users, migration window, dry-run mode, instant rollback plan. **Address:** ALL PHASES.

7. **Alert fatigue from poorly tuned monitoring (MEDIUM)** - Default thresholds too sensitive, hundreds of alerts/day, real problems drown in noise. **Prevention:** Longer evaluation windows (5min not 5s), recovery thresholds, severity levels, baseline observation for 2 weeks, weekly tuning sprints. **Address:** M2 Phase 1 Monitoring Foundation.

8. **Automation without safeguards causes data loss (HIGH)** - Cleanup scripts delete active containers with unsaved work at machine speed. **Prevention:** Mandatory dry-run, incremental scope (1 item at a time), user notification 24h before deletion, active session detection, checkpoint validation, backup before bulk ops, escape hatches (ds01.protect=true). **Address:** M3 Phase 2 Cleanup Automation.

## Implications for Roadmap

Based on combined research findings, recommended structure addresses bypass paths first (awareness + enforcement), then builds observability, then operational maturity. Order reflects dependency chains and risk mitigation.

### Phase Structure Overview

**5 milestones, 12-14 phases, 12-14 weeks**

1. **Milestone 1: Full Visibility & Control (Weeks 1-7)** - Fix bypass paths, comprehensive detection, complete enforcement
2. **Milestone 2: Observability & Analytics (Weeks 8-10)** - Stabilise monitoring, historical data, operational dashboards
3. **Milestone 3: Server Hygiene (Weeks 11-12)** - Automation maturity, cleanup, backup/DR
4. **Milestone 4: Batch Integration (Future)** - SLURM for batch workloads when demand materializes
5. **Milestone 5: Cloud Bursting (Future)** - Hybrid on-prem/cloud when budget allocated

### Milestone 1: Full Visibility & Control (Weeks 1-7)

**Goal:** Deliver core value proposition - DS01 has complete control over GPU resources with zero bypass paths.

**Phase 1.1: Foundation (Weeks 1-2)**
- **Rationale:** Observability must work before adding complexity. Can't debug what you can't see.
- **Delivers:** Docker events daemon, functional event logging, DCGM exporter stability, Alertmanager email config
- **Addresses pitfalls:** Lifecycle race conditions (comprehensive state tracking), alert fatigue foundation (monitoring baseline)
- **Features:** Audit trail functional, monitoring stability
- **Stack:** Docker events API, systemd service, Prometheus Alertmanager
- **Research flag:** Standard patterns, skip phase research

**Phase 1.2: Awareness Layer (Weeks 3-4)**
- **Rationale:** Can't enforce what you can't see. Detection before enforcement.
- **Delivers:** Container scanner (all containers, managed/unmanaged classification), host process scanner (nvidia-smi + user attribution), unified state files
- **Addresses pitfalls:** Process detection false positives (multi-step correlation), enforcement blind spots
- **Features:** Full workload visibility differentiator, user attribution for ALL GPU processes
- **Stack:** nvidia-smi, /proc parsing, Docker API, file locking for atomicity
- **Research flag:** Complex integration, may need phase-specific research for /proc → container correlation edge cases

**Phase 1.3: Comprehensive Resource Enforcement (Weeks 5-7)**
- **Rationale:** Extend cgroup controls to complete resource spectrum, close bypass paths.
- **Delivers:** Systemd slice IO/disk/tasks limits, Docker wrapper authorization (cross-user operation blocking), cgroup-parent override rejection, host process quota policy
- **Addresses pitfalls:** Enforcement bypass via cgroup-parent (wrapper rejects), backward compatibility (feature flags, gradual rollout)
- **Features:** Multi-tenancy isolation, comprehensive quota enforcement
- **Stack:** systemd resource-control directives, XFS quotas
- **Architecture:** Enforcement layer enhancements
- **Research flag:** Standard systemd patterns, skip phase research

### Milestone 2: Observability & Analytics (Weeks 8-10)

**Goal:** Operational visibility for lab manager, historical analytics for impact reporting.

**Phase 2.1: Monitoring Stabilisation (Week 8)**
- **Rationale:** Foundation must be stable before building analytics on top.
- **Delivers:** DCGM exporter resource limits, restart policies, scrape interval tuning, metric optimisation
- **Addresses pitfalls:** Alert fatigue (tuned thresholds after baseline), monitoring crashes
- **Features:** Monitoring dashboards stable and reliable
- **Stack:** Prometheus best practices, systemd service hardening
- **Research flag:** Standard Prometheus patterns, skip phase research

**Phase 2.2: Historical Analytics (Week 9)**
- **Rationale:** Need long-term data for impact reports, funding justification, usage patterns.
- **Delivers:** VictoriaMetrics deployment, Prometheus recording rules (daily/weekly/monthly aggregations), user self-service dashboard (GPU-hours usage)
- **Addresses pitfalls:** No historical data retention (7+ days now accessible)
- **Features:** Historical usage analytics differentiator
- **Stack:** VictoriaMetrics single-node, Prometheus remote write
- **Research flag:** VictoriaMetrics integration may need phase research if issues arise

**Phase 2.3: Green Computing Metrics (Week 10)**
- **Rationale:** Sustainability differentiator, aligns with university goals.
- **Delivers:** pyNVML power consumption tracking, carbon metrics (ds01_carbon_grams_total), Grafana green computing dashboard
- **Addresses pitfalls:** None directly, but builds on stable monitoring foundation
- **Features:** Green computing differentiator
- **Stack:** pyNVML, Green Algorithms methodology
- **Research flag:** Carbon intensity data sourcing may need research (API vs hardcoded)

### Milestone 3: Server Hygiene (Weeks 11-12)

**Goal:** Reduce operational burden, automate maintenance, prepare for disaster recovery.

**Phase 3.1: Linux Best Practices (Week 11)**
- **Rationale:** Replace ad-hoc approaches with systemd-native patterns for maintainability.
- **Delivers:** Cron → systemd timers migration, logrotate configuration, tmpfiles.d for directory management
- **Addresses pitfalls:** Custom daemon complexity (use systemd patterns)
- **Features:** Server hygiene operational maturity
- **Stack:** systemd timers, logrotate, tmpfiles.d
- **Research flag:** Standard Linux patterns, skip phase research

**Phase 3.2: Cleanup Automation (Week 12)**
- **Rationale:** Reduce manual toil, free disk space, but conservatively to avoid data loss.
- **Delivers:** Event-driven cleanup triggers (not polling), departed user automation, disk space optimisation, dry-run mandatory mode
- **Addresses pitfalls:** Automation data loss (mandatory dry-run, user notification, incremental scope)
- **Features:** Intelligent cleanup differentiator
- **Stack:** Docker events triggers, systemd timers for periodic reconciliation
- **Research flag:** Skip phase research (builds on Phase 1.1 events foundation)

### Milestone 4: Batch Integration (Future, ~4 weeks)

**Trigger:** User demand for batch scheduling, queue pressure, interactive/batch workload separation needed.

**Phase 4.1: SLURM Deployment**
- **Rationale:** Batch workloads benefit from queuing, job scripts, dependency chains.
- **Delivers:** SLURM installation alongside DS01, GPU GRES configuration, DS01 as SLURM execution backend
- **Features:** Batch job support
- **Stack:** SLURM workload manager
- **Research flag:** NEEDS PHASE RESEARCH - SLURM + Docker + GPU integration is complex, sparse documentation

### Milestone 5: Cloud Bursting (Future, ~3 weeks)

**Trigger:** On-prem capacity consistently saturated, budget allocated for cloud overflow.

**Phase 5.1: Hybrid Orchestration**
- **Rationale:** Cost-effective capacity expansion without buying hardware.
- **Delivers:** Cloud provider integration (AWS/GCP/Azure), burst policy (cost thresholds), user opt-in mechanism
- **Features:** Elastic capacity
- **Research flag:** NEEDS PHASE RESEARCH - Hybrid orchestration, cost management, data transfer

### Phase Ordering Rationale

1. **Foundation first** (M1.1) - Observability enables debugging of subsequent phases
2. **Detection before enforcement** (M1.2 before M1.3) - See the problem before auto-killing processes
3. **Core enforcement before polish** (M1 before M2) - Value delivery beats nice-to-haves
4. **Stable monitoring before analytics** (M2.1 before M2.2) - Can't build analytics on crashing exporters
5. **Hygiene after core functionality** (M3 after M1-M2) - Polish matters, but functionality first
6. **Batch/cloud deferred** (M4-M5) - Wait for demand signals, don't over-engineer

**Dependency chains identified:**
- Event logging (M1.1) → Awareness state (M1.2) → Enforcement actions (M1.3)
- Monitoring stability (M2.1) → Historical analytics (M2.2) → Green metrics (M2.3)
- Foundation events (M1.1) → Event-driven cleanup (M3.2)

### Research Flags

**Phases needing deeper research during planning:**
- **Phase 1.2 (Awareness):** /proc → container correlation edge cases, handling ephemeral containers < 30s
- **Phase 2.2 (Historical Analytics):** VictoriaMetrics integration if remote write issues arise
- **Phase 2.3 (Green Computing):** Carbon intensity data sourcing (API subscription vs hardcoded values)
- **Phase 4.1 (SLURM):** SLURM + Docker + GPU integration (complex, sparse documentation)
- **Phase 5.1 (Cloud Bursting):** Hybrid orchestration, cost controls, data transfer optimisation

**Phases with standard patterns (skip research):**
- **Phase 1.1 (Foundation):** Docker events API, systemd services - well-documented
- **Phase 1.3 (Enforcement):** systemd resource-control - official kernel feature
- **Phase 2.1 (Monitoring):** Prometheus best practices - established patterns
- **Phase 3.1 (Linux Best Practices):** systemd timers, logrotate - standard Linux tooling
- **Phase 3.2 (Cleanup Automation):** Builds on Phase 1.1 foundation

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Linux-native solutions, official kernel features, production-proven tools. cgroups v2, systemd, Prometheus, VictoriaMetrics all mature. NVIDIA Container Toolkit CVE patching critical. |
| Features | HIGH | Table stakes clearly identified via competitor analysis (SLURM, Run:ai, K8s GPU Operator). Differentiators align with university environment. Anti-features validated against operational burden. |
| Architecture | HIGH | Awareness-first architecture solves bypass path problem systematically. Non-breaking evolution preserves existing investment. Clear component boundaries and integration points. |
| Pitfalls | HIGH | CVE-2025-23266 (CRITICAL vulnerability), enforcement bypass, lifecycle races, alert fatigue all well-documented with concrete prevention strategies. Context-specific warnings for single-admin environment. |

**Overall confidence:** HIGH

Research quality is excellent - comprehensive coverage, authoritative sources (official docs, kernel documentation, CVE bulletins), practical focus on operational reality. Recommendations are opinionated and actionable.

### Gaps to Address

1. **Carbon intensity data source** - Research mentions hardcoding UK grid intensity (~200g CO₂/kWh) or API integration (WattTime, Electricity Maps). Need to decide during Phase 2.3 planning: Is there a university contract with carbon API provider? If not, which regional grid intensity value to use?

2. **User namespace migration path** - STACK.md rates Docker userns-remap confidence as MEDIUM due to volume ownership remapping requirements. Need detailed testing plan before production rollout: How to migrate existing containers? What breaks? What's the rollback procedure?

3. **SLURM integration specifics** - Deferred to M4 but flagged as needing research. If demand emerges earlier than expected, what's the fast-path to basic SLURM? Should DS01 act as SLURM execution backend, or run parallel?

4. **Alertmanager email credentials** - Stack research shows email config examples but not how to securely manage SMTP password. Address during Phase 1.1: Use `/etc/alertmanager/smtp_password` file, systemd secrets, or environment variable?

5. **Dev container workflow impact** - Universal enforcement (Phase 1.3) will catch VS Code dev containers. What's the user migration story? Do they need to use project-launch instead, or enhance wrapper to handle devcontainer.json specifications?

### Validation Checkpoints

These should be validated during implementation:

**Before Milestone 1 starts:**
- [ ] Verify `nvidia-ctk --version` >= 1.17.8 (CVE-2025-23266 patched)
- [ ] Confirm .planning directory not gitignored (commit_docs: true in config)
- [ ] Identify 2-3 canary users for gradual rollout testing

**After Phase 1.2 (Awareness):**
- [ ] Verify unmanaged containers appear in state files within 60s of creation
- [ ] Test host process detection with bare-metal Python CUDA script
- [ ] Confirm false positive rate < 10% (review detection logs for infrastructure processes)

**After Phase 1.3 (Enforcement):**
- [ ] Attempt --cgroup-parent override, verify wrapper rejects
- [ ] Test cross-user container operations, verify authorization blocks
- [ ] Validate existing containers (pre-enforcement) continue working

**After Phase 2.2 (Historical Analytics):**
- [ ] Query GPU usage for last 30 days, verify data exists
- [ ] Test Grafana dashboard loads < 2s with 1 year of data
- [ ] Validate VictoriaMetrics compression ratio (expect 10:1 vs Prometheus)

## Sources

Research synthesised findings from 4 parallel research agents. Source quality is high - official documentation, kernel sources, CVE bulletins, production deployment guides.

### Primary Sources (HIGH confidence)

**Official Documentation:**
- [systemd.resource-control(5)](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html) - Authoritative systemd cgroup directives
- [Docker events API](https://docs.docker.com/reference/cli/docker/system/events/) - Official Docker events reference
- [NVIDIA Security Bulletin - CVE-2025-23266](https://nvidia.custhelp.com/app/answers/detail/a_id/5659) - Critical vulnerability
- [Linux cgroups v2 documentation](https://www.kernel.org/doc/html/latest/admin-guide/cgroup-v2.html) - Kernel documentation

**Production Guides:**
- [Red Hat: Setting Resource Limits with Control Groups](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/8/html/managing_monitoring_and_updating_the_kernel/setting-limits-for-applications_managing-monitoring-and-updating-the-kernel)
- [Prometheus Alertmanager Configuration](https://prometheus.io/docs/alerting/latest/alertmanager/)
- [VictoriaMetrics Documentation](https://docs.victoriametrics.com/)

### Secondary Sources (MEDIUM confidence)

**Community Best Practices:**
- [Thanos vs VictoriaMetrics Comparison](https://last9.io/blog/thanos-vs-victoriametrics/) - Production benchmarks
- [Prometheus Exporters Best Practices](https://www.sysdig.com/blog/prometheus-exporters-best-practices)
- [Docker Container Lifecycle Management](https://daily.dev/blog/docker-container-lifecycle-management-best-practices)

**Academic/Research:**
- [NVIDIA GPU Monitoring Tools Comparison](https://lambda.ai/blog/keeping-an-eye-on-your-gpus-2)
- [Green Algorithms for Carbon Footprint](https://www.advancedsciencenews.com/measuring-computers-carbon-footprint-with-green-algorithms/)

### Vulnerability Sources (CRITICAL)

- [NVIDIAScape - CVE-2025-23266 Analysis](https://www.wiz.io/blog/nvidia-ai-vulnerability-cve-2025-23266-nvidiascape) - Detailed exploit analysis
- [Docker cgroup-parent bypass issue](https://github.com/moby/moby/issues/23262) - GitHub issue tracking
- [OPA Docker Authorization fail-open behaviour](https://www.openpolicyagent.org/docs/docker-authorization) - Official OPA docs

### Domain Knowledge Sources

**GPU Cluster Management:**
- Run:ai, Rafay, Anyscale, Kubernetes GPU Operator - Feature comparison for table stakes identification
- SLURM GPU scheduling (GRES) - Batch integration patterns
- NVIDIA Base Command Manager - Enterprise GPU management reference architecture

**University GPU Clusters:**
- University of Edinburgh, Harvard FASRC - Real-world deployment patterns
- Multi-tenant isolation approaches - Academic security models

---

**Research completed:** 2026-01-30
**Ready for roadmap:** Yes

**Next steps:**
1. Check nvidia-ctk version immediately (CVE-2025-23266)
2. Orchestrator proceeds to requirements definition
3. Roadmapper will use this summary to structure detailed phase plans
