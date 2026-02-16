---
created: 2026-02-16T18:00
title: Verify Phase 7 (Label Standards & Migration)
area: verification
files: []
---

After executing Phase 7, run `/gsd:verify-work` to UAT:

- All new containers created via DS01 commands receive `ds01.*` labels (not `aime.mlc.*`)
- Existing containers with `aime.mlc.*` labels continue working via ownership fallback
- Monitoring and cleanup scripts handle both `ds01.*` and `aime.mlc.*` label schemes
- Label schema document (`config/label-schema.yaml`) is complete and accurate
- No non-fallback `aime.mlc.*` references remain in scripts
