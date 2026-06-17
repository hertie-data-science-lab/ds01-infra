---
title: Subsystem references
sidebar_position: 3
---

# Subsystem references

In-depth reference docs currently live as READMEs next to the code they describe.
This page links out to them on GitHub. (Migrating this content into full pages on
this site is planned follow-up work — see the note on the [Developer home](./index.md).)

## Command layers

- [`scripts/user/README.md`](https://github.com/hertie-data-science-lab/ds01-infra/blob/main/scripts/user/README.md)
  — the user-facing command layers (L0–L4): every container/image/project command, plus workflows.
- [`scripts/user/USER-CLI-UIUX-GUIDE.md`](https://github.com/hertie-data-science-lab/ds01-infra/blob/main/scripts/user/USER-CLI-UIUX-GUIDE.md)
  — CLI/UX design standards for user-facing commands.
- [`scripts/lib/README.md`](https://github.com/hertie-data-science-lab/ds01-infra/blob/main/scripts/lib/README.md)
  — reference for the shared bash libraries and Python helpers used across the codebase.
- [`scripts/admin/README.md`](https://github.com/hertie-data-science-lab/ds01-infra/blob/main/scripts/admin/README.md)
  — admin tooling: dashboard, logs, user management, GPU tools.
- [`scripts/system/README.md`](https://github.com/hertie-data-science-lab/ds01-infra/blob/main/scripts/system/README.md)
  — system administration: user management, deploy tooling, systemd integration.

## Operations & lifecycle

- [`scripts/maintenance/README.md`](https://github.com/hertie-data-science-lab/ds01-infra/blob/main/scripts/maintenance/README.md)
  — lifecycle automation: container cleanup, idle detection, enforcement.
- [`monitoring/README.md`](https://github.com/hertie-data-science-lab/ds01-infra/blob/main/monitoring/README.md)
  — Prometheus/Grafana architecture, metric reference, alert rules, dashboards.
- [`scripts/monitoring/README.md`](https://github.com/hertie-data-science-lab/ds01-infra/blob/main/scripts/monitoring/README.md)
  and [`GPU_STRESS_TEST_GUIDE.md`](https://github.com/hertie-data-science-lab/ds01-infra/blob/main/scripts/monitoring/GPU_STRESS_TEST_GUIDE.md)
  — monitoring setup and GPU stress-test procedures.

## Configuration & testing

- [`config/README.md`](https://github.com/hertie-data-science-lab/ds01-infra/blob/main/config/README.md)
  — configuration lifecycle, runtime vs deploy-time, `resource-limits.yaml` reference.
- [`testing/README.md`](https://github.com/hertie-data-science-lab/ds01-infra/blob/main/testing/README.md)
  — test suite architecture (unit/integration/system), running tests, markers.
