---
created: 2026-02-05T18:15
title: "Bug: User cgroup slice not created (check-limits shows 'cgroup not yet created' after containers deployed)"
area: bug
files:
  - scripts/user/helpers/check-limits
  - scripts/system/create-user-slice.sh
  - scripts/docker/docker-wrapper.sh
  - scripts/docker/mlc-create-wrapper.sh
---

## Problem

`check-limits` shows "(No active containers - cgroup not yet created)" even after deploying multiple containers. This suggests the user's systemd cgroup slice (`ds01-{group}-{user}.slice`) is not being created properly.

## Expected Behaviour

When a user launches a container via ANY method, their cgroup slice should be created:
- DS01 commands (`container deploy`, `container-create`, etc.)
- Native `docker run` / `docker create`
- VS Code dev containers
- docker-compose

## Current Infrastructure

We already have cgroup infrastructure that should handle this:
- `create-user-slice.sh` — Creates the systemd slice
- `mlc-create-wrapper.sh` — Calls create-user-slice before container creation
- `docker-wrapper.sh` — Universal wrapper that intercepts all docker commands

## Investigation Needed

1. Is `create-user-slice.sh` being called?
2. Is it succeeding? Check for permission issues
3. Is `docker-wrapper.sh` calling it for non-DS01 containers?
4. Is the cgroup path in `check-limits` correct?
5. Are we looking in the right cgroup hierarchy (v1 vs v2)?

## Likely Root Causes

1. `create-user-slice.sh` not being called from docker-wrapper
2. Cgroup path mismatch between creation and check-limits lookup
3. Systemd slice created but containers not using `--cgroup-parent`
4. cgroup v1/v2 hybrid mode confusion

## Solution

Ensure ALL container creation paths create the user slice:
1. Audit docker-wrapper.sh to ensure it calls create-user-slice
2. Verify cgroup-parent is injected for all container types
3. Fix path lookup in check-limits to match actual slice location
4. Add logging to diagnose slice creation failures
