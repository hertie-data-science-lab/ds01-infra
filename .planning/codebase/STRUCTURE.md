# Codebase Structure

**Analysis Date:** 2026-01-26

## Directory Layout

```
/opt/ds01-infra/
├── scripts/                    # All user-facing and system commands
│   ├── user/                   # User-facing commands (L2-L5)
│   │   ├── atomic/             # L2 single-purpose commands
│   │   ├── orchestrators/      # L3 multi-step workflows
│   │   ├── wizards/            # L4 guided onboarding
│   │   ├── helpers/            # Helper utilities
│   │   ├── dispatchers/        # Command routers
│   │   └── CLAUDE.md
│   │
│   ├── docker/                 # GPU allocation and container enforcement
│   │   ├── gpu_allocator_v2.py # Stateless GPU allocation
│   │   ├── docker-wrapper.sh   # Universal enforcement wrapper at /usr/local/bin/docker
│   │   ├── mlc-patched.py      # AIME patch for custom images
│   │   ├── get_resource_limits.py # Config resolver
│   │   ├── container-owner-tracker.py # Real-time ownership tracking
│   │   ├── event-logger.py     # JSON event logging
│   │   └── CLAUDE.md
│   │
│   ├── lib/                    # Shared bash/Python libraries
│   │   ├── init.sh             # Standard bash initialization
│   │   ├── ds01_core.py        # Core utilities (duration parsing, etc.)
│   │   ├── dockerfile-generator.sh # Shared Dockerfile generation
│   │   ├── container-session.sh # Unified start/run/attach handler
│   │   ├── error-messages.sh   # User-friendly errors
│   │   └── CLAUDE.md
│   │
│   ├── admin/                  # Admin dashboards and tools
│   │   ├── dashboard           # Main system dashboard
│   │   ├── ds01-logs           # Log viewer
│   │   ├── ds01-users          # User management utilities
│   │   ├── mig-configure       # Interactive MIG configuration
│   │   └── CLAUDE.md
│   │
│   ├── system/                 # System administration and deployment
│   │   ├── deploy.sh           # Deploy commands to /usr/local/bin
│   │   ├── add-user-to-docker.sh # User onboarding
│   │   ├── setup-docker-cgroups.sh # Cgroup configuration
│   │   ├── create-user-slice.sh # Per-user systemd slice creation
│   │   └── CLAUDE.md
│   │
│   ├── monitoring/             # Metrics and health checks
│   │   ├── check-idle-containers.sh # Idle timeout enforcement
│   │   ├── gpu-utilization-monitor.py # GPU usage tracking
│   │   ├── ds01-events         # Query event log
│   │   ├── ds01-health-check   # System health checks
│   │   └── CLAUDE.md
│   │
│   └── maintenance/            # Cleanup automation and lifecycle
│       ├── enforce-max-runtime.sh # Max runtime enforcement
│       ├── cleanup-stale-gpu-allocations.sh # GPU hold cleanup
│       ├── cleanup-stale-containers.sh # Container removal
│       └── CLAUDE.md
│
├── config/                     # Resource configuration and groups
│   ├── resource-limits.yaml    # Central resource limits (users, groups, defaults)
│   ├── user-overrides.yaml     # Per-user exceptions
│   ├── groups/                 # Group membership files (*.members)
│   ├── deploy/                 # System deployment files
│   │   ├── cron.d/             # → /etc/cron.d/
│   │   ├── profile.d/          # → /etc/profile.d/
│   │   ├── systemd/            # → /etc/systemd/system/
│   │   └── logrotate.d/        # → /etc/logrotate.d/
│   ├── etc-mirrors/            # Reference copies from /etc
│   ├── usr-mirrors/            # Reference copies from /usr/local
│   └── CLAUDE.md
│
├── monitoring/                 # Prometheus/Grafana stack
│   ├── docker-compose.yaml     # Stack definition
│   ├── ds01_exporter.py        # Custom DS01 metrics exporter
│   ├── prometheus/             # Prometheus config and rules
│   └── grafana/                # Grafana dashboards
│
├── testing/                    # Test suites
│   ├── unit/                   # Unit tests
│   ├── component/              # Component tests
│   ├── cleanup-automation/     # Lifecycle enforcement tests
│   ├── docker-permissions/     # Docker/cgroup tests
│   └── validation/             # Validation tests
│
├── docs-user/                  # User documentation
├── docs-admin/                 # Admin documentation
├── CLAUDE.md                   # Root architecture overview
├── TODO.md                     # Work tracking
└── .planning/                  # Planning and codebase analysis
    └── codebase/               # GSD codebase documents (ARCHITECTURE.md, STRUCTURE.md, etc.)
```

## Directory Purposes

**scripts/user/**
- Purpose: All user-facing commands organized by layer (L2-L5)
- Contains: Atomic commands, orchestrators, wizards, helpers, dispatchers
- Key files: `scripts/user/CLAUDE.md` for detailed layer documentation
- Dependencies: lib utilities, docker wrapper, config

**scripts/docker/**
- Purpose: GPU allocation, container creation, and Docker enforcement
- Contains: gpu_allocator_v2.py (stateless allocation), docker-wrapper.sh (universal enforcement), mlc-patched.py (AIME patch)
- Key files: `gpu_allocator_v2.py` (entry point for allocation), `docker-wrapper.sh` (entry point at /usr/local/bin/docker)
- Dependencies: get_resource_limits.py, system utilities (nvidia-smi, systemd)

**scripts/lib/**
- Purpose: Shared libraries for bash and Python code
- Contains: init.sh (bash utilities), ds01_core.py (Python utilities), dockerfile-generator.sh, container-session.sh
- Key files: `init.sh` (source this first), `ds01_core.py` (import for Python)
- Dependencies: YAML parser, standard utilities

**scripts/admin/**
- Purpose: Admin tools and dashboards
- Contains: dashboard (main view), ds01-logs (log viewer), mig-configure (MIG setup)
- Key files: `dashboard` (main entry point for admin)
- Dependencies: /var/lib/ds01/ state files, system utilities

**scripts/system/**
- Purpose: System administration, deployment, and user setup
- Contains: deploy.sh (deploy to /usr/local/bin), add-user-to-docker.sh (user onboarding), setup-docker-cgroups.sh
- Key files: `deploy.sh` (command deployment), `add-user-to-docker.sh` (user setup)
- Dependencies: Root access, systemd, Docker

**scripts/monitoring/**
- Purpose: Metrics collection, health checks, idle detection
- Contains: check-idle-containers.sh (idle enforcement), gpu-utilization-monitor.py (metrics), ds01-events (event log)
- Key files: `check-idle-containers.sh` (cron :30/hour, universal idle detection)
- Dependencies: Docker, nvidia-smi, /var/lib/ds01/ state

**scripts/maintenance/**
- Purpose: Cleanup automation and lifecycle enforcement
- Contains: enforce-max-runtime.sh (max runtime enforcement), cleanup-stale-*.sh (garbage collection)
- Key files: `enforce-max-runtime.sh` (cron :45/hour), `cleanup-stale-gpu-allocations.sh` (cron :15/hour)
- Dependencies: Docker, /var/lib/ds01/ state, resource-limits.yaml

**config/**
- Purpose: Resource configuration, group definitions, system deployment files
- Contains: resource-limits.yaml (central config), groups/*.members (group membership), deploy/ (system files)
- Key files: `resource-limits.yaml` (read by all systems), `groups/*.members` (group definitions)
- Dependencies: YAML syntax, group names in Unix system

**monitoring/**
- Purpose: Prometheus/Grafana monitoring stack
- Contains: docker-compose.yaml (stack), ds01_exporter.py (custom exporter), prometheus/ (rules), grafana/ (dashboards)
- Key files: `docker-compose.yaml` (deployment), `ds01_exporter.py` (metrics)
- Dependencies: Docker, Prometheus format knowledge

**testing/**
- Purpose: Test suites for all functionality
- Contains: unit/ (isolated tests), component/ (integration), cleanup-automation/ (lifecycle), docker-permissions/ (cgroup)
- Key files: Test files match functionality being tested
- Dependencies: Python 3.8+, bash testing utilities

## Key File Locations

**Entry Points:**

- `scripts/user/atomic/container-create` - Create container (L2)
- `scripts/user/orchestrators/container-deploy` - Deploy container (L3)
- `scripts/user/wizards/user-setup` - Onboarding wizard (L4)
- `/usr/local/bin/docker` → `scripts/docker/docker-wrapper.sh` - Universal enforcement
- `scripts/admin/dashboard` - System dashboard
- `scripts/system/deploy.sh` - Command deployment

**Configuration:**

- `config/resource-limits.yaml` - Central resource limits (read by all systems)
- `config/user-overrides.yaml` - Per-user exceptions
- `config/groups/*.members` - Group membership files (referenced by YAML)

**Core Logic:**

- `scripts/docker/gpu_allocator_v2.py` - Stateless GPU allocation
- `scripts/docker/docker-wrapper.sh` - Command interception and rewriting
- `scripts/monitoring/check-idle-containers.sh` - Idle detection and stopping
- `scripts/maintenance/enforce-max-runtime.sh` - Max runtime enforcement

**Libraries:**

- `scripts/lib/init.sh` - Bash initialization (ANSI colors, log functions)
- `scripts/lib/ds01_core.py` - Python utilities
- `scripts/lib/dockerfile-generator.sh` - Dockerfile generation
- `scripts/lib/error-messages.sh` - User-friendly error messages

## Naming Conventions

**Files:**

- Bash scripts: `kebab-case.sh` or no extension for executables (e.g., `dashboard`, `ds01-logs`)
- Python scripts: `kebab-case.py` or `snake_case.py`
- Libraries: `kebab-case.sh` for bash (e.g., `init.sh`, `error-messages.sh`)
- Config: `.yaml` (e.g., `resource-limits.yaml`)

**Directories:**

- Layer directories: `atomic/`, `orchestrators/`, `wizards/`, `helpers/`, `dispatchers/`
- Functional areas: `docker/`, `lib/`, `admin/`, `system/`, `monitoring/`, `maintenance/`
- Config areas: `deploy/`, `etc-mirrors/`, `usr-mirrors/`, `groups/`
- System directories: `testing/`, `monitoring/`, `docs-*/`

**Functions (Bash):**

- Utilities: `snake_case` (e.g., `log_info()`, `get_container_owner()`)
- Entry point: `main()` function at end of file
- Helpers: `_private_function()` prefix for internal functions

**Variables (Bash):**

- Environment: `UPPERCASE` (e.g., `SCRIPT_DIR`, `DS01_ROOT`)
- Local: `snake_case` (e.g., `container_name`, `user_group`)
- Config: `UPPERCASE` in config files (e.g., `DS01_CONTEXT`)

**Functions (Python):**

- All functions: `snake_case` (e.g., `get_resource_limits()`, `allocate_gpu()`)
- Classes: `PascalCase` (e.g., `GPUAllocator`)
- Constants: `UPPERCASE` (e.g., `INTERFACE_ORCHESTRATION`)

## Where to Add New Code

**New User Command (Atomic/L2):**
- Create file: `scripts/user/atomic/container-{operation}` (e.g., `container-inspect`)
- Template: Source `scripts/lib/init.sh`, implement `main()`, parse args
- Tests: Add to `testing/` with same name pattern

**New Orchestrator (L3):**
- Create file: `scripts/user/orchestrators/{name}` (e.g., `container-status`)
- Template: Source `scripts/lib/init.sh`, set `DS01_CONTEXT=orchestration`, call atomic commands
- Integration: Update dispatcher if space-separated (e.g., `container status`)

**New Wizard (L4):**
- Create file: `scripts/user/wizards/{name}` (e.g., `env-setup`)
- Template: Interactive prompts using `scripts/lib/prompts.sh`, call orchestrators
- Help system: Implement `--help`, `--info`, `--concepts`, `--guided` flags

**New Admin Tool:**
- Create file: `scripts/admin/{name}` (e.g., `ds01-quota-report`)
- Template: Read from `/var/lib/ds01/` state files and resource-limits.yaml
- Logging: Use structured output (JSON or formatted tables)

**New Monitoring/Maintenance Script:**
- Monitoring (active checks): `scripts/monitoring/{name}.sh` or `.py`
  - Run as non-root where possible
  - Read from `/var/lib/ds01/` and Docker labels
  - Output metrics or health status
- Maintenance (cron automation): `scripts/maintenance/{name}.sh`
  - Run as root via cron
  - Log to `/var/log/ds01/{name}.log`
  - Parse resource-limits.yaml for user-specific limits

**New Config Section:**
- Add to `config/resource-limits.yaml` under appropriate section
- Document in `config/CLAUDE.md` with examples
- Reference in: `get_resource_limits.py`, relevant scripts

**New Test:**
- Unit test: `testing/unit/{area}/test_{functionality}.py` or `.sh`
- Component test: `testing/component/test_{functionality}.py`
- Integration test: `testing/{area}/test_{scenario}.sh`
- All tests must pass before deploying with `scripts/system/deploy.sh`

## Special Directories

**`.planning/codebase/`:**
- Purpose: GSD codebase analysis documents
- Generated: Yes (by /gsd:map-codebase command)
- Committed: Yes (to help future planners/executors)
- Contents: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, CONCERNS.md, STACK.md, INTEGRATIONS.md

**`/var/lib/ds01/`:**
- Purpose: Runtime state (not in repo)
- Generated: Yes (at runtime by allocation scripts)
- Committed: No (ephemeral)
- Contents: `gpu-state.json`, `container-metadata/`, `opa/`, logs

**/var/log/ds01/**
- Purpose: Centralized logging (not in repo)
- Generated: Yes (at runtime)
- Committed: No (ephemeral)
- Contents: Event logs, allocation logs, cleanup logs, metrics

**`aime-ml-containers/`:**
- Purpose: Submodule pointing to AIME ML Containers
- Generated: No (submodule)
- Committed: Yes (but in .gitmodules)
- Contains: mlc-create, base images, utilities

**`archive/`:**
- Purpose: Historical scripts and configs (no longer used)
- Generated: No (manual migration)
- Committed: Yes (for historical reference)
- Contents: Deprecated scripts from earlier versions

## Import Patterns

**Bash Scripts:**

All user/system scripts should start with:
```bash
#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$(dirname "$0")/../lib/init.sh"

main() {
    # script logic
}

main "$@"
```

**Python Scripts:**

All Python scripts should use:
```python
#!/usr/bin/env python3
import sys
import argparse
from pathlib import Path

# Add lib to path for local imports
sys.path.insert(0, str(Path(__file__).parent.parent / "lib"))
from ds01_core import parse_duration, get_container_owner

def main():
    parser = argparse.ArgumentParser(description="...")
    # argument setup
    args = parser.parse_args()
    # main logic

if __name__ == "__main__":
    main()
```

**Config References:**

Scripts read `config/resource-limits.yaml` via:
```bash
# Bash
python3 scripts/docker/get_resource_limits.py <username>

# Python
from get_resource_limits import GetResourceLimits
limits = GetResourceLimits().get_limits("username")
```

---

*Structure analysis: 2026-01-26*
