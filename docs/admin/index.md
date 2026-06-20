---
title: Admin & Ops
sidebar_position: 1
slug: /
---

# Admin & Operations

Documentation for **administering and operating DS01** — the multi-user GPU
container platform. For end-user docs see the [User Guide](/guide); for
contributor docs see [Developer](/develop).

## Setup & configuration

- [Architecture](./architecture.md) — system design, layers, container detection.
- [Installation](./installation.md) — initial setup.
- [Setup checklist](./setup-checklist.md) — pre-deployment validation steps.
- [System configuration](./system-config.md) — runtime config, resource limits, groups.

## Operations

- [Maintenance](./maintenance.md) — routine maintenance, cleanup, upgrades.
- [Monitoring](./monitoring.md) — Prometheus/Grafana, metrics, alerts.
- [Quick reference](./quick-reference.md) — admin command cheat sheet.
- [Versioning](./versioning.md) — version scheme, deprecation, upgrade paths.
- [CI & releases](./ci.md) — pipeline, conventional commits, release process.

## Architecture deep-dives

See the **Architecture** section in the sidebar — command layers, image/container
flows, the AIME MLC patch strategy, and integration strategy.

## Security

- [User privacy](./security/user-privacy.md) — privacy, data handling, user isolation.
