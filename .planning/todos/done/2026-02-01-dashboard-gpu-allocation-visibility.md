# Bug: Dashboard Not Showing GPU Allocations

## Summary

`dashboard` command does not show GPU allocations for deployed containers, but `gpu-availability-checker.py summary` correctly reports them (e.g. 1/4 allocated at 25%). The data exists — the dashboard just isn't reading it.

## Symptoms

- `container deploy` as h.baker succeeds, container running with GPU
- `gpu-availability-checker.py summary` shows 1/4 allocated (correct)
- `gpu_allocator_v2.py status` shows allocation with UUID (correct)
- `dashboard` does not show the GPU allocation

## Likely Cause

Dashboard may be reading GPU state from a different source than the allocator, or the display logic has a bug after recent changes. Needs audit of:
- How dashboard reads GPU state (does it call nvidia-smi directly? read state files? call allocator?)
- Whether the docker wrapper isolation filtering affects what dashboard sees
- Whether label changes from Phase 3.1 affect dashboard container detection

## Related

- Recent changes: nvidia-smi wrapper removed, video group restored, GPU inventory cache added
- Files: `scripts/admin/dashboard`, `scripts/docker/gpu-state-reader.py`, `scripts/docker/gpu_allocator_v2.py`

## Scope

This should be part of a broader audit of the logging/monitoring/dashboard system to ensure consistency after Phase 3.1 changes. Not just a point fix — verify the whole observation chain works end-to-end.

## Priority

Medium — functional impact but not blocking. GPU allocation works correctly, just not visible in dashboard.
