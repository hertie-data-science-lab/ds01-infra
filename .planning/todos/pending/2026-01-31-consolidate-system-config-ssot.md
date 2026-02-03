---
created: 2026-01-31T19:40
title: Consolidate system config into single SSOT directory
area: tooling
files:
  - config/deploy/:*
  - config/etc-mirrors/:*
  - scripts/system/deploy.sh:119-135
---

## Problem

Two directories with overlapping purpose create ambiguity about which is authoritative for system configs:

- `config/deploy/` — source files that deploy.sh copies TO `/etc/` (udev rules, profile.d/motd, systemd units, cron.d jobs). This is what the deploy pipeline reads from.
- `config/etc-mirrors/` — reference copies FROM `/etc/` (profile.d/ds01-docker-group.sh, ds01-path.sh, sudoers.d/, cron.d/, bash.bashrc, systemd/ds01.slice.conf). Snapshot for visibility but not consumed by deploy.

Some files exist in one but not the other. Neither directory is a complete picture of what DS01 deploys to the system. No single place to examine "what does DS01 put on this server?"

### Current inventory

**In `config/deploy/` only:**
- `udev/99-ds01-nvidia.rules`
- `profile.d/ds01-motd.sh`
- `systemd/ds01-workload-detector.{service,timer}`
- `systemd/ds01-dcgm-exporter.service`
- `cron.d/ds01-enforce-containers`
- `docker/daemon.json`
- `opa/` (parked)

**In `config/etc-mirrors/` only:**
- `profile.d/ds01-docker-group.sh`, `ds01-path.sh`
- `sudoers.d/ds01-docker-group`, `ds01-user-slice`
- `bash.bashrc`
- `systemd/system/ds01.slice.conf`
- `logrotate.d/ds01-infra-logrotate.conf`
- `cron.d/ds01-container-cleanup`, `ds01-gpu-cleanup`

## Solution

1. Merge both directories into `config/deploy/` as the single SSOT
2. Move all `etc-mirrors/` files into appropriate `config/deploy/` subdirectories
3. Remove `config/etc-mirrors/` entirely
4. Update deploy.sh to deploy ALL files from `config/deploy/` (sudoers.d, additional profile.d, etc.)
5. Add a `deploy --diff` option to show what differs between repo and live system
6. Update CLAUDE.md references
