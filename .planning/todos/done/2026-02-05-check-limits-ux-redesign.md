---
created: 2026-02-05T18:05
title: Redesign check-limits UX with cli-ux-designer
area: ux
files:
  - scripts/user/helpers/check-limits
---

## Problem

`check-limits` output needs UX improvements:
1. "Memory" and "Tasks" are technical — need more explanation and units
2. Organisation could be better — group by resource type (GPUs, CPUs, Memory, etc.)
3. Per-container vs total limits not clearly distinguished
4. "(No active containers - cgroup not yet created)" message is confusing

## Solution

Use cli-ux-designer agent for iterative Q&A design sessions to:
1. Reorganise display by resource type:
   - GPUs (total quota + per-container limit)
   - CPUs (total quota + per-container limit)
   - Memory (total quota + per-container limit, with units like "64 GB")
   - PIDs/Tasks (explain what this means, show units)
2. Add clear explanations for technical terms
3. Improve progress bar labels
4. Consider --verbose vs --brief modes

## Design Questions to Explore

- Should we show "what you could run" vs "what you're using"?
- How to handle users with unlimited quotas?
- Should storage quota be integrated or separate?
- Mobile-friendly output width?
