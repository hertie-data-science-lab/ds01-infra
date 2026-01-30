# External Integrations

**Analysis Date:** 2026-01-26

## APIs & External Services

**Docker:**
- SDK/Client: `docker` CLI (called via subprocess in Python/Bash scripts)
- Integration points: GPU allocation, container lifecycle management, label inspection
- Authentication: Unix socket at `/var/run/docker.sock` (group access via docker group)

**NVIDIA APIs:**
- nvidia-smi - GPU state querying (subprocess calls for allocation logic)
- NVIDIA DCGM (Data Center GPU Manager) - Native driver integration for metrics

**AIME ML Containers:**
- mlc-patched.py (wrapper at `scripts/docker/mlc-patched.py`)
- Integration: Custom --image flag extension for bypass of AIME catalog
- Location: `/opt/aime-ml-containers` (external mount reference in CLAUDE.md)

## Data Storage

**Databases:**
- None detected - No relational database integration
- Prometheus TSDB - Time-series metrics (embedded, persistent via Docker volume)
- Grafana SQLite - Dashboard configuration and user data (embedded, persistent)

**File Storage:**
- Local filesystem only - `/var/lib/ds01/` for GPU state and container metadata
- `/var/log/ds01/` for centralized event logs and allocation history
- Docker volumes: `prometheus-data`, `alertmanager-data`, `grafana-data`

**State Files:**
- `/var/lib/ds01/gpu-state.json` - Current GPU allocations (JSON)
- `/var/lib/ds01/container-metadata/` - Per-container metadata
- `/var/log/ds01/events.jsonl` - Centralized event log (JSON lines format)
- `/opt/ds01-infra/config/resource-limits.yaml` - Resource configuration (YAML)

**Caching:**
- None detected - No external cache service

## Authentication & Identity

**System Authentication:**
- Unix user/group - System-level user identity from `/etc/passwd`
- Domain usernames - Support for user@domain format in resource limits
- Username sanitization - Handled by `scripts/lib/username_utils.py` for systemd slice names

**Docker Authorization:**
- OPA Docker Authz Plugin - Policy enforcement at `config/deploy/opa/docker-authz.rego`
- Labels-based access control - `ds01.user` label matching on containers

**Monitoring Access:**
- Grafana: Local admin user (default admin/ds01admin)
- Prometheus: No authentication (localhost only)
- DCGM Exporter: No authentication (localhost only)

## Monitoring & Observability

**Metrics Exposure:**
- Prometheus metrics format (text-based) on HTTP endpoints
- DCGM Exporter: Port 9400 (`DCGM_FI_*` metrics)
- DS01 Exporter: Port 9101 (custom `ds01_*` metrics)
- Node Exporter: Port 9100 (system metrics)

**Error Tracking:**
- Application errors logged to `/var/log/ds01/` (JSON lines)
- Event logger at `scripts/docker/event-logger.py` for append-only event log

**Logs:**
- Docker-compose logging: json-file driver (10-50MB per service)
- systemd journal: DS01 exporter service logs via journalctl
- Centralized logs: `/var/log/ds01/events.jsonl` (container lifecycle, GPU allocation events)

## CI/CD & Deployment

**Hosting:**
- On-premises GPU server (no cloud deployment detected)
- Docker containers for monitoring stack (Prometheus, Grafana, exporters)

**CI Pipeline:**
- Git-based versioning with commitizen (conventional commits)
- No GitHub Actions / GitLab CI detected
- Manual deployment via scripts in `scripts/system/deploy-commands.sh`

**Deployment Tools:**
- Systemd services for daemon management:
  - `ds01-exporter.service` - Custom metrics exporter
  - `ds01-container-owner-tracker.service` - Container ownership tracking
  - `opa-docker-authz.service` - OPA authorization plugin
- Cron jobs (defined in `config/deploy/cron.d/ds01-maintenance`):
  - Hourly cleanup jobs (GPU release, container removal, idle detection)
- Docker-compose for monitoring stack (`monitoring/docker-compose.yaml`)

## Environment Configuration

**Required Environment Variables:**
- `DS01_EXPORTER_PORT` - Custom exporter HTTP port (default 9101)
- `DS01_EXPORTER_BIND` - Custom exporter bind address (default 127.0.0.1)
- `DCGM_EXPORTER_URL` - DCGM metrics endpoint (default http://127.0.0.1:9400/metrics)
- `GRAFANA_ADMIN_USER` - Admin username (default admin)
- `GRAFANA_ADMIN_PASSWORD` - Admin password (default ds01admin, MUST change in production)

**Secrets Location:**
- Environment variables in systemd service files (see `config/deploy/systemd/`)
- `.env` file for docker-compose (for Grafana, Alertmanager credentials)
- SMTP credentials for Alertmanager: `SMTP_AUTH_USER`, `SMTP_AUTH_PASSWORD`
- None committed to git (follow security practices)

**Configuration Sources:**
- `config/resource-limits.yaml` - Central resource policy
- `config/groups/*.members` - Group membership (one file per group)
- `config/user-overrides.yaml` - Per-user exceptions
- `monitoring/prometheus/rules/*.yml` - Alert rules

## Webhooks & Callbacks

**Incoming Webhooks:**
- None detected - No external webhook consumers

**Outgoing Webhooks:**
- Alertmanager SMTP - Email notifications on alerts
  - Configured in `monitoring/alertmanager/alertmanager.yml`
  - Supports Slack webhooks (configurable, not pre-configured)
  - Email routes by severity: critical (1h repeat), warning (4h repeat), info (24h repeat)

**Event Publishing:**
- Event logger at `scripts/docker/event-logger.py` appends to `/var/log/ds01/events.jsonl`
- Events include: GPU allocated, container started, container stopped, GPU released

## Docker Wrapper Integration

**Universal Docker Intercept:**
- `/usr/local/bin/docker` wrapper intercepts all docker CLI commands
- Injects cgroup-parent for resource enforcement: `--cgroup-parent=ds01-{group}-{user}.slice`
- GPU allocation via `gpu_allocator_v2.py allocate-external` when `--gpus` detected
- Labels applied automatically: `ds01.user`, `ds01.managed`, `ds01.container_type`

**Container Type Detection:**
- `devcontainer.*` labels → devcontainer (IDE remote)
- `com.docker.compose.*` labels → compose (docker-compose)
- Ownership extraction from `devcontainer.local_folder` path if needed
- Fallback → docker (CLI creation)

## Resource Enforcement

**GPU Allocation:**
- Stateless allocation via `gpu_allocator_v2.py` (reads state from Docker labels)
- File-locked updates to prevent race conditions
- MIG support: Tracks as `physical_gpu:instance` (e.g., `"0:0"`, `"0:1"`)
- Per-user limits from `resource-limits.yaml` (merges defaults + group + user-overrides)

**Cgroup Enforcement:**
- systemd hierarchy: `ds01.slice` → `ds01-{group}.slice` → `ds01-{group}-{user}.slice`
- CPU, memory, and task limits enforced via cgroup policies
- Applied at container creation via docker-wrapper

**GPU Hold After Stop:**
- Grace period before GPU release (configurable via `gpu_hold_after_stop`)
- Prevents rapid re-allocation churn
- Default: 15 minutes for students, configurable per group

---

*Integration audit: 2026-01-26*
