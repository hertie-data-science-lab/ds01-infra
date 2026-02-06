---
created: 2026-02-06T15:09
title: Fair-share GPU scheduling based on historical usage
area: enforcement
files:
  - .planning/phases/04-comprehensive-resource-enforcement/04-CONTEXT.md:99-101
---

## Problem

Current GPU allocation is first-come-first-served. Users who monopolise GPUs continuously get the same priority as users who rarely use them. No fairness mechanism exists.

SLURM-style fair-share scheduling uses historical GPU-hours to adjust priority — users who've consumed more recently get lower priority when GPUs are contested.

## Solution

TBD — Deferred from Phase 4 per research recommendations. Would need:
- Historical GPU usage tracking (partially available via event log)
- Priority scoring algorithm based on usage window (e.g., 7-day rolling)
- Integration with GPU allocator to prefer lower-usage users when contested
- Likely relevant when SLURM integration begins (Milestone 4)
