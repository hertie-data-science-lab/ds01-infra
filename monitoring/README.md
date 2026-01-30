# DS01 Monitoring Stack

Prometheus/Grafana monitoring for DS01 GPU infrastructure with NVIDIA DCGM integration.

## Quick Start

```bash
# 1. Start the DS01 exporter (runs as systemd service)
sudo cp /opt/ds01-infra/config/deploy/systemd/ds01-exporter.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ds01-exporter

# 2. Start the monitoring stack (Prometheus, Grafana, Node Exporter, DCGM Exporter)
monitoring-manage start

# 3. Check status
monitoring-manage status

# 4. Access Grafana (via SSH tunnel)
ssh -L 3000:localhost:3000 user@ds01-server
# Then open http://localhost:3000 in browser
```

## Optional: GPU Stress Testing Tools

The monitoring stack includes GPU stress testing tools for dashboard validation. These require **optional Python dependencies** (PyTorch or CuPy) that are **NOT** required for core DS01 functionality.

To use stress testing tools:
```bash
# Install PyTorch for GPU compute (most common)
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cu121

# Or see monitoring/requirements.txt for other options
```

**Note:** These tools never auto-install dependencies. If you try to run them without PyTorch/CuPy, they'll provide clear installation instructions and exit. This design ensures DS01 remains lightweight and doesn't force users to install heavy ML libraries unless explicitly needed.

## Architecture

DS01 uses a **hybrid exporter architecture** for efficient GPU monitoring:

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    DS01 MONITORING STACK (DCGM Hybrid)                       │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│   ┌─────────────────┐     ┌─────────────────┐                               │
│   │  DCGM Exporter  │     │  DS01 Exporter  │                               │
│   │   :9400 (Docker)│     │ :9101 (systemd) │                               │
│   │                 │     │                 │                               │
│   │ GPU HARDWARE    │     │ DS01 BUSINESS   │                               │
│   │ • Utilization   │     │ • Allocations   │                               │
│   │ • Memory        │     │ • User→GPU map  │                               │
│   │ • Temperature   │     │ • Interfaces    │                               │
│   │ • Power         │     │ • Events        │                               │
│   │ • Clocks        │     │ • MIG-equiv     │                               │
│   │ • MIG metrics   │     │                 │                               │
│   │                 │     │                 │                               │
│   │ <1s scrape      │     │ ~1s scrape      │                               │
│   └────────┬────────┘     └────────┬────────┘                               │
│            │                       │                                         │
│            └───────────┬───────────┘                                         │
│                        ▼                                                     │
│   ┌─────────────────┐     ┌─────────────────┐                               │
│   │  Node Exporter  │     │    Prometheus   │                               │
│   │   :9100 (Docker)│────►│   :9090 (Docker)│                               │
│   │                 │     │                 │                               │
│   │ • CPU/Memory    │     │ • Scrapes all   │                               │
│   │ • Disk/Network  │     │ • 7-day retain  │                               │
│   │ • Systemd       │     │ • Alert rules   │                               │
│   └─────────────────┘     └────────┬────────┘                               │
│                                    │                                         │
│                   ┌────────────────┼────────────────┐                       │
│                   │                ▼                │                       │
│           ┌───────┴───────┐   ┌────────────┐       │                       │
│           │ Alertmanager  │   │  Grafana   │       │                       │
│           │   :9093       │   │  :3000     │       │                       │
│           │               │   │            │       │                       │
│           │ • Routing     │   │ • Overview │       │                       │
│           │ • Silencing   │   │ • My Usage │       │                       │
│           └───────────────┘   │ • DCGM GPU │       │                       │
│                               └────────────┘       │                       │
│                                                     │                       │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Why Hybrid Architecture?

**Before (v1):** DS01 Exporter collected all metrics via nvidia-smi subprocess calls.
- Problem: nvidia-smi parsing took 15-20 seconds per scrape
- Problem: High CPU overhead, scrape timeouts

**After (v2):** Hybrid DCGM + DS01 approach.
- **DCGM Exporter**: Native NVIDIA driver integration for hardware metrics (sub-second)
- **DS01 Exporter**: Slimmed down to allocation/business metrics only (~1s)
- Result: Fast, reliable metrics without scrape timeouts

## Components

| Component | Port | Deployment | Purpose |
|-----------|------|------------|---------|
| **DCGM Exporter** | 9400 | Docker | GPU hardware metrics (utilization, memory, temp, power) |
| **DS01 Exporter** | 9101 | systemd | DS01 allocation/business metrics |
| Node Exporter | 9100 | Docker | System metrics (CPU, memory, disk) |
| Prometheus | 9090 | Docker | Time-series DB + alerting |
| Alertmanager | 9093 | Docker | Alert routing |
| Grafana | 3000 | Docker | Dashboards |

**Deployment Notes:**
- **DCGM Exporter** runs in Docker with `--gpus all` and `CAP_SYS_ADMIN` for driver access
- **DS01 Exporter** runs as systemd service to access `/var/lib/ds01` state files

## Metrics Reference

### DCGM Exporter Metrics (GPU Hardware)

DCGM provides comprehensive GPU metrics with `DCGM_FI_*` prefix:

```
# Utilization
DCGM_FI_DEV_GPU_UTIL{gpu="0"}           # GPU compute utilization %
DCGM_FI_DEV_MEM_COPY_UTIL{gpu="0"}      # Memory bandwidth utilization %

# Memory
DCGM_FI_DEV_FB_USED{gpu="0"}            # Framebuffer memory used (MB)
DCGM_FI_DEV_FB_FREE{gpu="0"}            # Framebuffer memory free (MB)

# Temperature & Power
DCGM_FI_DEV_GPU_TEMP{gpu="0"}           # GPU temperature (C)
DCGM_FI_DEV_POWER_USAGE{gpu="0"}        # Power draw (W)
DCGM_FI_DEV_TOTAL_ENERGY_CONSUMPTION{gpu="0"}  # Total energy (mJ)

# Clocks
DCGM_FI_DEV_SM_CLOCK{gpu="0"}           # SM clock (MHz)
DCGM_FI_DEV_MEM_CLOCK{gpu="0"}          # Memory clock (MHz)

# PCIe
DCGM_FI_DEV_PCIE_TX_THROUGHPUT{gpu="0"} # PCIe TX (KB/s)
DCGM_FI_DEV_PCIE_RX_THROUGHPUT{gpu="0"} # PCIe RX (KB/s)

# Errors
DCGM_FI_DEV_ECC_SBE_VOL_TOTAL{gpu="0"}  # Single-bit ECC errors
DCGM_FI_DEV_ECC_DBE_VOL_TOTAL{gpu="0"}  # Double-bit ECC errors
DCGM_FI_DEV_XID_ERRORS{gpu="0"}         # XID errors

# MIG (if enabled)
DCGM_FI_PROF_GR_ENGINE_ACTIVE{gpu="0",GPU_I_ID="0"}  # MIG instance utilization
```

### DS01 Exporter Metrics (Allocations)

DS01 exporter provides allocation and business metrics:

```
# Allocation tracking
ds01_gpu_allocated{gpu_slot="1.0",container="thesis",user="alice",interface="orchestration"} 1

# Containers by interface
ds01_containers_total{status="running",interface="orchestration"} 5
ds01_containers_total{status="stopped",interface="atomic"} 2

# User-level metrics
ds01_user_mig_allocated{user="alice"}     # MIG-equivalents allocated
ds01_user_containers_count{user="alice"}  # Container count

# Event counts (24h window)
ds01_events_24h_total{event_type="gpu.allocated"} 12
ds01_events_24h_total{event_type="container.started"} 8

# System metrics
ds01_state_disk_bytes{type="used"}        # DS01 state directory usage

# Exporter info
ds01_exporter_info{version="2.0.0",type="slim"} 1
```

### Metric Mapping (Old → New)

If migrating from v1 dashboards, use these equivalents:

| Old DS01 Metric | New Source | DCGM Equivalent |
|-----------------|------------|-----------------|
| `ds01_gpu_utilization_percent{gpu="0"}` | DCGM | `DCGM_FI_DEV_GPU_UTIL{gpu="0"}` |
| `ds01_gpu_temperature_celsius{gpu="0"}` | DCGM | `DCGM_FI_DEV_GPU_TEMP{gpu="0"}` |
| `ds01_gpu_memory_used_bytes{gpu="0"}` | DCGM | `DCGM_FI_DEV_FB_USED{gpu="0"} * 1024 * 1024` |
| `ds01_gpu_memory_total_bytes{gpu="0"}` | DCGM | `DCGM_FI_DEV_FB_FREE + DCGM_FI_DEV_FB_USED` (MB) |
| `ds01_mig_utilization_percent{slot="X.Y"}` | DCGM | `DCGM_FI_PROF_GR_ENGINE_ACTIVE{GPU_I_ID="Y"}` |
| `ds01_gpu_allocated{...}` | DS01 | (unchanged) |
| `ds01_containers_total{...}` | DS01 | (unchanged) |
| `ds01_user_*` | DS01 | (unchanged) |

## Alert Rules

Pre-configured alerts in `prometheus/rules/ds01_alerts.yml`:

| Alert | Severity | Condition |
|-------|----------|-----------|
| DS01GPUWaste | warning | Physical GPU allocated but <5% util for 30m |
| DS01MIGWaste | warning | MIG instance allocated but <5% util for 30m |
| DS01GPUHighTemperature | warning | GPU temp >85C for 5m |
| DS01GPUCriticalTemperature | critical | GPU temp >90C for 2m |
| DS01GPUMemoryHigh | warning | GPU memory >95% for 10m |
| DS01ContainerHighMemory | warning | Container >90% memory limit |
| DS01ExporterDown | critical | Exporter unreachable for 2m |
| DS01DCGMExporterDown | critical | DCGM exporter unreachable for 2m |
| DS01DiskSpaceLow | warning | <10% disk free |

## Grafana Dashboards

Three pre-provisioned dashboards:

### 1. DS01 Overview (`/d/ds01-overview`)
System health and resource allocation at a glance.
- **GPU Stats**: Total GPUs, average utilization, max temperature
- **MIG Status**: Total instances, allocated, free
- **GPU Metrics**: Utilization and memory time series (from DCGM)
- **Temperature**: GPU temperature over time
- **Allocations**: Current GPU→user→container mapping table
- **Containers**: By interface pie chart (orchestration, atomic, other)

### 2. DS01 My Usage (`/d/ds01-user`)
Personal dashboard for researchers.
- **User Selector**: Dropdown to filter by username
- **My Resources**: MIG allocation count, container count
- **My GPU Utilization**: Average utilization across allocated GPUs
- **My Allocations**: Table of my GPU assignments
- **My GPU History**: Utilization over time for my allocations
- **Container Stats**: CPU/memory usage per container

### 3. NVIDIA DCGM GPU Metrics (`/d/nvidia-dcgm`)
Detailed GPU hardware metrics from DCGM.
- **GPU Overview**: Utilization, memory, temperature stat panels
- **Power & Energy**: Power draw, total energy consumption
- **Clocks**: SM and memory clock frequencies
- **PCIe**: TX/RX throughput
- **Errors**: ECC errors, XID errors
- **Per-GPU Breakdown**: All metrics per physical GPU
- **MIG Metrics**: Per-instance utilization (if MIG enabled)

## Admin Commands

```bash
monitoring-manage status    # Show stack status
monitoring-manage start     # Start all services
monitoring-manage stop      # Stop all services
monitoring-manage restart   # Restart all services
monitoring-manage logs      # Follow all logs
monitoring-manage logs grafana  # Follow specific service
monitoring-manage update    # Pull latest images & restart
monitoring-manage build     # Rebuild exporter image

monitoring-status           # Quick health check
monitoring-status --quiet   # Exit 0 if healthy, 1 if not
```

## Configuration

### Environment Variables (docker-compose)

```bash
GRAFANA_ADMIN_USER=admin           # Grafana admin username
GRAFANA_ADMIN_PASSWORD=ds01admin   # Grafana admin password (CHANGE THIS)
GRAFANA_ROOT_URL=http://localhost:3000
```

### Prometheus Settings

- **Retention**: 7 days
- **Max size**: 20GB
- **Scrape intervals**:
  - DCGM Exporter: 15s
  - DS01 Exporter: 30s
  - Node Exporter: 15s

### Alertmanager

#### Configuring Email Alerts (Hertie SMTP)

1. Edit `alertmanager/alertmanager.yml`:
   ```yaml
   global:
     smtp_smarthost: 'smtp.hertie-school.org:587'
     smtp_from: 'ds01-alerts@hertie-school.org'
     smtp_auth_username: 'ds01-alerts@hertie-school.org'
     smtp_auth_password: 'YOUR_PASSWORD_HERE'  # Add your password
     smtp_require_tls: true
   ```

2. Restart alertmanager:
   ```bash
   monitoring-manage restart
   ```

3. Test alerts:
   ```bash
   # View active alerts
   curl -s http://localhost:9093/api/v2/alerts | jq

   # Send test alert
   curl -XPOST http://localhost:9093/api/v2/alerts \
     -H "Content-Type: application/json" \
     -d '[{"labels":{"alertname":"TestAlert","severity":"warning"}}]'
   ```

#### Alert Routing

- **Critical** (severity=critical): Immediate email, repeat every 1h
- **Warning** (severity=warning): Email, repeat every 4h
- **Info** (severity=info): Email, repeat every 24h

Edit `alertmanager/alertmanager.yml` to customise routing, add Slack webhooks, etc.

## Security

All services bind to **localhost only** by default:

- Prometheus: `127.0.0.1:9090`
- Alertmanager: `127.0.0.1:9093`
- Grafana: `127.0.0.1:3000`
- DCGM Exporter: `127.0.0.1:9400`
- DS01 Exporter: `0.0.0.0:9101` (bound to all interfaces for Docker access)
- Node Exporter: `127.0.0.1:9100`

### Accessing Grafana

Use SSH tunnel:
```bash
ssh -L 3000:localhost:3000 user@ds01-server
```

Or configure reverse proxy (nginx) with authentication.

### Grafana Password

**Change the default password** after first login:
1. Login with `admin` / `ds01admin`
2. Go to Profile → Change Password

Or set via environment variable before starting.

## Troubleshooting

### DCGM Exporter Issues

```bash
# Check if DCGM exporter is running
docker ps | grep dcgm

# Check DCGM exporter logs
docker logs ds01-dcgm-exporter

# Test DCGM metrics endpoint
curl http://localhost:9400/metrics | head -50

# Common issues:
# 1. "DCGM initialization error" - GPU driver mismatch
#    Solution: Ensure nvidia-driver and DCGM versions are compatible
#
# 2. "No GPUs found" - Container can't see GPUs
#    Solution: Check docker-compose has deploy.resources.reservations.devices
#
# 3. Permission denied
#    Solution: Ensure CAP_SYS_ADMIN capability in docker-compose
```

### DS01 Exporter Issues

```bash
# Check if DS01 exporter is running
sudo systemctl status ds01-exporter

# Check exporter logs
sudo journalctl -u ds01-exporter -f

# Test metrics endpoint
curl http://localhost:9101/metrics | grep ds01_

# Common issues:
# 1. "Connection refused" from Prometheus
#    Solution: Ensure exporter binds to 0.0.0.0 (not 127.0.0.1) for Docker access
#    Check: DS01_EXPORTER_BIND=0.0.0.0 in service file
#
# 2. "Module not found" errors
#    Solution: Check /opt/ds01-infra paths exist and are readable
#
# 3. Empty allocation metrics
#    Solution: Check /var/lib/ds01/gpu-state.json exists

# Reinstall service if needed:
sudo cp /opt/ds01-infra/config/deploy/systemd/ds01-exporter.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl restart ds01-exporter
```

### Prometheus Targets Down

```bash
# Check Prometheus targets page
curl http://localhost:9090/api/v1/targets | jq '.data.activeTargets[] | {job: .labels.job, health: .health}'

# Check container networking
docker network inspect ds01-monitoring

# Verify host.docker.internal resolves (for DS01 exporter)
docker exec ds01-prometheus ping -c 1 host.docker.internal
```

### Grafana Dashboard Issues

```bash
# Check provisioning logs
docker logs ds01-grafana 2>&1 | grep -i provision

# Verify dashboard files exist
ls -la /opt/ds01-infra/monitoring/grafana/provisioning/dashboards/dashboards/

# Check for JSON syntax errors
python3 -m json.tool monitoring/grafana/provisioning/dashboards/dashboards/ds01_overview.json > /dev/null

# Force dashboard refresh
docker restart ds01-grafana
```

### No GPU Metrics in Grafana

1. **Check DCGM exporter first**:
   ```bash
   curl http://localhost:9400/metrics | grep DCGM_FI_DEV_GPU_UTIL
   ```

2. **Check Prometheus is scraping DCGM**:
   ```bash
   curl 'http://localhost:9090/api/v1/query?query=DCGM_FI_DEV_GPU_UTIL' | jq
   ```

3. **Check dashboard queries**: Ensure dashboards use `DCGM_FI_*` metrics, not old `ds01_gpu_*` metrics

### Performance Issues

If Prometheus is slow or using too much memory:

```bash
# Check Prometheus memory usage
docker stats ds01-prometheus

# Reduce retention if needed (edit docker-compose.yaml):
# --storage.tsdb.retention.time=3d  (instead of 7d)

# Check cardinality
curl 'http://localhost:9090/api/v1/status/tsdb' | jq '.data.seriesCountByMetricName[:10]'
```

## File Structure

```
monitoring/
├── docker-compose.yaml          # Main compose file (Prometheus, Grafana, DCGM, Node)
├── README.md                    # This file
├── exporter/
│   └── ds01_exporter.py        # Custom metrics exporter v2 (slim, allocation-only)
├── prometheus/
│   ├── prometheus.yml          # Scrape configuration (DCGM + DS01 + Node)
│   └── rules/
│       └── ds01_alerts.yml     # Alert rules
├── alertmanager/
│   └── alertmanager.yml        # Alert routing
└── grafana/
    └── provisioning/
        ├── datasources/
        │   └── prometheus.yml  # Auto-configure Prometheus
        └── dashboards/
            ├── default.yml     # Dashboard provider
            └── dashboards/
                ├── ds01_overview.json  # System overview (DCGM + DS01)
                ├── ds01_user.json      # Per-user dashboard
                └── nvidia_dcgm.json    # Detailed GPU hardware metrics

config/deploy/systemd/
└── ds01-exporter.service        # Systemd unit for DS01 exporter
```

## Upgrading from v1

If upgrading from the original single-exporter architecture:

1. **Update DS01 exporter service**:
   ```bash
   sudo cp /opt/ds01-infra/config/deploy/systemd/ds01-exporter.service /etc/systemd/system/
   sudo systemctl daemon-reload
   sudo systemctl restart ds01-exporter
   ```

2. **Restart monitoring stack** (pulls DCGM exporter):
   ```bash
   cd /opt/ds01-infra/monitoring
   docker-compose pull
   docker-compose up -d
   ```

3. **Dashboards auto-update** via Grafana provisioning on restart

4. **Verify all targets healthy**:
   ```bash
   monitoring-status
   ```
