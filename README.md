# DS01 Infrastructure

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![Python 3.8+](https://img.shields.io/badge/python-3.8+-blue.svg)](https://www.python.org/downloads/) [![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff) [![Docs](https://img.shields.io/badge/docs-end%20user%20docs-blue)](https://github.com/hertie-data-science-lab/ds01-hub/tree/main/docs)

**Multi-user GPU management for research labs** - without the complexity of Kubernetes or SLURM.

DS01 brings container-based GPU allocation, per-user resource limits, and automated lifecycle management to small-to-medium research organisations running shared GPU servers.

## Why DS01?

| Challenge | DS01 Solution |
|-----------|---------------|
| **GPU contention** | MIG-aware allocation with priority scheduling |
| **Resource hogging** | Per-user/group limits via YAML + systemd cgroups |
| **Stale containers** | Automated idle detection and cleanup |
| **Complex onboarding** | Educational wizards guide new users |
| **Container sprawl** | Ephemeral model - GPUs freed on retire |

**Built on proven foundations:**
- [AIME ML Containers](https://github.com/aime-team/aime-ml-containers) for container management
- Docker + NVIDIA Container Toolkit for GPU passthrough
- VS Code Dev Containers for IDE integration
- systemd cgroups for resource isolation
- Prometheus + Grafana for monitoring and metrics

## Quick Start

### For Administrators

```bash
# Clone to standard location
sudo git clone https://github.com/hertie-data-science-lab/ds01-infra /opt/ds01-infra
cd /opt/ds01-infra

# Deploy commands and configure slices
sudo scripts/system/deploy-commands.sh
sudo scripts/system/setup-resource-slices.sh

# Add a user
sudo scripts/system/add-user-to-docker.sh alice
```

### For End Users

See the [End User Quickstart Guide](https://github.com/hertie-data-science-lab/ds01-hub/blob/main/docs/quickstart.md) for getting started with DS01.

```bash
user-setup              # Guided onboarding
project init my-thesis  # Create project with Dockerfile
container deploy        # Launch container with GPU
```

## Features

### GPU Resource Management
- **MIG-aware allocation** - Track and assign MIG instances or full GPUs
- **Priority scheduling** - Admins/researchers get priority over students
- **Access control** - Students get MIG only, researchers get full GPUs
- **Automatic release** - GPUs freed when containers stop

### Per-User Resource Limits
```yaml
# config/resource-limits.yaml
defaults:
  max_mig_instances: 1
  max_cpus: 8
  memory: "32g"
  idle_timeout: "48h"

groups:
  researchers:
    max_mig_instances: 2
    memory: "64g"
    allow_full_gpu: true
```

### Container Lifecycle Automation
- **Idle detection** - Auto-stop containers below CPU threshold
- **Runtime limits** - Enforce maximum container runtime
- **GPU cleanup** - Release allocations from stopped containers
- **Container removal** - Auto-remove stale stopped containers

### User-Friendly Workflows
- **4-tier help system** - `--help`, `--info`, `--concepts`, `--guided`
- **Interactive wizards** - Guide users through complex operations
- **Project-centric model** - Dockerfiles persist, containers are ephemeral

## Architecture

DS01 uses a **5-layer modular architecture**:

```
┌─────────────────────────────────────────────────────────────────┐
│ L4: Wizards      user-setup, project-init, project-launch       │
├─────────────────────────────────────────────────────────────────┤
│ L3: Orchestrators   container deploy, container retire          │
├─────────────────────────────────────────────────────────────────┤
│ L2: Atomic          container-*, image-*                        │
├─────────────────────────────────────────────────────────────────┤
│ L1: MLC             mlc-patched.py (AIME + custom images)       │
├─────────────────────────────────────────────────────────────────┤
│ L0: Docker          Foundation runtime                          │
└─────────────────────────────────────────────────────────────────┘
```

**Design principles:**
- Wrap AIME, don't replace it (2.5% patch for custom image support)
- Single-purpose commands compose into workflows
- Universal enforcement via Docker wrapper + systemd cgroups

## Requirements

- **OS:** Ubuntu 20.04+ / Debian 11+
- **GPU:** NVIDIA GPU with MIG support (A100, H100) or any CUDA GPU
- **Docker:** 20.10+ with NVIDIA Container Toolkit
- **Python:** 3.8+ with PyYAML
- **AIME:** [aime-ml-containers](https://github.com/aime-team/aime-ml-containers) v2

## Installation

### 1. Prerequisites

```bash
# Install NVIDIA Container Toolkit
distribution=$(. /etc/os-release;echo $ID$VERSION_ID)
curl -s -L https://nvidia.github.io/nvidia-docker/gpgkey | sudo apt-key add -
curl -s -L https://nvidia.github.io/nvidia-docker/$distribution/nvidia-docker.list | \
  sudo tee /etc/apt/sources.list.d/nvidia-docker.list
sudo apt-get update && sudo apt-get install -y nvidia-container-toolkit

# Install AIME ML Containers
sudo git clone https://github.com/aime-team/aime-ml-containers /opt/aime-ml-containers
```

### 2. Install DS01

```bash
# Clone repository
sudo git clone https://github.com/hertie-data-science-lab/ds01-infra /opt/ds01-infra
cd /opt/ds01-infra

# Make scripts executable
find scripts -type f \( -name "*.sh" -o -name "*.py" \) -exec chmod +x {} \;

# Deploy commands to PATH
sudo scripts/system/deploy-commands.sh

# Configure systemd slices
sudo scripts/system/setup-resource-slices.sh
sudo systemctl daemon-reload
```

### 3. Configure Resource Limits

```bash
sudo vim config/resource-limits.yaml
```

Define your groups and limits. See [config/README.md](config/README.md) for full reference.

### 4. Add Users

```bash
# Add user to docker group with DS01 slice
sudo scripts/system/add-user-to-docker.sh username

# User must log out and back in
```

## Usage

### For Users

```bash
# First-time setup
user-setup                              # Guided onboarding wizard

# Project workflow
project init my-thesis --type=cv        # Create project structure
project launch my-thesis                # Build image + deploy container

# Container management
container deploy my-project             # Launch container
container retire my-project             # Stop + remove + free GPU

# Check your limits
check-limits                            # View resource usage and limits
```

### For Administrators

```bash
# System status
dashboard                               # GPU, containers, system overview
dashboard users                         # Per-user breakdown

# User management
sudo scripts/system/add-user-to-docker.sh newuser

# GPU status
python3 scripts/docker/gpu_allocator.py status

# Logs
tail -f /var/log/ds01/gpu-allocations.log
```

## Directory Structure

```
ds01-infra/
├── config/
│   ├── resource-limits.yaml    # Central resource configuration
│   └── groups/                 # Group membership files
├── scripts/
│   ├── docker/                 # GPU allocation, container creation
│   ├── user/                   # User-facing commands (L2-L4)
│   ├── admin/                  # Admin tools and dashboards
│   ├── lib/                    # Shared libraries
│   ├── system/                 # System administration
│   ├── monitoring/             # Metrics and health checks
│   └── maintenance/            # Cleanup automation
├── testing/                    # Test suites
└── docs-user/                  # User documentation
```

## Documentation

| Document | Purpose |
|----------|---------|
| [CLAUDE.md](CLAUDE.md) | AI assistant instructions (index to detailed docs) |
| [ds01-UI_UX_GUIDE.md](ds01-UI_UX_GUIDE.md) | CLI design standards |
| [config/README.md](config/README.md) | Resource configuration reference |
| [scripts/user/README.md](scripts/user/README.md) | User command reference |
| [scripts/admin/README.md](scripts/admin/README.md) | Admin tools reference |
| [scripts/docker/README.md](scripts/docker/README.md) | GPU allocation internals |
| [scripts/monitoring/README.md](scripts/monitoring/README.md) | Monitoring setup |
| [scripts/maintenance/README.md](scripts/maintenance/README.md) | Cleanup automation |

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

**Commit format:** [Conventional Commits](https://www.conventionalcommits.org/)
```bash
feat: add feature     # MINOR bump
fix: resolve bug      # PATCH bump
feat!: breaking       # MAJOR bump
```

## Roadmap

See [TODO.md](TODO.md) for current priorities:
- **HIGH:** Dev Container GPU integration, monitoring fixes
- **MEDIUM:** OPA authorization, bare metal restriction
- **LOW:** SLURM integration, dynamic MIG partitioning

## License

MIT License - see [LICENSE](LICENSE) for details.

---

**Developed by [Henry Baker](https://henrycgbaker.github.io/) for the [Hertie School Data Science Lab](https://www.hertie-school.org/en/datasciencelab)**

📖 [User Documentation](https://github.com/hertie-data-science-lab/ds01-hub/tree/main/docs) · 🐛 [Report Issues](https://github.com/hertie-data-science-lab/ds01-hub/issues)
