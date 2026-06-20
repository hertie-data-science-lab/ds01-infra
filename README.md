# DS01 Infrastructure

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE) [![Code style: Ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff) [![Docs](https://img.shields.io/badge/docs-live-blue)](https://hertie-data-science-lab.github.io/ds01-infra/)

**Multi-user containerised ML workload management for data science research labs.**

DS01 brings container-based compute allocation, per-user resource limits, and automated lifecycle management to small-to-medium research organisations running shared GPU servers.

## Documentation

| Site | For | |
|------|-----|---|
| **[Full documentation](https://hertie-data-science-lab.github.io/ds01-infra/)** | Users, admins & contributors | install, operations, architecture, internals |
| **[User guide](https://hertie-data-science-lab.github.io/ds01/)** | Researchers & students | get a container running in ~30 minutes |

Everything below is a quick orientation for people browsing this repository — the sites above are the source of truth for usage and operations.

## Why DS01?

| Challenge | DS01 Solution |
|-----------|---------------|
| **GPU contention** | MIG-aware allocation with priority scheduling |
| **Resource hogging** | Per-user/group limits via YAML + systemd cgroups |
| **Stale containers** | Automated idle detection and cleanup |
| **Complex onboarding** | Educational wizards guide new users |
| **Container sprawl** | Ephemeral model — GPUs freed on retire |
| **Observability** | Prometheus & Grafana dashboard configs |
| **Green computing** | Energy use & carbon emission tracking |

**Built on:** [AIME ML Containers](https://github.com/aime-team/aime-ml-containers) · Docker + NVIDIA Container Toolkit · VS Code Dev Containers · systemd cgroups · Prometheus + Grafana.

## Architecture

DS01 wraps (rather than replaces) AIME MLC in a 5-layer command stack:

```
L4: Wizards        user-setup, project-init, project-launch
L3: Orchestrators  container deploy, container retire
L2: Atomic         container-*, image-*
L1: MLC            mlc-patched.py (AIME + custom images)
L0: Docker         foundation runtime
```

Single-purpose commands compose into workflows; enforcement is universal via a Docker wrapper + systemd cgroups. See [Admin → Architecture](https://hertie-data-science-lab.github.io/ds01-infra/admin/architecture) for the full design.

## Getting started

**Users** — see the [30-minute quickstart](https://hertie-data-science-lab.github.io/ds01/quickstart). In short:

```bash
user-setup              # guided onboarding
project init my-thesis  # create a project with a Dockerfile
container deploy        # launch a container with a GPU
```

**Administrators** — see [Admin → Installation](https://hertie-data-science-lab.github.io/ds01-infra/admin/installation) for the full deployment guide. In short:

```bash
sudo git clone https://github.com/hertie-data-science-lab/ds01-infra /opt/ds01-infra
cd /opt/ds01-infra
sudo scripts/system/deploy-commands.sh        # deploy commands to PATH
sudo scripts/system/setup-resource-slices.sh  # configure systemd slices
sudo scripts/system/add-user-to-docker.sh alice
```

## Requirements

- **OS:** Ubuntu 20.04+ / Debian 11+
- **GPU:** NVIDIA GPU with MIG support (A100, H100) or any CUDA GPU
- **Docker:** 20.10+ with NVIDIA Container Toolkit
- **Python:** 3.8+ with PyYAML
- **AIME:** [aime-ml-containers](https://github.com/aime-team/aime-ml-containers) v2

## Repository layout

```
ds01-infra/
├── config/        # resource-limits.yaml + group membership
├── scripts/       # docker/ user/ admin/ lib/ system/ monitoring/ maintenance/
├── monitoring/    # Prometheus + Grafana stack
├── tests/       # test suites
├── docs/user/     # end-user docs (source of truth; synced to the ds01-hub site)
├── docs/admin/    # admin & ops docs
├── docs/develop/  # contributor docs
└── website/       # Docusaurus site (full docs)
```

Subsystem READMEs live next to the code (`scripts/lib/`, `scripts/user/`, `monitoring/`, `config/`, …) and are indexed from [Developer → Subsystem references](https://hertie-data-science-lab.github.io/ds01-infra/develop/subsystem-references).

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## License

MIT — see [LICENSE](LICENSE).

---

Developed by [Henry Baker](https://henrycgbaker.github.io/) for the [Hertie School Data Science Lab](https://www.hertie-school.org/en/datasciencelab). · [Report an issue](https://github.com/hertie-data-science-lab/ds01-hub/issues)
