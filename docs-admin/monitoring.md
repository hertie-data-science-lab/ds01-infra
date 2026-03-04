# DS01 Monitoring Operations Guide

Practical reference for day-to-day monitoring tasks on the DS01 observability stack.
Stack: Prometheus · Grafana · Alertmanager · cAdvisor · DCGM Exporter · node-exporter · ds01-exporter

---

## 1. Accessing Grafana

Grafana is localhost-only. Access via SSH tunnel:

```bash
ssh -L 3000:localhost:3000 datasciencelab@ds01
```

Then open: **http://localhost:3000**

Login: `admin` / `ds01admin` (override with `GRAFANA_ADMIN_USER` / `GRAFANA_ADMIN_PASSWORD` env vars in `monitoring/.env`)

Prometheus UI: `http://localhost:9090` (same SSH tunnel session, or add `-L 9090:localhost:9090`)
Alertmanager UI: `http://localhost:9093`

---

## 2. Dashboard Guide

Four dashboards are provisioned automatically from `monitoring/grafana/provisioning/dashboards/dashboards/`.

### DS01 Overview (`ds01-overview`)

Real-time operational view. Use this for day-to-day monitoring.

| Row | Panels | Purpose |
|-----|--------|---------|
| Status at a Glance | GPU slots used/free, active users, containers, system GPU util %, highest temp, SSH sessions | Instant health check |
| GPU Device Metrics | Utilisation, memory %, power (W), temperature per device | Per-GPU deep dive |
| Container & Enforcement | Allocations by user, unmanaged containers, `--gpus all` usage, enforcement events 24h, SSH sessions by user | Access and policy compliance |
| System Health | CPU load average, memory available %, disk usage, scrape target status table | Infrastructure health |

Key indicators:
- **Unmanaged GPU Containers > 0** — containers bypassing DS01 wrapper (red alert)
- **Unrestricted GPU Access > 0** — `--gpus all` usage (dark-red alert)
- **Scrape Targets table** — any DOWN rows need investigation

### DS01 User Detail (`ds01-user`)

Admin tool for inspecting a specific user's GPU usage. Select user from the dropdown at the top.

Shows: current GPU allocations, running containers, GPU utilisation, SSH sessions, GPU-hours (7d/30d), efficiency score, per-container allocation table.

### DS01 Historical (`ds01-historical`)

Long-term trend analysis. Default range: last 7 days.

| Row | What to look for |
|-----|-----------------|
| GPU Utilisation Trends | Hourly avg/max trends, utilisation heatmap (orange = high demand) |
| GPU Cost Attribution | GPU-hours by user (stacked bar), total GPU-hours, efficiency bargauge, GPU-hours over time |
| Capacity & Demand | MIG slot allocation over time, active users over time, GPU waste % trend |
| Temperature & Health | Daily max GPU temp, enforcement activity over time (idle/runtime kills) |

### NVIDIA DCGM GPU Metrics (`nvidia-dcgm`)

Raw NVIDIA DCGM metrics: temperature, power, utilisation, memory, SM clocks, tensor core utilisation.
Use for GPU hardware debugging. Keep as-is — managed upstream by NVIDIA.

---

## 3. Alert Management

### Viewing Active Alerts

- Grafana: **Alerting** tab in left sidebar
- Alertmanager UI: `http://localhost:9093`
- Prometheus alerts: `http://localhost:9090/alerts`

### Alert Delivery

Alerts route to Microsoft Teams via Power Automate webhook (configured in `monitoring/alertmanager/alertmanager.yml`).

Two receivers:
- `ds01-teams` — warning/info alerts (group_wait: 5m, repeat: 4h)
- `ds01-teams-critical` — critical alerts (group_wait: 30s, repeat: 1h)

### Silencing Alerts

Via Alertmanager UI at `http://localhost:9093` → **Silences** → **New Silence**.

Or via CLI (install `amtool` if not present):
```bash
# Silence DS01UserGPUWaste for 4 hours (user on planned downtime)
amtool silence add --alertmanager.url=http://localhost:9093 \
  alertname=DS01UserGPUWaste user=alice \
  --comment="Alice on annual leave" --duration=4h

# List active silences
amtool silence query --alertmanager.url=http://localhost:9093

# Expire a silence by ID
amtool silence expire --alertmanager.url=http://localhost:9093 <silence-id>
```

### Testing Alert Delivery

Send a test alert to verify Teams webhook is working:
```bash
curl -s -X POST http://localhost:9093/api/v2/alerts \
  -H 'Content-Type: application/json' \
  -d '[{
    "labels": {"alertname": "DS01TestAlert", "severity": "warning", "job": "test"},
    "annotations": {"summary": "Test alert", "description": "Manual test from admin"}
  }]'
```

Check Alertmanager UI for delivery status. Alert rules live at:
`monitoring/prometheus/rules/ds01_alerts.yml`

---

## 4. Stack Management

Working directory for all commands: `/opt/ds01-infra/monitoring`

### Restart All Services

```bash
cd /opt/ds01-infra/monitoring && docker compose restart
```

### Restart Single Service

```bash
docker compose restart grafana
docker compose restart prometheus
docker compose restart alertmanager
docker compose restart cadvisor
docker compose restart node-exporter
```

Note: `dcgm-exporter` is managed by systemd (`ds01-dcgm-exporter.service`), not docker-compose restart:
```bash
sudo systemctl restart ds01-dcgm-exporter
```

### View Logs

```bash
docker logs ds01-grafana --tail 50
docker logs ds01-prometheus --tail 50
docker logs ds01-alertmanager --tail 50
docker logs ds01-cadvisor --tail 50
docker logs ds01-node-exporter --tail 50
```

### Check Scrape Targets

```
http://localhost:9090/targets
```

All 7 targets should be UP: dcgm-exporter, ds01-exporter, node-exporter, prometheus, cadvisor, grafana, alertmanager.

`ds01-exporter` runs as a systemd service (not docker):
```bash
sudo systemctl status ds01-exporter
sudo journalctl -u ds01-exporter -n 50
```

### Reload Configuration (without restart)

```bash
# Reload Prometheus config and rules
curl -s -X POST http://localhost:9090/-/reload

# Reload Alertmanager config
curl -s -X POST http://localhost:9093/-/reload
```

Use after editing `prometheus.yml`, `ds01_alerts.yml`, `ds01_recording.yml`, or `alertmanager.yml`.

### Start/Stop Full Stack

```bash
cd /opt/ds01-infra/monitoring
docker compose up -d      # Start all
docker compose down       # Stop all (data preserved in named volumes)
```

---

## 5. Troubleshooting

### Container crash-looping

Check permissions — config files must be readable (644):
```bash
ls -la /opt/ds01-infra/monitoring/prometheus/
ls -la /opt/ds01-infra/monitoring/alertmanager/
ls -la /opt/ds01-infra/monitoring/grafana/provisioning/
# Fix: chmod -R 644 <file>; chmod 755 <dir>
```

View crash logs:
```bash
docker logs ds01-grafana --tail 100
```

### Panel shows "No data"

1. Check the metric exists in Prometheus: `http://localhost:9090/graph`
2. Enter the metric name (e.g., `ds01_gpu_allocated`) and execute
3. If empty — check the relevant scrape target is UP (`/targets`)
4. If DCGM panels are empty — verify `ds01-dcgm-exporter` container is running:
   ```bash
   docker ps | grep dcgm
   sudo systemctl status ds01-dcgm-exporter
   ```

### Alerts not firing

1. Check Prometheus alert state: `http://localhost:9090/alerts`
2. Verify Alertmanager is healthy: `http://localhost:9093/-/healthy`
3. Confirm Teams webhook URL is configured (not placeholder):
   ```bash
   grep PLACEHOLDER /opt/ds01-infra/monitoring/alertmanager/alertmanager.yml
   # Should return nothing if webhook is configured
   ```
4. Check inhibition rules — a critical alert may be suppressing related warnings

### Alerts firing but no Teams message

1. Send a test alert (see section 3)
2. Check Alertmanager logs: `docker logs ds01-alertmanager --tail 50`
3. Verify Power Automate webhook URL is still valid (they expire)

### High disk usage from Prometheus

Check volume sizes:
```bash
du -sh /var/lib/docker/volumes/ds01-prometheus-data/
df -h /
```

Prometheus retention: 90 days / 15GB cap (whichever comes first).
If disk is critical, restart Prometheus with a lower retention:
```bash
# Edit docker-compose.yaml to reduce --storage.tsdb.retention.time=30d
cd /opt/ds01-infra/monitoring && docker compose up -d prometheus
```

### ds01-exporter not scraped

```bash
sudo systemctl status ds01-exporter
curl -s http://127.0.0.1:9101/metrics | head -20
sudo journalctl -u ds01-exporter -n 50
```

---

## 6. Configuration File Reference

All monitoring config lives in `/opt/ds01-infra/monitoring/`.

| File | Purpose |
|------|---------|
| `docker-compose.yaml` | Service definitions, image versions, resource limits, volume mounts |
| `prometheus/prometheus.yml` | Scrape targets, intervals, alertmanager endpoint |
| `prometheus/rules/ds01_alerts.yml` | Alert rules (24 rules across 5 groups) |
| `prometheus/rules/ds01_recording.yml` | Recording rules — pre-computed aggregates (10 groups, ~45 rules) |
| `alertmanager/alertmanager.yml` | Alert routing, inhibition rules, Teams webhook receivers |
| `grafana/provisioning/datasources/` | Prometheus datasource auto-provisioning |
| `grafana/provisioning/dashboards/` | Dashboard auto-provisioning config |
| `grafana/provisioning/dashboards/dashboards/` | Dashboard JSON files (ds01_overview, ds01_historical, ds01_user, nvidia_dcgm) |

After editing any config file, reload the relevant service (see section 4). For docker-compose changes, run `docker compose up -d`.

---

## 7. Key Metrics Reference

| Metric | Source | Description |
|--------|--------|-------------|
| `ds01_gpu_allocated` | ds01-exporter | Per-slot GPU allocation (labels: gpu_slot, user, container) |
| `ds01_ssh_sessions_active` | ds01-exporter | SSH sessions per user (from `who`) |
| `ds01_lifecycle_events_total` | ds01-exporter | Enforcement events last 24h (label: action) |
| `ds01:system_gpu_utilization_avg` | recording rule | System-wide GPU utilisation avg (0–1 scale) |
| `ds01:user_gpu_seconds` | recording rule | Proxy counter for GPU-hours attribution |
| `DCGM_FI_DEV_GPU_TEMP` | dcgm-exporter | Per-GPU temperature (°C) |
| `DCGM_FI_PROF_GR_ENGINE_ACTIVE` | dcgm-exporter | MIG GPU utilisation (0–1 scale) |
| `container_cpu_usage_seconds_total` | cAdvisor | Per-container CPU usage |
| `container_memory_usage_bytes` | cAdvisor | Per-container memory usage |
| `node_load15` | node-exporter | System 15-minute load average |
