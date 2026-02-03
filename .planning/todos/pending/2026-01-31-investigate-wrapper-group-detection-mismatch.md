---
created: 2026-01-31T22:58
title: Investigate wrapper group detection mismatch
area: tooling
files:
  - scripts/docker/mlc-create-wrapper.sh:419
  - scripts/docker/get_resource_limits.py
  - config/resource-limits.yaml
---

## Problem

During hbaker's container deploy, the mlc-create-wrapper applied **student** resource limits (32 CPU, 32g RAM, `ds01-student-h_baker.slice`) even though `h.baker@hertie-school.lan` is in the researcher group (should get 48 CPU, 64g RAM, `ds01-researcher-h_baker.slice`).

Running `get_resource_limits.py 'h.baker@hertie-school.lan'` directly returns the correct researcher group. So the discrepancy is in how the wrapper calls the resource parser or resolves group membership.

Evidence from deploy output:
```
[INFO] Resource limits applied:
  --cpus=32
  --memory=32g
  --cgroup-parent=ds01-student-h_baker.slice
[INFO] Allocating GPU via gpu_allocator_v2.py (priority: 10, max: 3)...
```

Expected: cpus=48, memory=64g, ds01-researcher-h_baker.slice, max: 6

The wrapper reads MAX_GPUS via `python3 "$RESOURCE_PARSER" "$CURRENT_USER" --max-gpus` — need to check what CURRENT_USER resolves to and whether the --max-gpus flag path has the same group resolution as the default output.

## Solution

TBD — investigate how CURRENT_USER is set in the wrapper and whether the resource parser's --max-gpus code path uses the same group membership files as the default output. May be a quoting issue with the @ in the username, or the wrapper may read group config differently from get_resource_limits.py.
