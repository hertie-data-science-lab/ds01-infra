---
created: 2026-02-16T17:17
title: Add ds01-users command to admin aliases
area: tooling
files:
  - config/container-aliases.sh
  - scripts/admin/ds01-users
---

## Problem

The `ds01-users` command is not included in the `--admin` aliases set. Admin users need to type the full path or know about the command separately.

## Solution

Add `ds01-users` to the admin aliases section in `config/container-aliases.sh` so it's available when users have admin access.
