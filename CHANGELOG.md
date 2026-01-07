# Changelog

All notable changes to DS01 Infrastructure will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).


Initial versioned release of DS01 Infrastructure.

### Features
- GPU-enabled container management with MIG support
- Per-user/group resource limits (YAML configuration)
- Container lifecycle automation (idle detection, auto-cleanup)
- 5-layer command architecture (Docker -> MLC -> Atomic -> Orchestrators -> Wizards)
- User-facing commands: `container deploy`, `container retire`, `project init`, `project launch`
- Admin dashboard with GPU, container, and system monitoring
- Centralized event logging

### Documentation
- Comprehensive user documentation in `docs-user/`
- Admin documentation in `docs-admin/`
- Module-specific READMEs throughout the codebase

### Infrastructure
- Systemd cgroups for resource isolation
- OPA authorization plugin
- Docker wrapper for per-user slice injection
- Cron-based cleanup automation

## v1.1.0 (2026-01-07)

### Features

- add semantic versioning with commitizen

## v1.0.0 (2025-12-02)

### Features

- Unify workflows into project-init with --guided flag + rollback docker socket
- Make all host commands available inside containers
- Clarify container vs host commands and add VS Code container setup guide
- Improve container workflow and fix name clash issues
- Add persistent container alias system and fix username display
- Improve user onboarding workflows and rename commands
