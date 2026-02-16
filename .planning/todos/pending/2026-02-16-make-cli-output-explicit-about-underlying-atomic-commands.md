---
created: 2026-02-16T16:42
title: Make CLI output explicit about underlying atomic commands
area: tooling
files:
  - scripts/user/orchestrators/container-deploy
  - scripts/user/orchestrators/container-retire
  - scripts/user/dispatchers/*
---

## Problem

When running orchestrator commands like `container deploy`, the output doesn't clearly show which atomic commands are being invoked underneath. For example, `container deploy` calls `container-create` and `mlc-create-wrapper` but the user sees a stream of `[INFO]` messages without clear boundaries between which subsystem is producing them.

This makes it hard for users (and admins debugging) to understand the pipeline: which atomic command is running, what step they're at, and where a failure occurred in the chain.

## Solution

TBD — needs careful design. General direction:

- Orchestrators should clearly announce which atomic commands they're calling (e.g. "Running: container-create ...")
- Consider a consistent output format that shows the command pipeline
- Balance between verbose transparency and clean UX — don't overwhelm
- May want different verbosity levels (default vs --verbose)
- Review ds01-UI_UX_GUIDE.md standards before implementing
- Consider this as part of a broader CLI UX improvement pass
