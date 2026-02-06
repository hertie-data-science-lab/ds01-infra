---
created: 2026-02-06T15:09
title: Network bandwidth limits (future multi-node)
area: enforcement
files:
  - .planning/phases/04-comprehensive-resource-enforcement/04-CONTEXT.md:103-105
---

## Problem

No per-user network bandwidth limits. Currently not relevant for single-server setup, but would matter if distributed training across servers is added or if users saturate the network link downloading large datasets.

## Solution

TBD — Not relevant until multi-node or network contention emerges. Options when needed:
- tc (traffic control) rules per user/cgroup
- Docker network bandwidth limits
- Switch-level QoS if hardware supports it
