---
created: 2026-02-06T15:09
title: I/O bandwidth enforcement (requires BFQ scheduler)
area: enforcement
files:
  - .planning/phases/04-comprehensive-resource-enforcement/04-CONTEXT.md:93-97
---

## Problem

Phase 4 deferred I/O bandwidth enforcement because the NVMe uses the mq-deadline scheduler. The cgroup v2 `io.weight` controller requires the BFQ (Budget Fair Queueing) scheduler to be effective.

Currently no per-user I/O limits — a user running heavy disk operations (large dataset loading, checkpoint writes) could starve other users' I/O.

## Solution

1. Evaluate whether I/O contention is actually occurring (~10 active users, NVMe bandwidth is high)
2. If needed, switch NVMe scheduler from mq-deadline to BFQ (may reduce peak throughput)
3. Add `io_weight` to resource-limits.yaml aggregate sections
4. Generate systemd drop-in with IOWeight directives

Revisit only if I/O contention emerges as an actual problem — NVMe bandwidth unlikely to be bottleneck at current scale.
