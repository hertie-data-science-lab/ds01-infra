# scripts/monitoring/CLAUDE.md

Metrics collection, health checks, and monitoring tools.

## Key Files

| File | Purpose |
|------|---------|
| `gpu-utilization-monitor.py` | Real-time GPU usage tracking |
| `mig-utilization-monitor.py` | MIG instance utilisation |
| `ds01-events` | Query centralised event log |
| `ds01-health-check` | Full system health check |
| `container-dashboard.sh` | Container resource dashboard |
| `gpu-status-dashboard.py` | GPU allocation dashboard |
| `detect-bare-metal.py` | Detect processes running on bare metal |
| `collect-*-metrics.sh` | Metric collection scripts (cron) |
| `audit-*.sh` | System audit scripts |

## Common Operations

```bash
# GPU monitoring
gpu-utilization-monitor              # Current snapshot
gpu-utilization-monitor --json       # JSON output
mig-utilization-monitor              # MIG instance utilisation

# Health checks
ds01-health-check                    # Full health check

# Event log
ds01-events                          # View all events
ds01-events user alice               # Events for specific user
ds01-events --since "1 hour ago"     # Recent events

# Audits
audit-system.sh                      # System audit
audit-docker.sh                      # Docker audit
audit-container.sh <name>            # Single container audit
```

## Metric Collection (Cron)

Scheduled every 5 minutes (`*/5 * * * *`):
- `collect-gpu-metrics.sh` → `/var/log/ds01-infra/metrics/gpu/`
- `collect-cpu-metrics.sh` → `/var/log/ds01-infra/metrics/cpu/`
- `collect-memory-metrics.sh` → `/var/log/ds01-infra/metrics/memory/`
- `collect-disk-metrics.sh` → `/var/log/ds01-infra/metrics/disk/`
- `collect-container-metrics.sh` → `/var/log/ds01-infra/metrics/container/`

## Monitoring Stack

Current deployment (hybrid architecture):
- **DS01 Exporter**: systemd service (`ds01-exporter.service`)
- **Prometheus**: Docker container (`ds01-prometheus`)
- **Grafana**: Docker container (`ds01-grafana`)
- **Node Exporter**: Docker container (`ds01-node-exporter`)
- **DCGM Exporter**: Docker container (`ds01-dcgm-exporter`)

## Log Locations

| Log | Path |
|-----|------|
| Event log | `/var/log/ds01/events.jsonl` |
| GPU allocations | `/var/log/ds01/gpu-allocations.log` |
| Cron logs | `/var/log/ds01/cron.log` |
| Metrics | `/var/log/ds01-infra/metrics/` |

---

**Parent:** [/CLAUDE.md](../../CLAUDE.md) | **Related:** [README.md](README.md)
