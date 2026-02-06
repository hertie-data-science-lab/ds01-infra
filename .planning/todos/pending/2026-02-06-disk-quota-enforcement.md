---
created: 2026-02-06T15:09
title: Disk quota enforcement (requires XFS migration)
area: enforcement
files:
  - config/runtime/resource-limits.yaml
  - .planning/phases/04-comprehensive-resource-enforcement/04-CONTEXT.md:86-91
---

## Problem

Phase 4 deferred disk quota enforcement (ENFORCE-04) because the server uses ext4 on a single 3.5TB NVMe. Kernel-level per-user/per-project disk quotas require XFS project quotas, which need an XFS filesystem.

Without disk quotas, a single user can fill the entire NVMe with Docker images, build caches, or training data — causing outages for all users.

## Solution

Three options (in order of capability):

1. **XFS migration** (best) — Reformat storage partition to XFS, enable project quotas. Requires downtime and data migration. Enables per-user AND per-container disk limits via cgroup v2 io controller.
2. **ext4 user/group quotas** (simpler) — Enable quota support on existing ext4. Less capable (no per-project/per-container quotas), but no reformatting needed.
3. **Software-based tracking** (easiest) — Periodic `du` scans with alerting when users exceed thresholds. No kernel enforcement, just visibility + warnings.

Needs an infrastructure prerequisite phase (XFS migration) before full enforcement. Could start with option 3 as interim measure.
