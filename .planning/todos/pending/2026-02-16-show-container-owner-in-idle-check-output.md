---
created: 2026-02-16T17:20
title: Show container owner in idle check output
area: tooling
files:
  - scripts/monitoring/check-idle-containers.sh
---

## Problem

The idle container checker logs container names like `test._.1722830498` without showing the owner. Admins have to mentally map UID suffixes to usernames. Output like "Container test._.1722830498 within grace period" should say "Container test._.1722830498 (h.baker) within grace period".

## Solution

Look up `ds01.user` label (with `aime.mlc.USER` fallback) for each container and include the owner name in log output.
