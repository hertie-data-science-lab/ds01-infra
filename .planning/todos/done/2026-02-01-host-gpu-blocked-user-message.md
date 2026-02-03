---
created: 2026-02-01T00:15
title: Add login message when host CUDA is blocked
area: tooling
files:
  - config/deploy/profile.d/ds01-gpu-awareness.sh
---

## Problem

When CUDA_VISIBLE_DEVICES="" blocks host GPU access, users get no explanation.
`torch.cuda.is_available()` silently returns False. Users don't know why or what
to do instead. Need a brief, non-annoying notification on login.

## Solution

Add a short message to the profile.d script for non-exempt users:

```bash
echo "GPU workloads run in containers. Use: container deploy <name>"
```

Keep it to one line. Don't use wall broadcasts. Just a quiet login hint.
