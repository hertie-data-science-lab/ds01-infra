# [1.2.0](https://github.com/hertie-data-science-lab/ds01-infra/compare/v1.1.0...v1.2.0) (2026-01-30)


### Bug Fixes

* correct container-retire path in session exit handler ([750f0d4](https://github.com/hertie-data-science-lab/ds01-infra/commit/750f0d4ed1aba77c8389089b60cc1eedc6b10f04))
* disable GDM on compute server to free GPU handles ([f949d87](https://github.com/hertie-data-science-lab/ds01-infra/commit/f949d873a3fc1e668c18e5265f027abfacf43efa))
* flush stdin buffer before all prompts in mig-configure ([b9fb303](https://github.com/hertie-data-science-lab/ds01-infra/commit/b9fb30397fe29725ebd7380301835a052567f73e))
* mig-configure handles pending state and GPU reset ([d9ffe6c](https://github.com/hertie-data-science-lab/ds01-infra/commit/d9ffe6ca4ea1d232f78977d647f2956a53cf1e1e))
* mig-configure instance count handles disabled GPUs ([d99846d](https://github.com/hertie-data-science-lab/ds01-infra/commit/d99846dee4b32b73e0eff2ec26bff18f75cd4b5f))
* resolve domain variants to canonical username for docker group ([e4eb58e](https://github.com/hertie-data-science-lab/ds01-infra/commit/e4eb58e21f267aad79738eefd38adbc28395d457))
* set HOME env var for VS Code server compatibility ([03c1562](https://github.com/hertie-data-science-lab/ds01-infra/commit/03c15629d2ae47a30fea9835946ec623b55290d2))
* sync alias-list with deployed version, add mig-configure ([77484e2](https://github.com/hertie-data-science-lab/ds01-infra/commit/77484e238adee6f63bb21fd8b5ee6be36c976c12))
* use ds01 recording rules in user and DCGM dashboards ([45531f8](https://github.com/hertie-data-science-lab/ds01-infra/commit/45531f8aba46b7cf33eb6eac6c84bef04b9616c8))


### Features

* **01-04:** replace commitizen with semantic-release ([7113835](https://github.com/hertie-data-science-lab/ds01-infra/commit/711383509fdee74a2b321a4505782819a0cbdb80))
* add interactive MIG configuration CLI ([1b99fde](https://github.com/hertie-data-science-lab/ds01-infra/commit/1b99fde99966babbe246ba381e6477eb77277f51))
* add Prometheus/Grafana monitoring stack ([2d1ad6c](https://github.com/hertie-data-science-lab/ds01-infra/commit/2d1ad6c87970fd147123d62e83b9692a8ab5f5d9))
* add real-time container ownership tracking system ([1be6507](https://github.com/hertie-data-science-lab/ds01-infra/commit/1be65072025bcda5cc77d156f0714d8ea810b4b2))
* add unmanaged GPU container detection and monitoring ([8fbee85](https://github.com/hertie-data-science-lab/ds01-infra/commit/8fbee85c87ed7a3d7dbd0bb7d915f29d816bb590))
* add VS Code dev container integration ([945600d](https://github.com/hertie-data-science-lab/ds01-infra/commit/945600d612abd6cf88a812d6b8a194d64bc7a442))
* mig-configure force reset with process detection ([10970dd](https://github.com/hertie-data-science-lab/ds01-infra/commit/10970dd0c30abe6df233a73c4e3efcc9aef3e800))
* prefer full GPUs for users with allow_full_gpu permission ([8e03dcb](https://github.com/hertie-data-science-lab/ds01-infra/commit/8e03dcb9ad660b4e62efd7fae5ec64b24a6787de))
* universal container management for all GPU containers ([4e634f7](https://github.com/hertie-data-science-lab/ds01-infra/commit/4e634f780d1f72ff68f8b4735edf5f309f24a897))

# Changelog

All notable changes to DS01 Infrastructure will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Hybrid monitoring architecture:
  - DS01 Exporter as systemd service (`ds01-exporter.service`) for allocation/business metrics
  - Prometheus container (`ds01-prometheus`) for metrics storage
  - Grafana container (`ds01-grafana`) for dashboards
  - Node Exporter container for system metrics
  - Alertmanager container for alert routing
  - DCGM Exporter for GPU metrics (Phase 3 complete)
- Metric collection cron jobs (GPU, CPU, memory, disk, containers - every 5 min)

### Known Issues
- DCGM Exporter container crashed (needs restart)
- Grafana dashboard provisioning misconfigured
- Event log empty (`/var/log/ds01/events.jsonl`)
- Dev Containers lack GPU assignment and label tracking

## v1.1.0 (2026-01-07)

### Added
- Semantic versioning with commitizen
- Interactive MIG configuration CLI (`mig-configure`)
- Real-time container ownership tracking system (`container-owner-tracker.py`)
- Force reset with process detection for MIG configuration

### Fixed
- Container-retire path in session exit handler
- Domain variants resolved to canonical username for docker group
- MIG instance count handling for disabled GPUs
- Pending state and GPU reset in mig-configure
- Stdin buffer flushed before all prompts in mig-configure
- GDM disabled on compute server to free GPU handles

### Testing
- Unit tests for username canonicalisation

## v1.0.0 (2025-12-02)

### Added
- 5-layer command architecture (L0: Docker → L1: MLC → L2: Atomic → L3: Orchestrators → L4: Wizards)
- User-facing commands: `container deploy`, `container retire`, `project init`, `project launch`
- Admin dashboard with GPU, container, and system monitoring
- Centralised event logging system
- 4-tier help system across all CLI commands (`--help`, `--info`, `--concepts`, `--guided`)
- DS01 UI/UX design guide for CLI consistency
- Per-user Docker container isolation system
- Docker wrapper with ownership tracking and visibility filtering
- Requirements.txt import support in image-create
- Auto-detect CUDA architecture based on host driver
- Shared Dockerfile generator library
- Project-centric workflow with project launch L4 wizard
- GitHub Actions workflow to sync docs to ds01-hub

### Fixed
- Silent exit code 2 failures in container creation
- MIG device visibility (CUDA_VISIBLE_DEVICES)
- Multi-MIG allocation and full GPU preference
- Image preservation in container retire workflow
- Username sanitisation consistency
- Dashboard and container-list owner detection
- Docker proxy HTTP/2 support

### Changed
- Tier → Layer (L0-L4) terminology
- Command reorganisation: clean user names, ds01-* admin prefix
- docs/ renamed to docs-user/ for clarity
- Comprehensive user documentation restructured for modularity

## v0.9.0 (2025-11-25) - Pre-release

### Added
- Layered architecture with universal enforcement (cgroups, OPA, Docker wrapper)
- Comprehensive pytest-based test suite (149 tests)
- LDAP/SSSD username support with auto docker group management
- Resource monitoring, alerts, and soft limits (Phase 7)
- Centralised logging for resource allocation audits
- Container session command unification
- Dashboard redesign with improved visual design and modular architecture
- 4-tier group model with faculty tier
- Group management system with auto-sync
- Container-unpause command
- User-activity-report admin tool
- Home directory enforcement via profile.d
- Maintenance scripts for permissions management

### Fixed
- LDAP user container deployment and diagnostics
- VS Code setup duplication and onboarding-create bug
- Git remote prompt duplication in project-init
- GID mapping debugging

### Changed
- User-setup wizard redesigned with skill-adaptive SSH flow
- Onboarding flows decoupled for shorter, focused setup
- Wizard output streamlined and verbosity reduced

## v0.8.0 (2025-10-01) - Foundation

### Added
- MIG partition configuration
- GPU status dashboard (`gpu-status-dashboard.py`)
- Resource limits system (`get_resource_limits.py`, `gpu_allocator.py`)
- Container setup wizard MVP
- User container scripts (create, start, stop, remove)
- mlc-create wrapper for AIME integration
- Systemd control groups with /var/log structure
- Initial monitoring: modular collectors

### Infrastructure
- Transferred scripts from home workspace
- DSL sudo protections
- Log mirrors and symlinks
