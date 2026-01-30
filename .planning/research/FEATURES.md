# Feature Research: GPU Cluster Management Platform

**Domain:** Multi-user GPU container management and HPC resource management
**Researched:** 2026-01-30
**Confidence:** MEDIUM

---

## Feature Landscape

### Table Stakes (Users Expect These)

Features users assume exist in a production GPU cluster management system. Missing these makes the system feel incomplete or unreliable.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| **Hierarchical resource quotas** | Standard in all modern GPU platforms (Anyscale, Rafay, Run:ai). Users/projects/orgs need allocation guarantees | MEDIUM | Already exists via YAML config; needs enhancement for dynamic borrowing |
| **GPU allocation and enforcement** | Core value proposition. Users expect GPUs to be actually reserved and limits enforced | HIGH | Exists but has bypass paths (dev containers, raw docker, host processes) |
| **Container lifecycle automation** | Idle timeout, max runtime, cleanup are HPC standards. Users expect runaway jobs to be stopped | MEDIUM | Exists but has escape bugs; containers not being caught by cleanup |
| **Basic monitoring dashboards** | Users expect real-time visibility into GPU/CPU/memory usage (Grafana standard) | LOW | Prometheus/Grafana deployed but needs stabilisation (DCGM crashes) |
| **User attribution** | Every GPU process must be traceable to a user. Foundation for multi-tenancy | MEDIUM | Exists for DS01-managed containers; missing for unmanaged workloads |
| **Resource isolation (cgroups)** | Linux standard for preventing resource exhaustion and interference | MEDIUM | Exists (systemd cgroups, ds01.slice); needs verification for GPU isolation |
| **Audit trail / event logging** | Users and admins expect history of container starts/stops/failures | LOW | Event log currently empty (0 lines) - broken |
| **User self-service** | Users expect to launch/stop/monitor own containers without admin | LOW | Exists via L2-L4 commands; needs quota visibility dashboard |
| **Multi-tenancy isolation** | Users cannot see/affect each other's containers. Table stakes for shared infrastructure | HIGH | Partial (cgroups). OPA failed. Needs comprehensive solution |
| **Notification system** | Users expect alerts when containers stop, approach limits, or fail | MEDIUM | Missing; standard in Run:ai, GKE, modern platforms |

### Differentiators (Competitive Advantage)

Features that set this platform apart from commercial or other university GPU clusters. Not required, but valuable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| **Full workload visibility** | DS01 sees EVERYTHING on GPUs - managed containers, unmanaged containers, dev containers, host processes. Zero blind spots | HIGH | Unique selling point. Most systems only track what they create. Requires detection layer |
| **Universal enforcement** | Docker wrapper intercepts ALL container creation, even dev containers and raw docker. No bypasses | HIGH | Partially exists. Needs expansion to catch VS Code, docker-compose, etc. |
| **Beginner-to-expert UX** | L4 wizards for beginners, L2 atomic commands for experts, dev container support for VS Code users | MEDIUM | Exists and working well. Differentiates from SLURM-only systems |
| **Container type intelligence** | System understands dev containers vs batch jobs vs interactive sessions; applies different lifecycle rules | MEDIUM | Detection exists; lifecycle differentiation needed |
| **Historical usage analytics** | Users see their GPU-hours over 1 week/month/year to understand impact and value | MEDIUM | Missing; valuable for justifying continued funding and compute requests |
| **Green computing metrics** | Carbon/energy tracking integrated into dashboards. Aligns with university sustainability goals | LOW | Trendy differentiator. Eco2AI, ZEUS libraries available. Low complexity with existing Prometheus |
| **Dynamic quota borrowing** | Users can temporarily borrow unused quota from other projects. Maximises utilisation | HIGH | Modern feature (Kueue, Exostellar). Complex to implement fairly |
| **Intelligent cleanup** | ML-aware idle detection (understands dataset loading vs actual idleness). Self-cleaning with user-tunable thresholds | MEDIUM | NVIDIA's GPU monitoring blog describes this pattern. Better than dumb CPU threshold |
| **Comprehensive cgroup enforcement** | GPU, CPU, memory, I/O, disk - all enforced via cgroups with user-specific overrides | HIGH | Linux standard but GPU cgroup support is emerging. Requires kernel 5.15+ |
| **One-line SLURM integration** | Users submit batch jobs via familiar SLURM commands; DS01 acts as execution backend | HIGH | Requires SLURM alongside DS01; clear interactive/batch separation |

### Anti-Features (Commonly Requested, Often Problematic)

Features that seem good but create problems for this specific context (university-scale, single-admin).

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| **Per-user custom images** | Users want total control over environment | 30-200 users × N images each = storage explosion. Version sprawl nightmare | Project-based images with shared base layers. User-specific conda/pip overlays |
| **Kubernetes migration** | "Industry standard", supposed scalability | Massive complexity for single server. Overkill for current scale. Learning curve | Design for K8s compatibility but stay on Docker until multi-node needed |
| **Real-time everything** | WebSocket dashboards, sub-second metrics | Complexity without value. Polling every 10s is sufficient for this workload | Standard Prometheus scrape intervals (10-30s). Grafana dashboards with 5s refresh |
| **Unlimited resource borrowing** | "Maximise utilisation" by allowing unlimited overflow | Users build workflows assuming borrowed resources; system becomes unreliable when quotas enforced | Cap borrowing at 2x quota or time-limited (4h bursts) |
| **Fine-grained RBAC** | Complex permission matrix for every resource | Single admin can't maintain. Complexity → bugs → security gaps | Two-tier: regular users vs admin. Group-based resource quotas handle most needs |
| **Container registry** | "Best practice" to run own registry | Adds maintenance burden, storage, backup complexity | Use Docker Hub for public images, bind mount for local dev images |
| **Gamification** | Leaderboards, badges for "greenest user" | Encourages gaming the metrics, creates perverse incentives | Simple historical analytics and quota visibility. Let users self-regulate |
| **VPN/network isolation per user** | Security theatre for on-prem lab | Complex networking, breaks legitimate use cases (distributed training, Jupyter access) | Trust university network boundary. Use cgroups + container isolation |
| **Auto-scaling to cloud** | "Elastic capacity" for peak demand | Cost explosion risk, complex hybrid orchestration, no budget allocated | Manual cloud bursting only when explicitly requested and budgeted |
| **Automatic dependency updates** | Keep base images current | Breaking changes disrupt active research. Users need stability | Scheduled update windows (semester breaks). Pin versions. User opt-in to new bases |

---

## Feature Dependencies

```
Resource Enforcement Foundation:
    [Unmanaged workload detection] ──requires──> [User attribution]
                                               └──enables──> [Comprehensive quota enforcement]
                                               └──enables──> [Multi-tenancy isolation]

Lifecycle Management:
    [Lifecycle bug fixes] ──requires──> [Comprehensive detection]
                        └──enables──> [Reliable cleanup automation]
                        └──enables──> [Container retirement enforcement]

Observability Stack:
    [Monitoring stability] ──requires──> [DCGM exporter fixes]
                         └──enables──> [Operational dashboards]
                         └──enables──> [Historical analytics]
                         └──enables──> [Green computing metrics]

Self-Service Layer:
    [User dashboards] ──requires──> [Monitoring stability]
                    └──requires──> [Historical analytics]
                    └──enables──> [Usage visibility]
                    └──enables──> [Quota transparency]

Alert System:
    [Notifications] ──requires──> [Monitoring stability]
                  └──requires──> [Event logging]
                  └──enables──> [User warnings]
                  └──enables──> [Admin alerts]

Hygiene & Operations:
    [Disk space management] ──requires──> [Container lifecycle fixes]
    [Departed user cleanup] ──requires──> [Comprehensive detection]
    [Backup/DR] ──requires──> [Stable state tracking]

Advanced Features:
    [SLURM integration] ──requires──> [Comprehensive resource enforcement]
                      └──requires──> [Multi-tenancy isolation]
    [MLflow integration] ──requires──> [Monitoring stability]
    [JupyterHub] ──requires──> [Multi-tenancy isolation]
    [Dynamic quota borrowing] ──requires──> [Comprehensive enforcement]
```

### Dependency Notes

- **Unmanaged workload detection → User attribution:** Can't attribute host GPU processes or raw docker containers without detection layer
- **Lifecycle bug fixes → Reliable cleanup:** Containers escaping cleanup undermine all lifecycle automation
- **Monitoring stability → Everything observability:** DCGM exporter crashing blocks dashboards, analytics, alerts
- **Comprehensive enforcement → SLURM:** SLURM assumes resources are actually enforced; bypass paths break this
- **Multi-tenancy isolation → Advanced features:** JupyterHub and SLURM require strong isolation guarantees

---

## MVP Definition

### Launch With (Milestone 1: Full Visibility & Control)

Minimum viable for "production-ready" system where core value (full control) is delivered.

- [x] GPU allocation with MIG — Exists
- [x] Resource limits via YAML — Exists
- [x] Universal Docker wrapper — Exists
- [x] Basic monitoring deployed — Exists (needs stabilisation)
- [ ] **Unmanaged container detection** — Critical gap; system can be bypassed
- [ ] **Host GPU process detection** — Critical gap; allocation model breaks without this
- [ ] **Lifecycle bug fixes** — Critical gap; containers escaping cleanup
- [ ] **Comprehensive cgroup enforcement** — Critical gap; limits aren't comprehensive
- [ ] **Multi-tenancy isolation** — Critical gap; users can interfere with each other
- [ ] **Event logging functional** — Currently broken (0 lines logged)
- [ ] **User notifications** — Table stakes missing; users don't know when containers stop

**Why this is MVP:** These features deliver the core value proposition (full control over GPU resources). Everything else is enhancement or operational improvement.

### Add After Validation (Milestone 2: Observability & Analytics)

Features to add once core enforcement is working and stable.

- [ ] **Monitoring stack stabilisation** — Fix DCGM crashes, improve uptime
- [ ] **Operational dashboards** — Lab manager real-time visibility
- [ ] **Historical usage analytics** — 1 week, 1 month, 1 year, all-time views
- [ ] **Green computing metrics** — Carbon/energy tracking
- [ ] **GPU hardware health** — ECC errors, thermal monitoring
- [ ] **Alert system** — Email/Teams for problems
- [ ] **User self-service dashboards** — Users see own GPU-hours, quota usage

**Trigger for adding:** Milestone 1 complete and running without major issues for 2-4 weeks.

### Add After Operations Mature (Milestone 3: Server Hygiene)

Features to improve operational maturity and reduce admin burden.

- [ ] **Departed user cleanup automation** — Semester transitions
- [ ] **Disk space optimisation** — Image/cache cleanup
- [ ] **Backup & disaster recovery** — Automated backups
- [ ] **Better use of systemd** — Replace custom daemons
- [ ] **Container image management** — Base updates, registry
- [ ] **CI/CD expansion** — More than current 149 tests

**Trigger for adding:** Milestone 2 stable, admin wants to reduce operational burden.

### Future Consideration (v2+)

Features to defer until demand or scale requires them.

- [ ] **SLURM integration** — Wait for actual batch job demand
- [ ] **Dynamic quota borrowing** — Complex; wait until utilisation consistently high
- [ ] **JupyterHub native interface** — Wait for user demand
- [ ] **MLflow integration** — Wait for researcher demand
- [ ] **Cloud bursting** — Wait for budget and queue pressure
- [ ] **Multi-node support** — Wait for second server
- [ ] **Web UI for lab manager** — Nice-to-have; SSH + Grafana sufficient for now
- [ ] **Security hardening** — Container scanning, secrets mgmt - defer until threat model requires

**Trigger for adding:** Explicit demand signals (user requests, queue congestion, funding availability).

---

## Feature Prioritisation Matrix

| Feature | User Value | Implementation Cost | Priority | Phase |
|---------|------------|---------------------|----------|-------|
| Unmanaged container detection | HIGH | HIGH | P1 | M1 |
| Host GPU process detection | HIGH | MEDIUM | P1 | M1 |
| Lifecycle bug fixes | HIGH | MEDIUM | P1 | M1 |
| Multi-tenancy isolation | HIGH | HIGH | P1 | M1 |
| Comprehensive cgroup enforcement | HIGH | HIGH | P1 | M1 |
| Event logging fix | MEDIUM | LOW | P1 | M1 |
| User notifications | MEDIUM | MEDIUM | P1 | M1 |
| Monitoring stability | HIGH | MEDIUM | P2 | M2 |
| Operational dashboards | HIGH | LOW | P2 | M2 |
| Historical analytics | MEDIUM | MEDIUM | P2 | M2 |
| Green computing metrics | LOW | LOW | P2 | M2 |
| User self-service dashboards | MEDIUM | MEDIUM | P2 | M2 |
| Alert system (email/Teams) | MEDIUM | LOW | P2 | M2 |
| Disk space automation | MEDIUM | MEDIUM | P3 | M3 |
| Departed user cleanup | MEDIUM | MEDIUM | P3 | M3 |
| Backup/DR | HIGH | HIGH | P3 | M3 |
| Dynamic quota borrowing | LOW | HIGH | P3 | Future |
| SLURM integration | MEDIUM | HIGH | P3 | M4 |
| JupyterHub integration | MEDIUM | HIGH | P3 | Future |
| MLflow integration | LOW | MEDIUM | P3 | Future |
| Cloud bursting | LOW | HIGH | P3 | M5 |

**Priority key:**
- P1: Must have for reliable production (Milestone 1)
- P2: Should have for operational visibility (Milestone 2)
- P3: Nice to have, add when demand signals emerge (M3+)

---

## Competitor Feature Analysis

| Feature | SLURM | Kubernetes + GPU Operator | Run:ai | DS01 (Current) | DS01 (Target) |
|---------|-------|--------------------------|--------|----------------|---------------|
| **GPU scheduling** | ✓ (GRES) | ✓ (k8s scheduler) | ✓ (advanced) | ✓ (MIG allocation) | ✓ |
| **Resource quotas** | ✓ (accounts) | ✓ (namespaces) | ✓ (hierarchical) | ✓ (YAML groups) | ✓ Enhanced |
| **Batch jobs** | ✓ (core feature) | ✓ (Jobs API) | ✓ | ✗ | ✓ (M4: SLURM) |
| **Interactive containers** | ✗ (poor UX) | ✓ | ✓ | ✓ (strong UX) | ✓ |
| **Dev container support** | ✗ | ✓ (via tooling) | ✗ | ✓ (via wrapper) | ✓ Enhanced |
| **Unmanaged workload detection** | ✗ | ✗ | ✗ | Partial | ✓ (M1) |
| **Lifecycle automation** | ✓ | ✓ (pod lifecycle) | ✓ | Buggy | ✓ (M1) |
| **Multi-tenancy** | ✓ (accounts) | ✓ (namespaces) | ✓ (projects) | Partial | ✓ (M1) |
| **Monitoring** | Basic | ✓ (Prometheus) | ✓ (built-in) | ✓ (unstable) | ✓ (M2) |
| **Historical analytics** | Basic | External tools | ✓ | ✗ | ✓ (M2) |
| **User self-service dashboards** | ✗ | External tools | ✓ | ✗ | ✓ (M2) |
| **Alerting** | Basic | ✓ (Alertmanager) | ✓ | ✗ | ✓ (M2) |
| **Green computing** | ✗ | ✗ | ✗ | ✗ | ✓ (M2) |
| **Beginner-friendly UX** | ✗ | ✗ | ~ | ✓ (L4 wizards) | ✓ |
| **Cloud bursting** | Plugins | ✓ | ✓ | ✗ | ✓ (M5) |
| **Dynamic quota borrowing** | ✗ | External (Kueue) | ✓ | ✗ | ✓ (Future) |

**Our approach:** Hybrid model combining Docker's simplicity with SLURM's batch capabilities, differentiated by full workload visibility and beginner-to-expert UX.

---

## Sources

### Resource Enforcement & Quota Management
- [Rafay: Configure and Manage GPU Resource Quotas in Multi-Tenant Clouds](https://rafay.co/ai-and-cloud-native-blog/configure-and-manage-gpu-resource-quotas-in-multi-tenant-clouds/)
- [Anyscale: Resource Quotas Documentation](https://docs.anyscale.com/administration/resource-management/resource-quotas)
- [Exostellar Multi-Cluster Operator for AI](https://www.exostellar.ai/post/intel-and-exostellar-multi-cluster-operator-ai-acceleration-without-the-bottleneck)
- [Red Hat: Improve GPU utilization with Kueue in OpenShift AI](https://developers.redhat.com/articles/2025/05/22/improve-gpu-utilization-kueue-openshift-ai)

### Multi-Tenancy & User Isolation
- [ScienceDirect: Efficient network isolation and load balancing in multi-tenant HPC clusters](https://www.sciencedirect.com/science/article/abs/pii/S0167739X16300735)
- [Microsoft: Architectural Approaches for Compute in Multitenant Solutions](https://learn.microsoft.com/en-us/azure/architecture/guide/multitenant/approaches/compute)
- [Loft Labs: Best Practices for Achieving Isolation in Kubernetes Multi-Tenant Environments](https://www.vcluster.com/blog/best-practices-for-achieving-isolation-in-kubernetes-multi-tenant-environments)
- [Medium: Multi-Tenant Kubernetes Resource Management Guide](https://medium.com/@theshawnshop/multi-tenant-kubernetes-part-1-a-practical-guide-to-isolation-and-resource-management-308ea814f4ff)

### GPU Monitoring & Observability
- [GitHub: NVIDIA DCGM Exporter](https://github.com/NVIDIA/dcgm-exporter)
- [OpenObserve: NVIDIA GPU Monitoring with DCGM Exporter](https://openobserve.ai/blog/how-to-monitor-nvidia-gpu/)
- [Google Cloud: Collect and view DCGM metrics](https://docs.cloud.google.com/kubernetes-engine/docs/how-to/dcgm-metrics)
- [NVIDIA Technical Blog: Monitoring GPUs in Kubernetes with DCGM](https://developer.nvidia.com/blog/monitoring-gpus-in-kubernetes-with-dcgm/)
- [Medium: Tracking GPU Usage in K8s with Prometheus and DCGM](https://medium.com/@penkow/tracking-gpu-usage-in-k8s-with-prometheus-and-dcgm-a-complete-guide-7c8590809d7c)

### University GPU Clusters & Self-Service
- [NVIDIA Base Command Manager](https://www.nvidia.com/en-us/data-center/base-command-manager/)
- [University of Edinburgh: GPU and cluster computing](https://computing.help.inf.ed.ac.uk/cluster-computing)
- [Harvard FASRC: GPU Computing on the cluster](https://docs.rc.fas.harvard.edu/kb/gpgpu-computing-on-the-cluster/)
- [Together AI: Instant GPU Clusters](https://www.together.ai/instant-gpu-clusters)

### SLURM & Batch Scheduling
- [SLURM Workload Manager: Generic Resource (GRES) Scheduling](https://slurm.schedmd.com/gres.html)
- [NVIDIA Mission Control: Slurm Workload Management](https://docs.nvidia.com/mission-control/docs/systems-administration-guide/2.0.0/slurm-workload-management.html)
- [University of Edinburgh: The Slurm job scheduler](https://computing.help.inf.ed.ac.uk/slurm)

### Container Lifecycle & Cleanup
- [CleanStart: What is Container Lifecycle](https://www.cleanstart.com/guide/container-lifecycle)
- [CrowdStrike: Container Lifecycle Management](https://www.crowdstrike.com/en-us/cybersecurity-101/cloud-security/container-lifecycle-management/)
- [Daily.dev: Docker Container Lifecycle Management Best Practices](https://daily.dev/blog/docker-container-lifecycle-management-best-practices)
- [Last9: Docker Container Lifecycle: Key States and Best Practices](https://last9.io/blog/docker-container-lifecycle/)

### Container Security & Escape Prevention
- [SentinelOne: 10 Container Security Best Practices in 2026](https://www.sentinelone.com/cybersecurity-101/cloud-security/container-security-best-practices/)
- [Wiz: What is Container Escape: Detection & Prevention](https://www.wiz.io/academy/container-security/container-escape)
- [AccuKnox: Container Security in 2026](https://accuknox.com/blog/container-security)

### Green Computing & Energy Tracking
- [NVIDIA: Solutions for Sustainable Computing](https://www.nvidia.com/en-us/data-center/sustainable-computing/)
- [NVIDIA Blog: AI's Key Role in Energy Efficiency](https://blogs.nvidia.com/blog/ai-energy-innovation-climate-research/)
- [Carbon Credits: NVIDIA's Accelerated Analytics Can Cut Cost and CO2](https://carboncredits.com/nvidias-accelerated-analytics-can-cut-computing-cost-and-co2-footprint-by-80/)
- [University of Michigan: Green Research Computing Guide](https://guides.lib.umich.edu/c.php?g=1459709&p=11107909)

### Alerting & Notifications
- [Grafana: Configure Slack for Alerting](https://grafana.com/docs/grafana/latest/alerting/configure-notifications/manage-contact-points/integrations/configure-slack/)
- [NVIDIA Run:ai: Notifications Documentation](https://run-ai-docs.nvidia.com/saas/settings/user-settings/notifications)
- [Google Cloud: Configure cluster notifications for third-party services](https://cloud.google.com/kubernetes-engine/docs/tutorials/cluster-notifications-slack)

### Workload Detection & Rogue Container Tracking
- [NVIDIA Technical Blog: Making GPU Clusters More Efficient](https://developer.nvidia.com/blog/making-gpu-clusters-more-efficient-with-nvidia-data-center-monitoring)
- [Security Boulevard: Anomaly Detection for Non-Human Identities](https://securityboulevard.com/2026/01/anomaly-detection-for-non-human-identities-catching-rogue-workloads-and-ai-agents/)
- [SentinelOne: Container and Cloud-Native Workload Protection](https://www.sentinelone.com/press/sentinelone-releases-revolutionary-container-and-cloud-native-workload-protection/)

### Cgroups & Resource Enforcement
- [LWN: cgroup support for GPU devices](https://lwn.net/Articles/844199/)
- [Linux Manual: cgroups(7)](https://man7.org/linux/man-pages/man7/cgroups.7.html)
- [Red Hat: Setting system resource limits with control groups](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/8/html/managing_monitoring_and_updating_the_kernel/setting-limits-for-applications_managing-monitoring-and-updating-the-kernel)
- [iximiuz Labs: Controlling Process Resources with Linux Control Groups](https://labs.iximiuz.com/tutorials/controlling-process-resources-with-cgroups)

### User Dashboards & Quota Visibility
- [Google Cloud: View and manage quotas](https://docs.cloud.google.com/docs/quotas/view-manage)
- [Qrvey: 2026 Self-Service Dashboards: Benefits & Implementation](https://qrvey.com/blog/self-service-dashboard/)
- [AWS: Visualizing service quotas and setting alarms](https://docs.aws.amazon.com/AmazonCloudWatch/latest/monitoring/CloudWatch-Quotas-Visualize-Alarms.html)

### MLflow & Experiment Tracking
- [MLflow: System Metrics Documentation](https://mlflow.org/docs/latest/ml/tracking/system-metrics/)
- [GitHub: mlflow-sysmetrics plugin](https://github.com/hugodscarvalho/mlflow-sysmetrics)
- [Restack: MLflow GPU Integration Guide](https://www.restack.io/docs/mlflow-knowledge-mlflow-gpu-usage-guide)

### JupyterHub & Custom Spawners
- [JupyterHub: Spawners Documentation](https://jupyterhub.readthedocs.io/en/stable/reference/spawners.html)
- [Zero to JupyterHub: Customizing User Resources](https://z2jh.jupyter.org/en/latest/jupyterhub/customizing/user-resources.html)
- [GitHub: FAU GPU-Jupyterhub](https://github.com/FAU-DLM/GPU-Jupyterhub)
- [Jupyter Community Forum: Distribute GPU with jupyterhub](https://discourse.jupyter.org/t/distribute-gpu-with-jupyterhub/2181)

### Historical Analytics & Time Series
- [Kinetica: The Real-Time Database](https://www.kinetica.com/)
- [Datadog: Real-Time NVIDIA GPU Monitoring](https://www.datadoghq.com/monitoring/nvidia-gpu-monitoring/)
- [ClickHouse: What is observability in 2026?](https://clickhouse.com/resources/engineering/what-is-observability)

---

*Feature research for: DS01 Multi-user GPU Container Management Platform*
*Researched: 2026-01-30*
*Confidence: MEDIUM (WebSearch findings cross-referenced across multiple sources; some details need verification with official documentation)*
