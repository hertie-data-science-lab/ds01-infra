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
