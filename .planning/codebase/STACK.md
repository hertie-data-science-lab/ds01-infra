# Technology Stack

**Analysis Date:** 2026-01-26

## Languages

**Primary:**
- Python 3.10+ - Core GPU allocation logic, monitoring exporters, resource configuration parsing
- Bash/Shell - CLI commands, deployment scripts, container orchestration wrappers
- YAML - Configuration files (resource limits, Prometheus, Grafana provisioning)

**Secondary:**
- JSON - Docker labels, event logging, GPU state serialization
- SQL - Grafana backend (SQLite via docker-compose)
- Rego - OPA authorization policies for Docker authz plugin

## Runtime

**Environment:**
- Ubuntu 22.04 (implied by docker-compose DCGM image pinning)
- systemd (cgroup management via ds01.slice hierarchy)
- Docker with NVIDIA Container Toolkit

**Package Manager:**
- pip (Python dependencies)
- No lock files observed (Python deps declared in requirements.txt only)

## Frameworks

**Core:**
- Docker/Docker Compose - Container orchestration and monitoring stack deployment
- AIME ML Containers (mlc) - Base image management (patched with custom --image flag at `scripts/docker/mlc-patched.py`)

**Monitoring & Metrics:**
- Prometheus v2.48.0 - Time-series metrics database, alert evaluation
- Grafana v10.2.0 - Dashboard visualization and UI
- NVIDIA DCGM Exporter v3.3.0 - GPU hardware metrics (utilization, memory, temperature, power)
- Node Exporter v1.7.0 - System metrics (CPU, memory, disk, network)
- Alertmanager v0.26.0 - Alert routing and email notifications

**Configuration Management:**
- PyYAML - YAML parsing for resource limits and exporter configuration

**Testing:**
- No formal test framework detected. Testing scripts in `testing/` directory but no pytest/unittest infrastructure observed.

**Build/Dev:**
- commitizen - Semantic versioning and changelog generation
- Ruff - Python linting/formatting (100 char line length, target py310)

## Key Dependencies

**Critical:**
- PyYAML >=6.0 - Required for `get_resource_limits.py`, `gpu_allocator_v2.py`, and DS01 exporter
- Docker - Core runtime for all container operations and monitoring stack
- nvidia-smi - GPU state querying (via subprocess in allocation logic)
- NVIDIA Container Toolkit - GPU device mapping to containers

**Infrastructure:**
- prometheus-client >=0.19.0 - Prometheus metrics exposition (optional, used in monitoring/requirements.txt)
- pytorch or cupy - Optional GPU stress testing (not auto-installed, user manually installs if needed)

## Configuration

**Environment Variables:**
- `DS01_EXPORTER_PORT` (default 9101) - DS01 exporter HTTP port
- `DS01_EXPORTER_BIND` (default 127.0.0.1) - DS01 exporter bind address
- `DCGM_EXPORTER_URL` (default http://127.0.0.1:9400/metrics) - DCGM metrics endpoint
- `GRAFANA_ADMIN_USER` (default admin) - Grafana admin username
- `GRAFANA_ADMIN_PASSWORD` (default ds01admin) - Grafana admin password
- `GRAFANA_ROOT_URL` (default http://localhost:3000) - Grafana root URL
- `SMTP_AUTH_USER` / `SMTP_AUTH_PASSWORD` - Email alert credentials (Alertmanager)

**Configuration Files:**
- `/opt/ds01-infra/config/resource-limits.yaml` - Central resource configuration (GPU limits, groups, defaults)
- `/opt/ds01-infra/monitoring/prometheus/prometheus.yml` - Prometheus scrape configuration
- `/opt/ds01-infra/monitoring/docker-compose.yaml` - Monitoring stack services
- `/opt/ds01-infra/monitoring/alertmanager/alertmanager.yml` - Alert routing rules
- `/opt/ds01-infra/monitoring/grafana/provisioning/` - Dashboard and datasource auto-provisioning

## Platform Requirements

**Development:**
- Python 3.10+
- Docker with docker-compose (v2+)
- NVIDIA GPU with driver and NVIDIA Container Toolkit
- systemd for service management
- bash shell (POSIX-compatible scripts)

**Production:**
- Ubuntu 22.04+ or compatible Linux
- NVIDIA CUDA-capable GPU (A100/H100 implicit from DCGM integration)
- NVIDIA Container Toolkit installed
- systemd enabled for cgroup slice management
- Disk space: ~20GB for Prometheus time-series retention (7 days)

**Monitoring Stack Deployment:**
- Binds to localhost only (127.0.0.1) by default
- Uses Docker bridge network (ds01-monitoring)
- Requires host.docker.internal for Prometheus→DS01 exporter communication
- Named volumes for persistence: prometheus-data, alertmanager-data, grafana-data

---

*Stack analysis: 2026-01-26*
