# Technology Stack Research

**Project:** DS01 Infrastructure Milestone Enhancements
**Domain:** GPU Container Management Platform Enhancement
**Researched:** 2026-01-30
**Overall Confidence:** HIGH

## Executive Summary

This stack research focuses on technologies needed to add comprehensive resource enforcement, unmanaged process detection, user isolation, historical analytics, green computing metrics, and server hygiene automation to the existing DS01 GPU container management system.

The research emphasises Linux-native solutions that integrate with the existing Docker + systemd + Prometheus stack, avoiding heavy new infrastructure dependencies. All recommendations prioritise stability, backward compatibility, and ease of administration for a single-admin environment.

---

## Core Resource Enforcement

### cgroups v2

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Linux cgroups v2 | Kernel 4.5+ (unified hierarchy) | Comprehensive CPU, memory, IO, and disk enforcement | Unified hierarchy provides consistent resource control; superior to v1's fragmented controllers; already partially used via systemd slices |
| systemd resource-control | systemd 219+ | Declarative cgroup configuration via unit files | Native integration with systemd; configuration persists across reboots; more maintainable than manual cgroup manipulation |

**Rationale:** DS01 already uses systemd cgroups (`ds01.slice` hierarchy). Extending this with comprehensive resource limits requires:
- `CPUAccounting=true`, `CPUQuota=`, `CPUWeight=` for CPU enforcement
- `MemoryAccounting=true`, `MemoryMax=`, `MemoryHigh=` for memory limits with throttling
- `IOAccounting=true`, `IODeviceWeight=`, `IOReadBandwidthMax=`, `IOWriteBandwidthMax=` for IO control
- Configured via `/etc/systemd/system/user-{uid}.slice.d/*.conf` drop-in files

**Confidence:** HIGH - Official kernel feature, well-documented, production-proven.

**Sources:**
- [Linux cgroups v2 for Resource Isolation (Medium)](https://medium.com/@springmusk/cgroups-v2-for-resource-isolation-in-linux-c413d11cd36f)
- [systemd.resource-control(5)](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html)
- [Red Hat: Setting Resource Limits with Control Groups](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/8/html/managing_monitoring_and_updating_the_kernel/setting-limits-for-applications_managing-monitoring-and-updating-the-kernel)

### Disk Quota Enforcement

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| XFS project quotas | xfs_quota (xfsprogs) | Per-user disk space limits on `/home`, `/var/lib/docker` | Native filesystem support; quota accounting via mount option; no separate quota files to corrupt |
| ext4 quotas | quota-tools 4.x | Fallback for ext4 filesystems | Well-established if not on XFS |

**Rationale:** Docker doesn't natively enforce per-user disk quotas. Linux filesystem quotas provide:
- User quotas (`uquota`) for `/home/{user}` directories
- Project quotas (`pquota`) for `/var/lib/docker/volumes/{user}` namespaces
- Group quotas (`gquota`) for shared project directories

**XFS advantages:** Quota accounting built into journaling; no `quotacheck` needed; can enable/disable enforcement without remount.

**Confidence:** HIGH - Standard Linux capability, kernel-enforced.

**Sources:**
- [How to Enable Disk Quota on XFS or Ext4](https://computingforgeeks.com/how-to-enable-disk-quota-on-xfs-or-ext4-linux-system/)
- [Red Hat: Limiting storage space usage on XFS with quotas](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/8/html/managing_file_systems/assembly_limiting-storage-space-usage-on-xfs-with-quotas_managing-file-systems)

---

## Unmanaged Process Detection

### GPU Process Monitoring

| Tool | Version | Purpose | Why Recommended |
|------|---------|---------|-----------------|
| nvidia-smi | Bundled with NVIDIA drivers | Query GPU processes with PID, user, memory | Already available; provides authoritative GPU utilisation data |
| nvitop | 1.x (PyPI) | Interactive GPU process monitoring with user attribution | Python library; htop-like interface; works on Linux and Windows; integrates with psutil for host process info |
| nvtop | Latest stable | Alternative ncurses GPU monitor supporting NVIDIA, AMD, Intel | Multi-vendor support; interactive process killing; builtin configuration |

**Detection Strategy:**
1. Poll `nvidia-smi --query-compute-apps=pid,process_name,used_memory --format=csv` every 30-60s
2. Cross-reference PIDs with Docker container PIDs via `docker inspect` and cgroup membership
3. Detect unmanaged processes: GPU PIDs not in any DS01-tracked container
4. Attribute to user via `/proc/{pid}/status` → `Uid` field → `getpwuid()`

**Confidence:** HIGH - nvidia-smi is authoritative; nvitop actively maintained.

**Sources:**
- [Useful nvidia-smi Queries (NVIDIA)](https://nvidia.custhelp.com/app/answers/detail/a_id/3751/~/useful-nvidia-smi-queries)
- [nvitop on PyPI](https://pypi.org/project/nvitop/)
- [nvtop on GitHub](https://github.com/Syllo/nvtop)
- [GPU Monitoring Tools Comparison (Lambda Labs)](https://lambda.ai/blog/keeping-an-eye-on-your-gpus-2)

### Container Detection

| Tool | Version | Purpose | Why Recommended |
|------|---------|---------|-----------------|
| Docker API | Docker Engine API v1.43+ | Detect all containers regardless of how they were created | Already available; `docker ps -a` shows containers from all sources (docker run, docker-compose, dev containers) |
| Docker labels | OCI standard | Identify DS01-managed vs unmanaged containers | Containers created via DS01 have `ds01.*` labels; absence indicates unmanaged |

**Detection Strategy:**
1. List all containers: `docker ps -a --format '{{.ID}}\t{{.Labels}}'`
2. Check for `ds01.managed=true` label (or any `ds01.*` namespace label)
3. Containers without DS01 labels = unmanaged
4. Cross-reference with GPU process detection to attribute GPU usage

**Label Standardisation:** Use reverse-DNS OCI standard: `ds01.user`, `ds01.managed`, `ds01.type`, etc.

**Confidence:** HIGH - Docker API is stable and authoritative.

**Sources:**
- [Docker Labels Best Practices](https://www.docker.com/blog/docker-best-practices-using-tags-and-labels-to-manage-docker-image-sprawl/)
- [OCI Container Annotations](https://snyk.io/blog/how-and-when-to-use-docker-labels-oci-container-annotations/)

---

## User Isolation & Security

### Docker User Namespaces

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| Docker userns-remap | Docker Engine 1.10+ | Map container root to unprivileged host user | Mitigates container escape attacks; container root = host UID 100000+; no host privileges |
| Enhanced Container Isolation (ECI) | Docker Desktop (optional) | Automatic user namespace isolation | Recommended for future Docker Desktop deployments; automatic 64K UID range mapping |

**Implementation:**
- Configure `/etc/docker/daemon.json`: `{"userns-remap": "default"}`
- Container UIDs 0-65535 map to host UIDs 100000-165535
- Per-user mapping: `{"userns-remap": "{username}"}` for finer control

**Caveat:** Requires Docker volume ownership remapping; test thoroughly with existing containers.

**Confidence:** MEDIUM - Feature is stable but requires careful migration planning.

**Sources:**
- [Docker User Namespace Isolation](https://docs.docker.com/engine/security/userns-remap/)
- [Enhanced Container Isolation (Docker)](https://docs.docker.com/enterprise/security/hardened-desktop/enhanced-container-isolation/)
- [Container Security Fundamentals: User Namespaces (Datadog)](https://securitylabs.datadoghq.com/articles/container-security-fundamentals-part-2/)
- [Kubernetes User Namespace Isolation (CNCF)](https://www.cncf.io/blog/2025/07/16/securing-kubernetes-1-33-pods-the-impact-of-user-namespace-isolation/)

### AppArmor (Ubuntu Default)

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| AppArmor | Kernel module (Ubuntu default) | Mandatory Access Control for container workloads | Standard on Ubuntu; easier than SELinux for single-admin environment; path-based controls |

**Implementation:**
- Docker loads default AppArmor profile: `docker-default`
- Custom profiles: `/etc/apparmor.d/docker-ds01-*` for stricter isolation
- Assign profile to containers: `docker run --security-opt apparmor=docker-ds01-restricted`

**Alternative: SELinux** (if on RHEL/CentOS) - More complex but stronger Multi-Category Security (MCS).

**Confidence:** MEDIUM - AppArmor is standard on Ubuntu; custom profiles require learning curve.

**Sources:**
- [AppArmor vs SELinux for Container Isolation (Red Hat)](https://www.redhat.com/en/blog/apparmor-selinux-isolation)
- [Container Security: AppArmor and SELinux (Datadog)](https://securitylabs.datadoghq.com/articles/container-security-fundamentals-part-5/)

---

## Historical Analytics & Long-Term Storage

### VictoriaMetrics

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| VictoriaMetrics | v1.134.0 (latest: Jan 2026) | Long-term Prometheus storage with high compression | 10x better compression than Prometheus; simpler than Thanos; low resource usage; single binary |

**Architecture:**
- VictoriaMetrics as Prometheus remote write target
- Prometheus keeps 15-day local storage for fast queries
- VictoriaMetrics stores 1+ year history for analytics

**Why VictoriaMetrics over Thanos:**
- Simpler deployment (single binary vs multi-component)
- Lower resource usage (80-90% less RAM)
- Faster queries on historical data
- No object storage dependency (uses local/network disk)

**Confidence:** HIGH - Production-proven, actively maintained, excellent performance benchmarks.

**Sources:**
- [Thanos vs VictoriaMetrics Comparison (Last9)](https://last9.io/blog/thanos-vs-victoriametrics/)
- [VictoriaMetrics Changelog 2025](https://docs.victoriametrics.com/victoriametrics/changelog/changelog_2025/)
- [Prometheus Long-Term Storage Options (Greptime)](https://greptime.com/blogs/2024-08-16-prometheus-long-term-storage)

---

## Green Computing & Carbon Metrics

### Carbon Tracking

| Tool | Purpose | Why Recommended |
|------|---------|-----------------|
| pyNVML | Python binding for NVIDIA Management Library | Query GPU power consumption in real-time; required for carbon calculations |
| Green Algorithms methodology | CO2 estimation framework | Standard academic approach: runtime × hardware × grid carbon intensity |
| RAPL (Running Average Power Limit) | CPU/GPU/RAM power monitoring | Kernel interface for real-time power measurement on Intel/AMD systems |

**Implementation Strategy:**
1. **GPU Power:** `pyNVML` → `nvmlDeviceGetPowerUsage()` → Watts → kWh
2. **Carbon Intensity:** Hardcode grid carbon intensity (e.g., UK: ~200g CO₂/kWh) or use API (e.g., WattTime)
3. **Metrics:** Expose as Prometheus metrics via DS01 Exporter:
   - `ds01_gpu_energy_kwh_total{user, gpu}` (counter)
   - `ds01_carbon_grams_total{user}` (counter)
4. **Dashboard:** Grafana panel showing carbon footprint per user, per project

**Regulatory Context:** Germany's Energy Efficiency Act (2026) mandates PUE ≤ 1.2 for large data centres; carbon tracking becoming standard practice.

**Confidence:** MEDIUM - pyNVML is reliable; carbon intensity requires external data or hardcoded assumptions.

**Sources:**
- [Green Algorithms for Carbon Footprint (Advanced Science News)](https://www.advancedsciencenews.com/measuring-computers-carbon-footprint-with-green-algorithms/)
- [GPU Carbon Calculator Explained (Leafcloud)](https://leaf.cloud/blog/gpu-carbon-calculator-explained/)
- [NVIDIA Sustainable Computing](https://www.nvidia.com/en-us/data-center/sustainable-computing/)

---

## Monitoring Stack Stabilisation

### Prometheus Exporter Best Practices

| Practice | Why Important |
|----------|---------------|
| Resource requests in systemd unit | Prevent exporter OOM; use `MemoryMax=512M` in service file |
| Restart policy | `Restart=always` with `RestartSec=10s` for auto-recovery |
| Metrics optimisation | Drop unused metrics via `metric_relabel_configs` to reduce cardinality |
| Scrape interval tuning | 30-60s for most metrics; 5s only for critical fast-changing metrics |
| Health checks | Expose `/health` endpoint; monitor with Prometheus blackbox exporter |

**DCGM Exporter Stability:**
- Known issue: DCGM exporter crashes on stale GPU process queries
- Mitigation: Run in systemd with automatic restart; upgrade to latest version; reduce scrape frequency to 30s

**Confidence:** HIGH - Official Prometheus best practices.

**Sources:**
- [Prometheus Exporters Best Practices (Sysdig)](https://www.sysdig.com/blog/prometheus-exporters-best-practices)
- [Writing Exporters (Prometheus)](https://prometheus.io/docs/instrumenting/writing_exporters/)
- [Mastering Prometheus Exporters (Checkly)](https://www.checklyhq.com/blog/mastering-prometheus-exporters-game-changing-techniques/)

---

## Alerting

### Email and Microsoft Teams Integration

| Tool | Version | Purpose | Why Recommended |
|------|---------|---------|-----------------|
| Prometheus Alertmanager | v0.30.1 (latest: Jan 2026) | Central alert routing and deduplication | Already deployed; handles email, webhooks, grouping, silencing |
| prometheus-msteams | Latest stable | Bridge for MS Teams webhooks | Required due to Microsoft's deprecation of native webhooks (Oct 2025) |

**Email Configuration:**
```yaml
receivers:
  - name: 'email-admin'
    email_configs:
      - to: 'admin@university.edu'
        from: 'ds01-alerts@university.edu'
        smarthost: 'smtp.university.edu:587'
        auth_username: 'ds01-alerts'
        auth_password_file: '/etc/alertmanager/smtp_password'
        headers:
          Subject: '[DS01] {{ .GroupLabels.alertname }}'
```

**Microsoft Teams (2026):**
- **Critical:** Microsoft deprecated traditional incoming webhooks (August 2025)
- **Solution:** Use `prometheus-msteams` bridge or native Alertmanager webhook_configs with Adaptive Cards format
- **Alternative:** Power Automate Workflows (new Microsoft approach as of 2026)

**Confidence:** HIGH for email; MEDIUM for Teams due to recent Microsoft platform changes.

**Sources:**
- [Prometheus Alertmanager Releases](https://github.com/prometheus/alertmanager/releases)
- [Effective Alerting with Alertmanager (Better Stack)](https://betterstack.com/community/guides/monitoring/prometheus-alertmanager/)
- [prometheus-msteams Bridge](https://github.com/prometheus-msteams/prometheus-msteams)
- [Microsoft Teams Webhook Deprecation Issue](https://github.com/prometheus/alertmanager/issues/3920)

---

## Server Hygiene & Linux Best Practices

### systemd Timers (Replace Cron)

| Feature | Why Use systemd Timers |
|---------|------------------------|
| Persistent execution | `Persistent=true` runs missed jobs on boot; cron can't do this |
| Dependency management | Wait for network, Docker, etc. before running cleanup |
| Logging integration | Automatic journald logging; query with `journalctl -u cleanup.service` |
| Monitoring | Timer status visible in `systemctl list-timers`; failed runs tracked |

**Example: Idle Container Cleanup Timer**
```ini
# /etc/systemd/system/ds01-cleanup-idle.timer
[Unit]
Description=DS01 Idle Container Cleanup Timer

[Timer]
OnCalendar=daily
Persistent=true
RandomizedDelaySec=1h

[Install]
WantedBy=timers.target
```

**Migration Path:** Convert existing cron jobs in `/etc/cron.daily/` to systemd timers.

**Confidence:** HIGH - Standard Linux practice for 2026.

**Sources:**
- [Use systemd timers instead of cronjobs (Opensource.com)](https://opensource.com/article/20/7/systemd-timers)
- [systemd Advanced Guide for 2026 (Medium)](https://medium.com/@springmusk/systemd-advanced-guide-for-2026-b2fe79af3e78)
- [Systemd Timers (Arch Wiki)](https://wiki.archlinux.org/title/Systemd/Timers)

### logrotate with systemd

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| logrotate | 3.x | Automatic log rotation and compression | Industry standard; systemd integration via timer |
| systemd-journald | systemd built-in | Structured logging with metadata | Queryable logs; eliminates need for syslog |

**Configuration:**
- Default: `logrotate.timer` runs daily via systemd
- Custom: Override frequency in `/etc/systemd/system/logrotate.timer`
- DS01 logs: Add `/etc/logrotate.d/ds01` config for `/var/log/ds01/*.log`

**journald Best Practices:**
- Set `SystemMaxUse=2G` in `/etc/systemd/journald.conf` to cap disk usage
- Use `journalctl -u ds01-exporter --since "1 hour ago"` for structured queries
- Keep metadata: boot IDs, service identifiers, PIDs for root-cause analysis

**Confidence:** HIGH - Standard Linux tooling.

**Sources:**
- [logrotate with systemd timer (GitHub Gist)](https://gist.github.com/pancudaniel7/4ce4fb3ecebc70e97210cc36638ef8a9)
- [Managing Temporary Files with systemd-tmpfiles (Red Hat)](https://developers.redhat.com/blog/2016/09/20/managing-temporary-files-with-systemd-tmpfiles-on-rhel7)
- [Logrotate ArchWiki](https://wiki.archlinux.org/title/Logrotate)

### tmpfiles.d for Temporary File Management

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| systemd-tmpfiles | systemd built-in | Declarative temporary file/directory creation and cleanup | Runs on boot; automatically creates `/run/ds01`, `/var/cache/ds01` with correct permissions |

**Example Configuration:**
```ini
# /etc/tmpfiles.d/ds01.conf
# Type Path          Mode UID  GID  Age Argument
d      /run/ds01      0755 root root -   -
d      /var/cache/ds01 0755 root root 7d  -
z      /var/lib/ds01  0750 root docker -  -
```

**Benefits:**
- No custom startup scripts to create directories
- Automatic cleanup of old cache files
- Permission enforcement on every boot

**Confidence:** HIGH - Standard systemd feature.

**Sources:**
- [tmpfiles.d Manual (freedesktop.org)](https://www.freedesktop.org/software/systemd/man/latest/tmpfiles.d.html)
- [Configuration of Temporary Files with systemd-tmpfiles (Baeldung)](https://www.baeldung.com/linux/systemd-tmpfiles-configure-temporary-files)

---

## Python Libraries for System Integration

### Python System Management

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| psutil | 5.x+ | Cross-platform system and process utilities | Get process info (PID, user, CPU, memory) for attribution |
| PyYAML | 6.x+ | YAML parsing | Already in use for `resource-limits.yaml` |
| python-systemd | 235+ | Python bindings for systemd API | Query systemd units, journal, cgroup status programmatically |
| docker-py | Latest | Docker Engine API client | Already in use; container inspection and management |
| pynvml | Latest | NVIDIA Management Library bindings | GPU process queries, power consumption, health metrics |

**Confidence:** HIGH - All libraries are mature and actively maintained.

**Sources:**
- [cgroup-utils on PyPI](https://pypi.org/project/cgroup-utils/)
- [psutil Documentation](https://psutil.readthedocs.io/)
- [pynvml on PyPI](https://pypi.org/project/nvidia-ml-py/)

---

## Supporting Tools

### Development and Debugging

| Tool | Purpose | Notes |
|------|---------|-------|
| bpftrace | eBPF-based kernel tracing | Advanced debugging for GPU driver activity, syscall tracing; requires kernel 4.x+ with eBPF |
| htop | Interactive process viewer | Standard tool for manual process inspection |
| iotop | IO monitoring | Identify users causing disk IO bottlenecks |
| ncdu | Disk usage analyser | Interactive tool for finding disk space hogs |

**Confidence:** HIGH - Standard Linux debugging toolkit.

**Sources:**
- [eBPF Introduction](https://ebpf.io/what-is-ebpf/)
- [eBPF Tracing Tutorial (Brendan Gregg)](https://www.brendangregg.com/ebpf.html)
- [eBPF GPU Driver Monitoring (eunomia)](https://eunomia.dev/tutorials/xpu/gpu-kernel-driver/)

---

## Installation Commands

### Core Resource Enforcement
```bash
# cgroups v2 is kernel-level, ensure systemd is using it
systemctl --version  # systemd 219+

# Disk quotas (XFS example)
sudo apt install xfsprogs quota
# Enable at mount: /etc/fstab → add 'uquota,pquota' to XFS mount options
```

### GPU Monitoring
```bash
# nvidia-smi already bundled with NVIDIA drivers

# nvitop (recommended)
pip3 install nvitop

# nvtop (alternative, requires compilation)
sudo apt install nvtop  # or compile from source
```

### Historical Analytics
```bash
# VictoriaMetrics single-node
wget https://github.com/VictoriaMetrics/VictoriaMetrics/releases/download/v1.134.0/victoria-metrics-linux-amd64-v1.134.0.tar.gz
tar xzf victoria-metrics-linux-amd64-v1.134.0.tar.gz
sudo mv victoria-metrics-prod /usr/local/bin/
sudo systemctl enable --now victoriametrics.service
```

### Alerting
```bash
# Alertmanager already deployed in DS01

# prometheus-msteams (for Teams integration)
wget https://github.com/prometheus-msteams/prometheus-msteams/releases/latest/download/prometheus-msteams-linux-amd64
sudo mv prometheus-msteams-linux-amd64 /usr/local/bin/prometheus-msteams
sudo systemctl enable --now prometheus-msteams.service
```

### Python Libraries
```bash
pip3 install psutil pynvml python-systemd
```

---

## Alternatives Considered

| Category | Recommended | Alternative | Why Not Alternative |
|----------|-------------|-------------|---------------------|
| Long-term storage | VictoriaMetrics | Thanos | Thanos requires object storage (S3/GCS) and multi-component architecture; overkill for single-server |
| Long-term storage | VictoriaMetrics | InfluxDB | Not Prometheus-native; requires separate query language (InfluxQL/Flux) |
| GPU monitoring | nvitop | gpustat | nvitop has better interactivity and Windows compatibility; gpustat is simpler but less feature-rich |
| User isolation | Docker userns-remap | OPA (Open Policy Agent) | OPA already attempted and caused problems; userns-remap is simpler and kernel-enforced |
| Scheduler | systemd timers | cron | systemd timers have `Persistent=true`, dependency management, better logging |
| Security MAC | AppArmor | SELinux | SELinux is more powerful but complex; AppArmor is Ubuntu default and easier for single admin |

---

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| cgroups v1 | Fragmented hierarchy; deprecated in modern kernels | cgroups v2 (unified hierarchy) |
| Custom cgroup scripts | Brittle; doesn't survive systemd updates | systemd resource-control directives |
| Manual log rotation | Unreliable; requires custom maintenance | logrotate + systemd timer |
| Hardcoded cron jobs | Can't track missed runs; no dependency management | systemd timers with `Persistent=true` |
| Microsoft Teams native webhooks | Deprecated August 2025; stops working October 2025 | prometheus-msteams bridge or Power Automate |
| Docker `--cgroup-parent` override | Security risk; bypasses DS01 enforcement | Enforce via Docker wrapper rejection |
| Running exporters without resource limits | Can OOM and crash monitoring stack | systemd `MemoryMax=` + `Restart=always` |
| Custom syslog setup | Deprecated in systemd-first distros | journald with structured logging |

---

## Stack Patterns by Use Case

### If you need bare metal GPU access restriction:
- Use NVIDIA Compute Mode "EXCLUSIVE_PROCESS" per GPU: `nvidia-smi -i 0 -c EXCLUSIVE_PROCESS`
- Detect violations via polling `nvidia-smi` and checking PIDs against allowed users
- Alert via Prometheus rule → Alertmanager → email/Teams

### If you need per-container IO limits:
- Use systemd `IODeviceWeight=`, `IOReadBandwidthMax=`, `IOWriteBandwidthMax=` in user slice
- Or Docker `--device-read-bps`, `--device-write-bps` flags (less flexible)
- Monitor with `iotop` or Prometheus `node_exporter` disk metrics

### If you need project-level quotas (not just user-level):
- Use XFS project quotas with project ID per collaboration
- Map project directories to project IDs in `/etc/projects` and `/etc/projid`
- Enforce with `xfs_quota -x -c 'limit -p bsoft=100g bhard=110g projectname'`

---

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| VictoriaMetrics v1.134.0 | Prometheus 2.x remote write API | Fully compatible; no version lock-in |
| Alertmanager v0.30.1 | Prometheus 2.x | UTF-8 matcher support; v1 API removed |
| nvitop | Python 3.8+ | Requires nvidia-ml-py (bundled with NVIDIA drivers) |
| systemd resource-control | Linux kernel 4.5+ (cgroups v2) | Ubuntu 20.04+ has cgroups v2 by default |
| Docker userns-remap | Docker Engine 1.10+ | Requires volume ownership remapping for existing containers |
| XFS quotas | XFS filesystem + kernel quota support | Ubuntu kernel has quota support compiled in |

---

## Implementation Priorities

### Phase 1: Resource Enforcement (Milestone 1)
1. Extend systemd slices with CPU, memory, IO limits
2. Enable XFS/ext4 disk quotas
3. Detect unmanaged containers via Docker API + label checks
4. Detect host GPU processes via nvidia-smi polling
5. Implement Docker userns-remap for user isolation (test first)

### Phase 2: Observability (Milestone 2)
1. Deploy VictoriaMetrics for long-term storage
2. Stabilise DCGM exporter (systemd restart policy, resource limits)
3. Add carbon metrics to DS01 Exporter (pyNVML power consumption)
4. Configure Alertmanager for email + Teams (via prometheus-msteams)

### Phase 3: Hygiene (Milestone 3)
1. Convert cron jobs to systemd timers
2. Configure logrotate for DS01 logs
3. Add tmpfiles.d configs for automatic directory creation
4. Implement automatic cleanup timers for idle containers, old images

---

## Confidence Assessment

| Area | Confidence | Reason |
|------|------------|--------|
| Resource enforcement (cgroups v2, systemd) | HIGH | Kernel feature, well-documented, production-proven in DS01 already |
| Disk quotas (XFS/ext4) | HIGH | Standard Linux capability, kernel-enforced |
| GPU process detection (nvidia-smi) | HIGH | Authoritative NVIDIA tool, already in use |
| Container detection (Docker API) | HIGH | Stable API, existing DS01 integration |
| User isolation (userns-remap) | MEDIUM | Feature is stable but requires careful migration and testing with existing containers |
| AppArmor | MEDIUM | Standard on Ubuntu but custom profiles need learning curve |
| Historical storage (VictoriaMetrics) | HIGH | Production-proven, excellent benchmarks, active development |
| Carbon metrics (pyNVML) | MEDIUM | pyNVML is reliable but carbon intensity requires external data or assumptions |
| Alerting (Alertmanager email) | HIGH | Standard Prometheus stack component |
| Alerting (Teams integration) | MEDIUM | Microsoft platform changes in 2025/2026 require bridge solution |
| systemd timers, logrotate, tmpfiles.d | HIGH | Standard Linux best practices for 2026 |
| eBPF tracing | LOW | Advanced tool, steep learning curve, use only for deep debugging |

---

## Open Questions for Phase-Specific Research

1. **User namespace migration:** How to migrate existing containers to userns-remap without data loss? Need detailed testing plan.
2. **Carbon grid intensity:** Should we hardcode university grid carbon intensity or integrate live API (e.g., WattTime, Electricity Maps)?
3. **AppArmor profiles:** What specific restrictions are needed beyond docker-default? Need to analyse attack vectors.
4. **VictoriaMetrics retention:** How much disk space for 1-year retention at 30s scrape interval? Needs capacity planning calculation.
5. **Teams integration:** Does university use Microsoft 365 with Power Automate licenses? May affect alerting implementation path.

---

## Sources

### Resource Enforcement
- [Linux cgroups v2 for Resource Isolation](https://medium.com/@springmusk/cgroups-v2-for-resource-isolation-in-linux-c413d11cd36f)
- [systemd.resource-control(5)](https://www.freedesktop.org/software/systemd/man/latest/systemd.resource-control.html)
- [Red Hat: Setting Resource Limits with Control Groups](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/8/html/managing_monitoring_and_updating_the_kernel/setting-limits-for-applications_managing-monitoring-and-updating-the-kernel)
- [How to Enable Disk Quota on XFS or Ext4](https://computingforgeeks.com/how-to-enable-disk-quota-on-xfs-or-ext4-linux-system/)
- [Red Hat: Limiting storage space usage on XFS with quotas](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/8/html/managing_file_systems/assembly_limiting-storage-space-usage-on-xfs-with-quotas_managing-file-systems)

### GPU Monitoring & Detection
- [Useful nvidia-smi Queries (NVIDIA)](https://nvidia.custhelp.com/app/answers/detail/a_id/3751/~/useful-nvidia-smi-queries)
- [nvitop on PyPI](https://pypi.org/project/nvitop/)
- [nvtop on GitHub](https://github.com/Syllo/nvtop)
- [GPU Monitoring Tools Comparison (Lambda Labs)](https://lambda.ai/blog/keeping-an-eye-on-your-gpus-2)

### Container Security & Isolation
- [Docker User Namespace Isolation](https://docs.docker.com/engine/security/userns-remap/)
- [Enhanced Container Isolation (Docker)](https://docs.docker.com/enterprise/security/hardened-desktop/enhanced-container-isolation/)
- [Container Security Fundamentals: User Namespaces (Datadog)](https://securitylabs.datadoghq.com/articles/container-security-fundamentals-part-2/)
- [Kubernetes User Namespace Isolation (CNCF)](https://www.cncf.io/blog/2025/07/16/securing-kubernetes-1-33-pods-the-impact-of-user-namespace-isolation/)
- [AppArmor vs SELinux for Container Isolation (Red Hat)](https://www.redhat.com/en/blog/apparmor-selinux-isolation)
- [Container Security: AppArmor and SELinux (Datadog)](https://securitylabs.datadoghq.com/articles/container-security-fundamentals-part-5/)
- [Docker Labels Best Practices](https://www.docker.com/blog/docker-best-practices-using-tags-and-labels-to-manage-docker-image-sprawl/)
- [OCI Container Annotations](https://snyk.io/blog/how-and-when-to-use-docker-labels-oci-container-annotations/)

### Historical Analytics
- [Thanos vs VictoriaMetrics Comparison (Last9)](https://last9.io/blog/thanos-vs-victoriametrics/)
- [VictoriaMetrics Changelog 2025](https://docs.victoriametrics.com/victoriametrics/changelog/changelog_2025/)
- [Prometheus Long-Term Storage Options (Greptime)](https://greptime.com/blogs/2024-08-16-prometheus-long-term-storage)

### Green Computing
- [Green Algorithms for Carbon Footprint (Advanced Science News)](https://www.advancedsciencenews.com/measuring-computers-carbon-footprint-with-green-algorithms/)
- [GPU Carbon Calculator Explained (Leafcloud)](https://leaf.cloud/blog/gpu-carbon-calculator-explained/)
- [NVIDIA Sustainable Computing](https://www.nvidia.com/en-us/data-center/sustainable-computing/)

### Monitoring & Alerting
- [Prometheus Exporters Best Practices (Sysdig)](https://www.sysdig.com/blog/prometheus-exporters-best-practices)
- [Writing Exporters (Prometheus)](https://prometheus.io/docs/instrumenting/writing_exporters/)
- [Mastering Prometheus Exporters (Checkly)](https://www.checklyhq.com/blog/mastering-prometheus-exporters-game-changing-techniques/)
- [Prometheus Alertmanager Releases](https://github.com/prometheus/alertmanager/releases)
- [Effective Alerting with Alertmanager (Better Stack)](https://betterstack.com/community/guides/monitoring/prometheus-alertmanager/)
- [prometheus-msteams Bridge](https://github.com/prometheus-msteams/prometheus-msteams)
- [Microsoft Teams Webhook Deprecation Issue](https://github.com/prometheus/alertmanager/issues/3920)

### Linux Best Practices
- [Use systemd timers instead of cronjobs (Opensource.com)](https://opensource.com/article/20/7/systemd-timers)
- [systemd Advanced Guide for 2026 (Medium)](https://medium.com/@springmusk/systemd-advanced-guide-for-2026-b2fe79af3e78)
- [Systemd Timers (Arch Wiki)](https://wiki.archlinux.org/title/Systemd/Timers)
- [logrotate with systemd timer (GitHub Gist)](https://gist.github.com/pancudaniel7/4ce4fb3ecebc70e97210cc36638ef8a9)
- [Managing Temporary Files with systemd-tmpfiles (Red Hat)](https://developers.redhat.com/blog/2016/09/20/managing-temporary-files-with-systemd-tmpfiles-on-rhel7)
- [Logrotate ArchWiki](https://wiki.archlinux.org/title/Logrotate)
- [tmpfiles.d Manual (freedesktop.org)](https://www.freedesktop.org/software/systemd/man/latest/tmpfiles.d.html)
- [Configuration of Temporary Files with systemd-tmpfiles (Baeldung)](https://www.baeldung.com/linux/systemd-tmpfiles-configure-temporary-files)

### Advanced Debugging
- [eBPF Introduction](https://ebpf.io/what-is-ebpf/)
- [eBPF Tracing Tutorial (Brendan Gregg)](https://www.brendangregg.com/ebpf.html)
- [eBPF GPU Driver Monitoring (eunomia)](https://eunomia.dev/tutorials/xpu/gpu-kernel-driver/)

---

*Stack research for: DS01 Infrastructure Milestone Enhancements*
*Researched: 2026-01-30*
