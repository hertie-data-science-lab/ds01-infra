# CLAUDE.md

AI assistant instructions for DS01 Infrastructure.

## Quick Reference

**What is DS01?** Multi-user GPU container management built on AIME ML Containers.

**Key paths:**
- Config: `config/resource-limits.yaml`
- Scripts: `scripts/{docker,user,admin,lib,system,monitoring,maintenance}/`
- State: `/var/lib/ds01/` | Logs: `/var/log/ds01/`

**Common operations:**
```bash
sudo deploy                                    # Deploy commands to /usr/local/bin
python3 scripts/docker/get_resource_limits.py <user>  # Check user limits
python3 scripts/docker/gpu_allocator.py status        # GPU allocation state
dashboard                                      # System overview
monitoring-manage status                       # Prometheus/Grafana stack status
```

## Guidelines

- Be concise, update docs when changing implementation
- Use [Conventional Commits](https://www.conventionalcommits.org/) - commits without type prefixes rejected
- Store tests in `/testing` directory
- See `ds01-UI_UX_GUIDE.md` for CLI design standards

## Architecture Overview

**5-layer hierarchy:**
```
L4: Wizards        → user-setup, project-init, project-launch
L3: Orchestrators  → container deploy, container retire
L2: Atomic         → container-*, image-*
L1: MLC (hidden)   → mlc-patched.py
L0: Docker         → Foundation
```

**Universal enforcement:** All containers subject to:
- Systemd cgroups (`ds01.slice` hierarchy)
- Docker wrapper (`/usr/local/bin/docker`) for slice injection
- GPU allocation tracking via Docker labels

## Directory Index

Each directory has detailed CLAUDE.md/README.md. Read the relevant one for your task:

| Directory | Purpose | Key Files |
|-----------|---------|-----------|
| `scripts/docker/` | GPU allocation, container creation | `gpu_allocator_v2.py`, `mlc-patched.py`, `docker-wrapper.sh` |
| `scripts/user/` | User commands (L2-L4) | `atomic/`, `orchestrators/`, `wizards/` |
| `scripts/admin/` | Admin tools, dashboards | `dashboard`, `ds01-logs`, `ds01-users` |
| `scripts/lib/` | Shared bash/Python libraries | `init.sh`, `ds01_core.py` |
| `scripts/system/` | System administration | `deploy-commands.sh`, `add-user-to-docker.sh` |
| `scripts/monitoring/` | Metrics, health checks | `gpu-utilization-monitor.py`, `ds01-events` |
| `scripts/maintenance/` | Cleanup automation | `check-idle-containers.sh`, `cleanup-*.sh` |
| `config/` | Resource limits, groups | `resource-limits.yaml`, `groups/*.members` |
| `testing/` | Test suites | `cleanup-automation/`, `validation/` |
| `monitoring/` | Prometheus/Grafana stack | `docker-compose.yaml`, `ds01_exporter.py` |

## Coding Conventions

**Bash:**
- Use `set -e`, shebang line 1
- Use `echo -e` for ANSI colours
- Capture exit codes: `set +e; OUTPUT=$(cmd); CODE=$?; set -e`

**Python:**
- Use argparse with `main()` function
- For bash heredocs: `<<'PYEOF'` with env vars

**CLI commands:**
- Interactive by default (no args → wizard)
- 4-tier help: `--help`, `--info`, `--concepts`, `--guided`
- Dispatcher pattern: `container deploy` routes to `container-deploy`

## Resource Configuration

Priority order: `user_overrides` > `groups` > `defaults`

Key fields in `config/resource-limits.yaml`:
- `max_mig_instances` - GPUs per user
- `allow_full_gpu` - Access to non-MIG GPUs
- `idle_timeout`, `max_runtime` - Lifecycle limits
- `gpu_hold_after_stop` - GPU reservation after stop

## Security

- GPU pinning via `--gpus device=X` prevents cross-user access
- Systemd cgroups prevent resource exhaustion
- Never store secrets in YAML
- Never allow cgroup-parent override

## Dependencies

- Docker + NVIDIA Container Toolkit
- Python 3.8+ with PyYAML
- AIME ML Containers at `/opt/aime-ml-containers`
- systemd, nvidia-smi, git

---

**For detailed docs:** See README.md in each `scripts/*/` directory.
