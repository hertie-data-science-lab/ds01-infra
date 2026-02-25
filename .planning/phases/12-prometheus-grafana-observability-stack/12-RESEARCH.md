# Phase 12: Prometheus & Grafana Observability Stack - Research

**Researched:** 2026-02-25
**Domain:** Prometheus/Grafana/DCGM GPU observability, cAdvisor, Alertmanager Teams integration
**Confidence:** HIGH (stack is well-documented; Teams integration has nuance — see details)

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Fix existing buggy dashboards — methodical audit of all panels
- Two audiences: admin dashboards (operational) + simplified user-facing dashboards
- **Clean separation**: real-time/current-state dashboards separate from historical/trend dashboards
- User-facing access: both Grafana (visual) and CLI commands (terminal)
- Existing user-facing CLI commands already exist — find and integrate them
- Current 47 alert rules are untested — methodical validation required
- **Teams-only notification** — drop email channel, Teams webhook created from scratch
- **90-day metric retention** — increase from current 7d/20GB
- **Fully automatic recovery** on reboot — zero manual intervention
- **Lean resource footprint** — monitoring must not consume significant CPU/RAM
- **Add cAdvisor** for per-container resource metrics (industry standard)
- **Lifecycle events in Prometheus** — enforcement actions (idle kills, runtime kills, GPU allocations, warnings) as metrics for dashboard panels
- **User login tracking** — SSH session data as Prometheus metrics
- **GPU cost attribution** — GPU-hours per user (awareness/fair-sharing, not billing); recording rules exist but untested
- Research-grounded: base everything on industry peer codebases and proven patterns

### Claude's Discretion
- Admin dashboard panel selection and layout
- Grafana authentication model (anonymous read-only vs LDAP)
- Version management strategy (pin vs latest)
- Alert approach (minimal-first vs audit-all)
- Exporter architecture (single enhanced DS01 exporter vs multiple)
- Login tracking granularity
- Resource limits for monitoring containers
- Recording rule optimisation

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| MON-01 | DCGM exporter runs reliably without crashing (auto-restart, health checks) | Hybrid compose+systemd pattern already works for DCGM; docker restart: unless-stopped with systemd fallback |
| MON-02 | DS01 exporter stable with comprehensive metrics | Exporter needs new metric families: lifecycle events, SSH sessions; existing architecture is sound |
| MON-03 | Prometheus scraping all targets reliably | cAdvisor target addition required; scrape config audit; `up{}` metric validates all targets |
| DASH-01 | Lab manager operational dashboard — real-time GPU/container/user status | Industry pattern: top-row stat gauges → time-series detail → per-entity breakdown |
| DASH-02 | Per-user self-service dashboard — own GPU-hours, quota usage, efficiency | Variable-based user filtering; recording rules already exist (ds01:user_gpu_seconds) |
| HIST-01 | Usage data retained long-term (1 year minimum) | 90-day in Prometheus is locked decision; VictoriaMetrics deferred; 90d is viable on small metric volume |
| HIST-02 | Visualise usage patterns over 1 week, 1 month, all-time | Grafana time range variable + recording rules for hourly aggregates |
| HIST-03 | Quantify total GPU-hours, number of users, demand patterns | ds01:user_gpu_seconds recording rules exist; need validation and increase() panel queries |
| ALERT-01 | Email notifications for critical system issues | Decision: drop email, Teams-only. This req is satisfied by Teams delivery of critical alerts |
| ALERT-02 | Teams notifications for critical system issues | msteamsv2_configs (Alertmanager v0.28+) with Power Automate Workflows webhook URL |
| ALERT-03 | Alert tuning — appropriate thresholds, no alert fatigue | Audit-then-prune approach: validate each of 47 rules fires correctly, prune noisy ones |
</phase_requirements>

---

## Summary

The DS01 monitoring stack is architecturally sound but unvalidated. The core components — Prometheus, Grafana, Alertmanager, DCGM Exporter, DS01 Exporter, Node Exporter — are all deployed but none has been tested end-to-end in production. This phase is primarily a **maturation and validation effort**, not a greenfield build.

The most significant external change affecting this phase is Microsoft's deprecation of Office 365 Connectors (Teams Incoming Webhooks). The old `msteams_config` mechanism the current alertmanager.yml uses is dead as of October 2024. Alertmanager v0.28.0 (December 2024) introduced `msteamsv2_configs` for Power Automate Workflows, which is the correct migration path — but it requires creating a new webhook via the Teams Workflows app (not the old Connectors mechanism). The existing alertmanager.yml webhook URL format (`webhookb2/...`) is the deprecated format.

For GPU monitoring, the DCGM Exporter has been updated to v4.5.2 (February 2026) while the stack is pinned to v3.3.0. The existing `dcp-metrics-included.csv` collector file and the profiling metrics (DCGM_FI_PROF_GR_ENGINE_ACTIVE) used by DS01's MIG recording rules are still the correct approach. Adding cAdvisor for per-container CPU/memory/network metrics is the industry standard complement to DCGM.

**Primary recommendation:** Audit-first approach — validate every existing component before adding new ones; fix the Teams integration as the first priority since it blocks any alert delivery.

---

## Standard Stack

### Core (already deployed — version audit required)

| Component | Current Version | Latest Stable | Purpose | Notes |
|-----------|----------------|--------------|---------|-------|
| Prometheus | v2.48.0 | v3.1.x (2025) | TSDB + alerting engine | v2.48 is old but stable; upgrade to v2.55+ for wal-compression improvements |
| Grafana | v10.2.0 | v11.6 (Mar 2025) | Dashboards | v10.2 is mature; upgrade to v11.x for Scenes dashboards |
| Alertmanager | v0.28.1 | v0.28.1 | Alert routing | Already at correct version for msteamsv2_configs |
| DCGM Exporter | v3.3.0-3.2.0 | v4.5.2-4.8.1 (Feb 2026) | GPU hardware metrics | Version gap is significant; latest has MIG improvements |
| Node Exporter | v1.7.0 | v1.9.x | System metrics | Stable, minor update available |
| DS01 Exporter | v2.1.0 (custom) | N/A | DS01-specific metrics | Extend for new metric families |

### New Components to Add

| Component | Version | Purpose | Resource Overhead |
|-----------|---------|---------|------------------|
| cAdvisor | v0.49.x | Per-container CPU/memory/network/disk I/O | ~30MB RAM, <1% CPU |

### Supporting Libraries (already used)

| Component | Purpose |
|-----------|---------|
| prometheus_client (Python) | DS01 exporter metric emission — NOT currently used (raw HTTP server); should migrate |
| prom/alertmanager templates | Go template syntax for alert message formatting |

---

## Architecture Patterns

### Current Deployment Architecture

```
Host Machine
├── systemd services
│   ├── ds01-exporter.service (port 9101)     ← DS01-specific metrics
│   └── ds01-dcgm-exporter.service             ← manages restart of DCGM container
│
└── docker-compose (ds01-monitoring network)
    ├── node-exporter     :9100  ← system metrics (CPU, mem, disk, net)
    ├── dcgm-exporter     :9400  ← GPU hardware metrics (MIG-aware)
    ├── cadvisor          :8080  ← per-container metrics (TO BE ADDED)
    ├── prometheus        :9090  ← scrapes all above; runs rules
    ├── alertmanager      :9093  ← receives alerts from prometheus
    └── grafana           :3000  ← visualises prometheus data
```

**Key architectural constraint:** DS01 exporter runs on the host (not in Docker) because it needs access to `/var/lib/ds01` state files and gpu-state-reader.py. This is correct and should be preserved.

### Pattern 1: cAdvisor Deployment (Add to docker-compose.yaml)

Industry-standard deployment per [Prometheus cAdvisor guide](https://prometheus.io/docs/guides/cadvisor/):

```yaml
cadvisor:
  image: gcr.io/cadvisor/cadvisor:v0.49.1
  container_name: ds01-cadvisor
  restart: unless-stopped
  privileged: true
  ports:
    - "127.0.0.1:8080:8080"
  volumes:
    - /:/rootfs:ro
    - /var/run:/var/run:ro
    - /sys:/sys:ro
    - /var/lib/docker/:/var/lib/docker:ro
    - /dev/disk/:/dev/disk:ro
  devices:
    - /dev/kmsg
  deploy:
    resources:
      limits:
        memory: 256M
        cpus: '0.15'
  labels:
    - "ds01.monitoring=true"
    - "ds01.protected=true"
  networks:
    - ds01-monitoring
```

**Why privileged:** Required on Ubuntu for cgroup access. The container only reads cgroup data, not modify it.

**Scrape config to add in prometheus.yml:**
```yaml
- job_name: 'cadvisor'
  static_configs:
    - targets: ['cadvisor:8080']
  scrape_interval: 30s
  metric_relabel_configs:
    # Drop high-cardinality metrics not needed for DS01
    - source_labels: [__name__]
      regex: 'container_(tasks_state|blkio.*|spec.*)'
      action: drop
```

**Cardinality note:** cAdvisor generates many high-cardinality metrics. The `metric_relabel_configs` drop clause above is a proven pattern to reduce storage load while keeping the metrics that matter (CPU, memory, network, disk I/O per container).

### Pattern 2: Teams Integration via msteamsv2_configs

**Critical finding:** The existing alertmanager.yml uses the deprecated `webhook_configs` with an Office 365 Connector URL (`webhookb2/...` format). This stopped working in October 2024. The correct migration is:

1. Create a new workflow in Teams via the **Workflows** app (not Connectors)
2. Use the "Post to a channel when a webhook request is received" template
3. Copy the resulting Power Automate webhook URL (format: `https://prod-XX.eastus.logic.azure.com:443/workflows/...`)
4. Configure Alertmanager with `msteamsv2_configs` (available in v0.28.0+, already deployed)

Alertmanager v0.28.1 (currently deployed) has native `msteamsv2_configs` support:

```yaml
receivers:
  - name: 'ds01-teams'
    msteamsv2_configs:
      - webhook_url: 'https://prod-XX.eastus.logic.azure.com:443/workflows/...'
        send_resolved: true
        title: '{{ template "msteams.v2.title" . }}'
        text: '{{ template "msteams.v2.text" . }}'
```

**Note on email removal:** The current alertmanager.yml sends to two email addresses AND Teams. Per user decision: drop email entirely, keep only Teams. This simplifies the config and removes SMTP dependency.

### Pattern 3: Prometheus Retention — 90-day Configuration

Current: `--storage.tsdb.retention.time=7d --storage.tsdb.retention.size=20GB`

Target: 90-day retention

**Disk space estimation for DS01:**
- Metric families: ~500-800 active series (DCGM ~200, node-exporter ~300, DS01 exporter ~100, cAdvisor ~200)
- Scrape interval: 15-30s
- Bytes per sample: ~1.5 bytes average (with WAL compression)
- Formula: `90d × 86400s × (800 series × 1 sample/30s) × 1.5 bytes = ~310MB`
- Real-world overhead (WAL, compaction, index): 3-5× → **~1.5-3GB total**

**Recommended configuration:**
```yaml
command:
  - '--storage.tsdb.retention.time=90d'
  - '--storage.tsdb.retention.size=15GB'   # Safety cap; 80-85% of allocated volume
  - '--storage.tsdb.wal-compression'        # Already present, keep it
```

**Why 15GB cap:** At ~3GB actual usage, 15GB is generous headroom. The size cap prevents runaway disk usage if cardinality spikes. Set to 80% of whatever volume is allocated.

**Prometheus resource bump required:**
```yaml
deploy:
  resources:
    limits:
      memory: 4G   # Increase from 2G for 90-day head block
      cpus: '0.5'  # Keep the same
```

### Pattern 4: Alert Audit Approach — Audit-then-Prune

For 47 untested rules, industry best practice is NOT to delete speculatively. Instead:

1. **Fire each alert manually** using PromQL to verify the expression returns results
2. **Test delivery** via `amtool` or Alertmanager API
3. **Categorise:** actionable (keep), too noisy (tune `for:` duration), wrong metric (fix expr), irrelevant (remove)

Common pitfalls found in current rules:
- `DS01GPUWaste` uses metric `ds01_gpu_utilization_percent` which does NOT exist in the exporter — DCGM provides `DCGM_FI_DEV_GPU_UTIL`. This alert will never fire.
- `DS01GPUHighTemperature` uses `ds01_gpu_temperature_celsius` — same problem, should be `DCGM_FI_DEV_GPU_TEMP`.
- `DS01GPUMemoryHigh` uses `ds01_gpu_memory_used_bytes / ds01_gpu_memory_total_bytes` — neither metric exists; should use DCGM framebuffer metrics.
- `DS01UserGPUWaste` uses recording rule `ds01:user_gpu_utilization_avg` which depends on `ds01_gpu_allocated` joining with DCGM — this join may work if exporter is up.
- `DS01GrafanaDown` and `DS01AlertmanagerDown` reference `up{job="grafana"}` and `up{job="alertmanager"}` but these jobs are not in `prometheus.yml` — they will never fire.

**Recommendation:** Start with the "infrastructure scrape" alerts (exporter down, DCGM down) as those are highest value and simplest. Fix metric names before tuning thresholds.

### Pattern 5: Grafana Authentication — Anonymous Read-Only

For an internal server with SSH-accessible users, anonymous read-only is the correct model:

```ini
[auth.anonymous]
enabled = true
org_name = Main Org.
org_role = Viewer
hide_version = true
```

Combined with admin user for editing:
```yaml
environment:
  - GF_AUTH_ANONYMOUS_ENABLED=true
  - GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer
  - GF_AUTH_ANONYMOUS_HIDE_VERSION=true
```

**Why not LDAP:** This is an internal single-org server. LDAP adds complexity without benefit — admin is the only editor. Users only need read access to their own usage data (anonymous viewer is sufficient).

### Pattern 6: Dashboard Design — Industry-Grounded Layout

Based on [NVIDIA/deepops monitoring](https://github.com/NVIDIA/deepops/blob/master/docs/slurm-cluster/slurm-monitor.md), [AWS ParallelCluster monitoring](https://github.com/aws-samples/aws-parallelcluster-monitoring), and [Grafana HPC dashboard community](https://grafana.com/grafana/dashboards/24182):

**Admin dashboard structure (top → bottom hierarchy):**

Row 1 — Status at a Glance (stat panels):
- GPU Slots Allocated / Total
- Active Users
- Running Containers
- System GPU Utilisation (avg)
- Highest GPU Temperature

Row 2 — Real-time Time Series (last 1h):
- GPU Utilisation per device (separate series per MIG slot / GPU)
- GPU Memory % per device
- GPU Power (W) per device
- GPU Temperature (°C) per device

Row 3 — Container & User Activity:
- Containers by user (table: user → container → GPU slot → runtime → utilisation)
- Unmanaged GPU containers alert panel
- Enforcement activity (idle kills, runtime kills, warnings — from new lifecycle metrics)

Row 4 — System Health:
- CPU load average (1m/5m/15m)
- Memory available %
- Disk usage key partitions
- Exporter `up{}` status panel (all scrape targets)

**User dashboard (per-user variable filtering):**

Row 1 — My Current Status:
- My GPU allocations (stat)
- My containers running (stat)
- My GPU utilisation (gauge)

Row 2 — My History:
- GPU-hours used this week/month (bar chart from recording rules)
- GPU utilisation over time (time series)

Row 3 — My Quota:
- Memory usage vs limit
- GPU slots vs quota
- Container count vs limit

**Separate historical/trend dashboard:**

- GPU utilisation heatmap (week/month)
- GPU-hours by user over time (stacked bar)
- System demand patterns (time-of-day heat)
- Capacity trend (allocated slots over time)

### Pattern 7: Lifecycle Events as Prometheus Metrics

Enforcement actions (idle kills, runtime kills, warnings) should become Prometheus counters exposed by the DS01 exporter. This is a standard instrumentation pattern — see [Prometheus instrumentation guide](https://prometheus.io/docs/practices/instrumentation/).

**Metric types to add to DS01 exporter:**

```python
# Counters — never decrease, survive restarts via state file
ds01_lifecycle_events_total{action="idle_warning", level="first"}
ds01_lifecycle_events_total{action="idle_warning", level="final"}
ds01_lifecycle_events_total{action="idle_kill"}
ds01_lifecycle_events_total{action="runtime_warning", level="first"}
ds01_lifecycle_events_total{action="runtime_warning", level="final"}
ds01_lifecycle_events_total{action="runtime_kill"}

# Source: parse events.jsonl (already read by exporter for ds01_events_24h_total)
# Implementation: extend collect_event_counts() to also emit per-action totals
```

**Dashboard pattern:** Use `increase(ds01_lifecycle_events_total[24h])` for "events today" stat panels. Use `rate()` for time-series trend panels.

**Implementation note:** The existing `collect_event_counts()` function already parses `events.jsonl` — these metrics can be derived from the same data. The event types in `events.jsonl` map directly to action labels (e.g., `container.idle_killed`, `container.runtime_killed`, `container.idle_warning`).

### Pattern 8: SSH Login Tracking

Node Exporter has a built-in `logind` collector (disabled by default) that exposes session counts via D-Bus:

```
--collector.logind
```

This produces metrics like `node_logind_sessions` with labels for session type (x11, tty, wayland, mir, unspecified) and class (user, greeter, lock-screen).

**Recommended approach:** Enable the `logind` collector in Node Exporter (zero additional components):

```yaml
command:
  - '--collector.logind'    # Add to existing node-exporter command flags
```

This gives an active SSH sessions gauge with no new code. For per-user detail, the DS01 exporter can parse `/var/run/utmp` or `who` output and emit `ds01_ssh_sessions_active{user="alice"}` — simple to add to `collect_user_metrics()`.

**Decision rationale:** Active session count gauge is sufficient for the dashboard. Per-user session history is not required (was listed as Claude's discretion on granularity). The `logind` collector covers the admin need; per-user gauge in DS01 exporter covers the user dashboard.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| GPU hardware metrics | Custom nvidia-smi parser | DCGM Exporter | Native driver access, MIG-aware, maintained by NVIDIA |
| Container CPU/memory/network | Custom docker stats parser | cAdvisor | Production-grade, handles cgroup v2, low overhead |
| Teams alert delivery | Custom HTTP webhook sender | Alertmanager msteamsv2_configs | Already in deployed Alertmanager v0.28.1 |
| SSH session tracking | Custom PAM module / auth.log parser | node_exporter --collector.logind | Built into already-deployed node exporter |
| Dashboard version control | Manual export/import | Grafana file provisioning (already configured) | Already set up — dashboards auto-loaded from JSON files |
| Metric retention beyond 90d | VictoriaMetrics/Thanos | Prometheus native 90d | 90d is the locked decision; 3GB storage is trivial |

**Key insight:** The existing stack is more capable than currently used. Before adding components, enable what's already there.

---

## Common Pitfalls

### Pitfall 1: Alert Expressions Reference Non-Existent Metrics
**What goes wrong:** 10+ alert rules reference `ds01_gpu_*` metrics that don't exist — the exporter provides DCGM metrics under `DCGM_FI_*` names. These alerts silently never fire.
**Root cause:** Alert rules were written against a planned metric schema before the decision to use DCGM as the GPU metrics source.
**How to avoid:** For each alert rule, manually query its `expr` in Prometheus UI and verify it returns data. If it returns no data, the rule needs fixing.
**Warning signs:** `ALERTS` metric in Prometheus shows 0 pending/firing for expected conditions.

### Pitfall 2: Teams Webhook URL Format Mismatch
**What goes wrong:** The current `webhook_configs` URL (`webhookb2/...`) was a deprecated O365 Connector URL format. As of October 2024 it no longer works.
**Root cause:** Microsoft retired O365 Connectors. The new Power Automate webhook URL format is completely different (`https://prod-XX.region.logic.azure.com:443/workflows/...`).
**How to avoid:** Use `msteamsv2_configs` (Alertmanager v0.28+) and create a fresh webhook via Teams → Workflows app. The `msteams_configs` key remains in Alertmanager for legacy but points to a dead endpoint.
**Verification:** After creating, send a test alert via `amtool alert add testname` and verify it appears in Teams.

### Pitfall 3: cAdvisor High Cardinality
**What goes wrong:** cAdvisor generates hundreds of metric families, many with high cardinality (per-container × per-operation labels). Storage can balloon unexpectedly.
**Root cause:** Default cAdvisor exposes everything including block I/O per device, per-filesystem, etc.
**How to avoid:** Add `metric_relabel_configs` with drop rules for `container_(tasks_state|blkio.*|spec.*)` patterns that aren't needed for DS01 use cases.
**Warning signs:** Prometheus `prometheus_tsdb_head_series` count spikes sharply after adding cAdvisor.

### Pitfall 4: Recording Rules Depend on Unavailable Metrics
**What goes wrong:** `ds01:user_gpu_utilization_avg` joins `ds01_gpu_allocated` with `ds01:gpu_utilization_by_slot` — if DCGM is down, the join produces no results, making user utilisation dashboards blank.
**Root cause:** The `or vector(0)` fallback in the recording rule produces 0 instead of "no data" — which is misleading in dashboards.
**How to avoid:** Test recording rules with DCGM simulated as down. Dashboard panels should use "No value" display rather than showing 0%.
**Warning signs:** Dashboard shows 0% utilisation even when DCGM is up.

### Pitfall 5: Retention Size vs Time Both Set
**What goes wrong:** Setting both `retention.time=90d` and `retention.size=15GB` means whichever triggers first wins. If the size cap is too small, data gets deleted before 90 days.
**Root cause:** Both flags are independent limits; the smaller wins.
**How to avoid:** Calculate expected storage first (see Architecture Patterns section). Set `retention.size` as a safety cap well above expected usage, not as the primary retention mechanism.

### Pitfall 6: DCGM Exporter Version Gap
**What goes wrong:** The stack uses DCGM Exporter v3.3.0 while v4.5.2 is current (Feb 2026). The image tag `nvcr.io/nvidia/k8s/dcgm-exporter:3.3.0-3.2.0-ubuntu22.04` may not be pulling updates.
**Root cause:** Version is pinned in docker-compose.yaml.
**How to avoid:** The v3.3.0 → v4.x jump may have breaking changes in metric names or MIG handling. Test version upgrade in isolation before deploying. The `dcp-metrics-included.csv` approach and `DCGM_FI_PROF_GR_ENGINE_ACTIVE` for MIG is still correct in v4.x.
**Decision:** For this phase, leave DCGM at v3.3.0 unless a specific bug drives an upgrade. Version upgrades are out of scope for a maturation/validation phase.

### Pitfall 7: Prometheus Volume Mount vs Named Volume for 90-day Data
**What goes wrong:** If the `prometheus-data` Docker volume is on the same filesystem as OS, 90 days of data could fill the root partition.
**Root cause:** Default Docker volume location is `/var/lib/docker/volumes/`.
**How to avoid:** Verify free space on the Docker data partition before extending retention. If `/var/lib/docker` is on root, consider a bind mount to a dedicated data partition.

---

## Code Examples

Verified patterns from official documentation and codebase analysis:

### Prometheus scrape config for cAdvisor
```yaml
# Source: https://prometheus.io/docs/guides/cadvisor/
- job_name: 'cadvisor'
  static_configs:
    - targets: ['cadvisor:8080']
      labels:
        ds01_category: 'infrastructure'
        ds01_component: 'cadvisor'
  scrape_interval: 30s
  metric_relabel_configs:
    - source_labels: [__name__]
      regex: 'container_(tasks_state|blkio_io_service_bytes_recursive|blkio_io_serviced_recursive|spec_.*)'
      action: drop
    # Keep only DS01-named containers (has ds01.user label or monitoring stack)
    - source_labels: [container_label_ds01_user]
      regex: '.+'
      target_label: ds01_user
```

### msteamsv2_configs in alertmanager.yml
```yaml
# Source: Alertmanager v0.28 docs — msteamsv2_configs
# https://prometheus.io/docs/alerting/latest/configuration/
receivers:
  - name: 'ds01-teams'
    msteamsv2_configs:
      - webhook_url: 'https://prod-XX.eastus.logic.azure.com:443/workflows/...'
        send_resolved: true
        title: '[DS01] {{ .Status | toUpper }}: {{ .CommonLabels.alertname }}'
        text: |
          **Severity:** {{ .CommonLabels.severity }}
          {{ range .Alerts }}
          **{{ .Annotations.summary }}**
          {{ .Annotations.description }}
          {{ end }}
```

**Note on email removal:** Simply replace both email_configs receiver blocks with a single msteamsv2_configs block. Remove the `global` SMTP settings too.

### DS01 Exporter: Lifecycle counter metric addition
```python
# Extend collect_event_counts() in ds01_exporter.py
# New: emit per-action counters from events.jsonl

# Map event_type → metric labels
LIFECYCLE_EVENT_MAP = {
    'container.idle_killed':        {'action': 'idle_kill'},
    'container.runtime_killed':     {'action': 'runtime_kill'},
    'container.idle_warning':       {'action': 'idle_warning', 'level': 'first'},
    'container.idle_warning_final': {'action': 'idle_warning', 'level': 'final'},
    'container.runtime_warning':    {'action': 'runtime_warning', 'level': 'first'},
    'container.runtime_warning_final': {'action': 'runtime_warning', 'level': 'final'},
}

# Emit: ds01_lifecycle_events_total{action="idle_kill"} N
# Use same event cache already built by collect_event_counts()
```

**Note:** The actual event type strings used in events.jsonl should be verified against the existing event logger in `scripts/lib/ds01_events.py` and lifecycle scripts.

### Node Exporter logind collector enablement
```yaml
# In docker-compose.yaml, node-exporter service command section
command:
  - '--path.procfs=/host/proc'
  - '--path.sysfs=/host/sys'
  - '--path.rootfs=/rootfs'
  - '--collector.filesystem.mount-points-exclude=^/(sys|proc|dev|host|etc)($$|/)'
  - '--collector.systemd'
  - '--collector.logind'    # ADD THIS — disabled by default
  - '--no-collector.arp'
  # ... rest unchanged
```

This adds `node_logind_sessions` gauge with type/class labels — SSH sessions show as `session_type="unspecified"` or `session_type="tty"`.

### Alert fix example — GPU temperature (wrong metric → correct metric)
```yaml
# BEFORE (broken — metric does not exist)
- alert: DS01GPUHighTemperature
  expr: ds01_gpu_temperature_celsius > 85

# AFTER (fixed — uses DCGM metric name)
- alert: DS01GPUHighTemperature
  expr: DCGM_FI_DEV_GPU_TEMP > 85
  for: 5m
  labels:
    severity: warning
  annotations:
    summary: "GPU {{ $labels.gpu }} temperature above 85°C"
    description: "GPU {{ $labels.gpu }} ({{ $labels.modelName }}) at {{ $value }}°C"
```

### Grafana anonymous access config (env vars in docker-compose)
```yaml
environment:
  - GF_SECURITY_ADMIN_USER=${GRAFANA_ADMIN_USER:-admin}
  - GF_SECURITY_ADMIN_PASSWORD=${GRAFANA_ADMIN_PASSWORD:-ds01admin}
  - GF_AUTH_ANONYMOUS_ENABLED=true
  - GF_AUTH_ANONYMOUS_ORG_ROLE=Viewer
  - GF_AUTH_ANONYMOUS_HIDE_VERSION=true
  - GF_USERS_ALLOW_SIGN_UP=false
```

### Grafana provisioning — allowUiUpdates for dashboard editing workflow
```yaml
# monitoring/grafana/provisioning/dashboards/default.yml
# Current: allowUiUpdates: false
# Change to: allowUiUpdates: true
# Why: During the audit/fix phase, admins need to edit panels in UI then export JSON
# After phase is complete: set back to false for production stability
```

---

## State of the Art

| Old Approach | Current Approach | Notes |
|--------------|-----------------|-------|
| Teams Incoming Webhooks (O365 Connectors) | Power Automate Workflows + `msteamsv2_configs` | Breaking change Oct 2024; old URL format dead |
| DCGM v3.x | DCGM v4.5.x | v4 has improved MIG metrics; existing recording rules still work |
| Prometheus v2.48 | Prometheus v2.55+ (or v3.x) | v3 is experimental; v2.55 adds OTLP improvements; v2.48 is functional for DS01 |
| Grafana v10.2 | Grafana v11.6 | v11 Scenes dashboards, improved provisioning; v10.2 works fine |
| `msteams_configs` (deprecated) | `msteamsv2_configs` (Alertmanager v0.28+) | Already on correct version; config needs updating |
| Email alerts | Teams-only | Removes SMTP dependency |

**Deprecated/outdated in current config:**
- `msteams_configs` with `webhookb2` URL: dead since Oct 2024, must replace with `msteamsv2_configs`
- Email `smtp_smarthost`, `smtp_from`, `smtp_auth_*` in alertmanager global: remove once Teams-only
- `GF_DATABASE_WAL=true` in Grafana: this is now default in v10+, but keeping it is harmless
- `allowUiUpdates: false` in dashboard provisioner: correct for production but blocks fixing dashboards — set true during work phase

---

## Open Questions

1. **What are the actual event_type strings in events.jsonl?**
   - What we know: `collect_event_counts()` reads events.jsonl and groups by `event_type`
   - What's unclear: Exact strings for idle kills, runtime kills, warnings (may differ from what lifecycle scripts emit)
   - Recommendation: During implementation, query `ds01_events_24h_total` metric labels in Prometheus to discover actual event types in use

2. **Docker volume partition for 90-day Prometheus data**
   - What we know: `ds01-prometheus-data` is a named Docker volume; estimated 1.5-3GB needed
   - What's unclear: Which partition `/var/lib/docker` sits on and available free space
   - Recommendation: Check with `df -h /var/lib/docker` before changing retention; add a health check alert on `node_filesystem_avail_bytes`

3. **DCGM Exporter systemd service deployment status**
   - What we know: Service file exists at `config/deploy/systemd/ds01-dcgm-exporter.service`; listed as a pending todo in STATE.md
   - What's unclear: Whether DCGM is currently crashing in production without the systemd wrapper
   - Recommendation: Verify DCGM container status as first task; if crashing, deploy systemd service immediately

4. **Teams webhook URL**
   - What we know: Old URL in alertmanager.yml is dead; `msteamsv2_configs` is the correct format
   - What's unclear: The Power Automate webhook URL format requires manual creation in Teams UI — this is a human action, not automatable
   - Recommendation: Document the exact steps in the plan; URL will need to be placed in a `.env` file or environment variable (do NOT commit to git)

5. **DS01 exporter: `prometheus_client` library vs raw HTTP server**
   - What we know: Current exporter uses a hand-rolled HTTP server and raw text format
   - What's unclear: Whether switching to `prometheus_client` Python library would be worth it for new metric types
   - Recommendation: Keep raw HTTP approach for now — the existing pattern works and migration is out of scope. New metric families (lifecycle events, SSH sessions) can follow the same raw text pattern.

---

## Existing User-Facing CLI Commands (to integrate)

These were found in the codebase — the context notes say to find and integrate them:

| Command | Location | Purpose |
|---------|----------|---------|
| `check-limits` | `scripts/user/helpers/check-limits` | Shows GPU/memory/task usage vs limits with progress bars |
| `ds01-status` | `scripts/user/helpers/ds01-status` | Shows systemd slice hierarchy, GPU usage, running containers |
| `quota-check` | `scripts/user/helpers/quota-check` | Disk quota check |
| `container-stats` | `scripts/user/atomic/container-stats` | Container resource usage |
| `ds01-dashboard` | `scripts/admin/ds01-dashboard` | Admin CLI dashboard |
| `dashboard` | `scripts/admin/dashboard` | Alias for admin dashboard |
| `gpu-status-dashboard.py` | `scripts/monitoring/gpu-status-dashboard.py` | GPU allocation dashboard |
| `container-dashboard.sh` | `scripts/monitoring/container-dashboard.sh` | Container resource dashboard |

The "integration" here means: Grafana dashboards should complement (not replace) these CLI tools. The CLI tools are the "quick terminal check" path; Grafana is the "visual exploration" path. They should show consistent data from the same sources.

---

## Validation Architecture

### Test Framework

| Property | Value |
|----------|-------|
| Framework | pytest (configured in `/opt/ds01-infra/testing/pytest.ini`) |
| Config file | `/opt/ds01-infra/testing/pytest.ini` |
| Quick run command | `cd /opt/ds01-infra/testing && pytest unit/monitoring/ -v` |
| Full suite command | `cd /opt/ds01-infra/testing && pytest -m "not runtime"` |
| Runtime tests | `cd /opt/ds01-infra/testing && sudo pytest -m runtime` |
| Estimated runtime | ~30 seconds (unit/monitoring only) |

### Phase Requirements → Test Map

| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|--------------|
| MON-01 | DCGM exporter stays up; auto-restarts on crash | manual/smoke | `docker inspect ds01-dcgm-exporter --format='{{.State.Status}}'` | ❌ needs smoke test |
| MON-02 | DS01 exporter exposes all required metrics | unit | `pytest unit/monitoring/test_ds01_exporter.py -v` | ✅ partial |
| MON-03 | All scrape targets healthy | smoke | `curl -s localhost:9090/api/v1/targets \| jq '.data.activeTargets[] \| {job, health}'` | ❌ Wave 0 gap |
| DASH-01 | Admin dashboard loads with data | manual | Grafana visual check | manual only |
| DASH-02 | User dashboard filters by user variable | manual | Grafana visual check | manual only |
| HIST-01 | 90-day retention configured and data retained | smoke | `curl -s localhost:9090/api/v1/status/config \| jq '.data.retentionTime'` | ❌ Wave 0 gap |
| HIST-02 | Historical queries return data | smoke | PromQL query for data >7d old | ❌ (requires time) |
| HIST-03 | GPU-hours recording rules return values | unit/smoke | PromQL `ds01:user_gpu_seconds` query | ❌ Wave 0 gap |
| ALERT-01 | No email channels (dropped) | unit | Config file validation | ❌ Wave 0 gap |
| ALERT-02 | Teams delivery works | manual | `amtool alert add test --alertmanager.url=http://localhost:9093` | manual |
| ALERT-03 | Alert rules reference valid metrics | unit/smoke | PromQL query for each alert expr | ❌ Wave 0 gap |

### Wave 0 Gaps

- [ ] `testing/unit/monitoring/test_monitoring_config.py` — expand existing file for alert rule validation (query each alert expr against Prometheus API, verify it returns data structure; mock for unit tests)
- [ ] `testing/unit/monitoring/test_alertmanager_config.py` — validate alertmanager.yml: no email_configs, msteamsv2_configs present, correct routing tree
- [ ] `testing/unit/monitoring/test_prometheus_config.py` — validate prometheus.yml: all required scrape targets present (dcgm, ds01, node, cadvisor, prometheus), retention configured

---

## Sources

### Primary (HIGH confidence)
- [Prometheus Storage Docs](https://prometheus.io/docs/prometheus/latest/storage/) — retention flags, compaction, size estimation
- [Prometheus Alertmanager Configuration](https://prometheus.io/docs/alerting/latest/configuration/) — `msteamsv2_configs` options
- [Grafana Anonymous Access](https://grafana.com/docs/grafana/latest/setup-grafana/configure-access/configure-authentication/anonymous-auth/) — exact env var configuration
- [Prometheus cAdvisor Guide](https://prometheus.io/docs/guides/cadvisor/) — deployment pattern, volume mounts
- [NVIDIA DCGM Exporter GitHub](https://github.com/NVIDIA/dcgm-exporter) — current version v4.5.2-4.8.1, metrics CSV
- [Alertmanager PR #4024](https://github.com/prometheus/alertmanager/pull/4024) — msteamsv2 merged in v0.28.0

### Secondary (MEDIUM confidence)
- [Microsoft Office 365 Connectors Retirement Blog](https://devblogs.microsoft.com/microsoft365dev/retirement-of-office-365-connectors-within-microsoft-teams/) — deadline April 30, 2026; Power Automate is replacement
- [Alertmanager Issue #3920](https://github.com/prometheus/alertmanager/issues/3920) — Teams deprecation impact; community workarounds
- [Grafana HPC Dashboard #24182](https://grafana.com/grafana/dashboards/24182-hpc-combined-node-ib-gpu-profiling-included-nvlink-metrics-dashboard/) — HPC peer dashboard structure
- [Grafana Upgrade Strategy](https://grafana.com/docs/grafana/latest/upgrade-guide/when-to-upgrade/) — minor-release following for production
- [NVIDIA deepops Slurm Monitor](https://github.com/NVIDIA/deepops/blob/master/docs/slurm-cluster/slurm-monitor.md) — reference SLURM+GPU monitoring stack
- [node_exporter logind collector](https://github.com/prometheus/node_exporter/blob/master/collector/logind_linux.go) — `--collector.logind` for SSH session tracking

### Tertiary (LOW confidence — needs validation)
- Teams `msteamsv2_configs` behaviour with Power Automate: confirmed merged (v0.28.0) but some users report 400 errors (issue #4434). Needs live test to confirm working configuration.
- cAdvisor privileged mode on Ubuntu 22.04: works per community reports but should be validated on actual server.

---

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH — all components are official and well-documented
- Architecture: HIGH — codebase directly inspected; existing patterns understood
- Teams integration: MEDIUM-HIGH — merged in v0.28.0 (deployed) but some compatibility reports; test before declaring done
- Alert rule bugs: HIGH — directly identified by cross-referencing alert exprs against exporter metric names in codebase
- Pitfalls: HIGH — drawn from direct code inspection + authoritative sources

**Research date:** 2026-02-25
**Valid until:** 2026-05-25 (stable stack; Teams API changes could happen sooner)
