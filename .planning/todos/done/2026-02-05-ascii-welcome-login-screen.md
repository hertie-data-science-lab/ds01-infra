---
created: 2026-02-05T18:05
title: Design ASCII welcome login screen for DS01
area: ux
files:
  - config/deploy/profile.d/ds01-login-greeting.sh
---

## Problem

The login greeting currently shows a simple one-liner:
```
DS01 Resource Quota — h.baker@hertie-school.lan (unknown): unlimited
```

This is functional but misses an opportunity for a proper branded welcome experience like what we have with `user-setup`.

## Solution

Design a proper ASCII art welcome screen for DS01 login, similar to the style in user-setup. Should be:
- Visually appealing but not overwhelming (3-5 lines max)
- Show key info at a glance (user, group, quota summary)
- Consistent with DS01 branding
- Fast to render (no slow operations on login)

## Notes

- Consider using cli-ux-designer agent for iterative design
- May want different verbosity levels (first login vs returning user)
- The "(unknown)" group display is a separate bug to fix
