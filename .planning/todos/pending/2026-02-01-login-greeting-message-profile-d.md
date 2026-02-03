---
created: 2026-02-01T00:15
title: Add login greeting/welcome message via profile.d
area: tooling
files:
  - config/deploy/profile.d/ds01-gpu-awareness.sh
---

## Problem

Users logging into DS01 get no greeting or orientation. A brief welcome message
on login via profile.d would help users understand they're on a managed GPU server
and point them towards key commands (container deploy, dashboard, etc.).

## Solution

Add a short greeting block to an existing or new profile.d script. Keep it to 2-3
lines max — system name, brief orientation, and a pointer to help. Don't duplicate
the GPU notice (that's handled contextually in ds01-gpu-awareness.sh when python3
is invoked). Could be a separate `ds01-welcome.sh` in profile.d to keep concerns
separated from the GPU awareness script.
