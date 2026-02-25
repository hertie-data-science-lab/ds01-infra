# ADR-008: Layered Command Architecture

**Status:** Accepted
**Date:** 2026-01-30

## Context

DS01 serves users with vastly different experience levels — students new to Linux and Docker, researchers comfortable with command lines, and faculty with varying technical backgrounds. A single command interface cannot serve all these audiences well: beginners need guidance, experts need efficiency.

## Decision

Organise user commands in a 5-layer hierarchy where each layer wraps the one below:

| Layer | Type | Audience | Example |
|-------|------|----------|---------|
| L4 | Wizards | Beginners | `user-setup`, `project-init`, `project-launch` |
| L3 | Orchestrators | Intermediate | `container deploy`, `container retire` |
| L2 | Atomic | Advanced | `container-create`, `container-start`, `container-stop` |
| L1 | MLC | Internal | `mlc-patched.py` (AIME wrapper) |
| L0 | Docker | Foundation | `/usr/bin/docker` (real binary) |

Each layer adds value: L4 wizards compose L3 orchestrators, which sequence L2 atomic commands, which call L1 MLC, which calls L0 Docker (through the wrapper).

## Rationale

Composition over monolith. Single-purpose atomic commands (L2) are independently testable, scriptable, and debuggable. Orchestrators (L3) compose them into user-friendly workflows. Wizards (L4) add interactive guidance. Users can enter at any layer appropriate to their skill level.

## Alternatives Considered

- **Single monolithic CLI:** One command with many subcommands. Doesn't scale to different skill levels. Beginners overwhelmed by options; experts frustrated by mandatory wizards.
- **Separate tools per audience:** Different binaries for beginners vs experts. Maintenance burden, inconsistent behaviour, confusing when users graduate from one level to another.
- **GUI-only:** Web interface for all users. Excludes SSH-only access patterns and power users who prefer CLI.

## Consequences

- **Positive:** Users can work at their comfort level. Commands compose naturally. Each layer is testable in isolation. 4-tier help system (`--help`, `--info`, `--concepts`, `--guided`) provides appropriate depth per layer.
- **Negative:** More commands to maintain. Context variable (`DS01_CONTEXT=orchestration`) needed to suppress duplicate output when commands are chained.
- **Accepted trade-off:** Maintenance cost of layered commands is offset by better UX across diverse user population.
