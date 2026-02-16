---
phase: 07-label-standards-migration
plan: 01
subsystem: container-metadata
tags: [labels, namespace-migration, backward-compatibility]
dependency_graph:
  requires: []
  provides:
    - ds01.* label namespace
    - label-schema.yaml (authoritative)
    - ownership fallback functions
  affects:
    - mlc-patched.py (all new containers)
    - container creation workflow
    - ownership detection
tech_stack:
  added: [config/label-schema.yaml]
  patterns: [backward-compatible-migration, authoritative-schema]
key_files:
  created:
    - config/label-schema.yaml
  modified:
    - scripts/docker/mlc-patched.py
    - scripts/lib/ds01_core.py
    - scripts/lib/docker-utils.sh
decisions:
  - Lowercase label names (ds01.user not ds01.USER) for consistency with Docker conventions
  - Single ds01.user label replaces both aime.mlc (bare) and aime.mlc.USER
  - Fallback functions in shared libraries (not inline in each script)
  - TODO comments mark fallback code for future removal
  - Label schema as authoritative YAML document (not code comments)
metrics:
  duration_minutes: 3
  completed_date: 2026-02-16
  tasks_completed: 2
  files_modified: 4
  commits: 2
---

# Phase 07 Plan 01: Label Namespace Migration Summary

**One-liner:** Migrated mlc-patched.py from aime.mlc.* to ds01.* label namespace with backward-compatible fallback functions and authoritative schema document.

## What Was Accomplished

### Task 1: Label Schema and mlc-patched.py Migration (Commit: 449f3d8)

**Created authoritative label schema** (`config/label-schema.yaml`):
- Complete ds01.* namespace definition (32 labels documented)
- Migration mapping from aime.mlc.* to ds01.* labels
- Description, type, set_by, example for each label
- Version 1.0 with migration notes

**Patched mlc-patched.py** (root label generation fix):
- Changed `container_label = "aime.mlc"` → `container_label = "ds01"`
- Updated all label names to lowercase: `.USER` → `.user`, `.NAME` → `.name`, etc.
- Consolidated duplicate labels: removed bare `{container_label}={user_name}` since `ds01.user` now serves that purpose
- Updated all internal references (12 locations):
  - Filter statements: `label=aime.mlc` → `label=ds01.user`
  - `columns_transcription` dict: all label references updated
  - Image inspect labels: `aime.mlc.DS01_*` → `ds01.*`
  - Variable name: `filter_aime_mlc_user` → `filter_ds01_user`
  - Comments updated to reflect new namespace
- Result: **1 aime.mlc reference remaining** (in migration comment explaining Phase 7 change)

**Verification:** All Python syntax valid, container_label correctly set to "ds01", label schema parses as valid YAML.

### Task 2: Ownership Fallback Functions (Commit: 80d5e80)

**Added Python fallback functions** to `ds01_core.py`:
- `get_container_owner_from_labels(labels)`: checks ds01.user → aime.mlc.USER → None
- `get_container_managed_from_labels(labels)`: checks ds01.managed → aime.mlc.DS01_MANAGED
- Both include docstrings, type hints, examples, and TODO comments for future removal
- Updated module docstring to document new functions

**Enhanced Bash fallback** in `docker-utils.sh`:
- Verified existing `ds01_get_container_owner()` implements correct fallback pattern
- Added TODO comment marking aime.mlc.USER fallback for future removal
- No functional changes needed (already correct)

**Verification:** Functions compile, ds01.user works, aime.mlc.USER fallback works, TODO comments present.

## Impact

**Immediate:**
- All containers created by mlc-patched.py after Phase 7 deployment use ds01.* labels
- Legacy containers (aime.mlc.*) continue to work via fallback functions
- Single source of truth for label namespace (config/label-schema.yaml)

**Future cleanup** (when no legacy containers remain):
- Remove aime.mlc.* fallback logic from ds01_core.py
- Remove aime.mlc.* fallback logic from docker-utils.sh
- Check: `docker ps --filter label=aime.mlc.USER` should return nothing

**Scripts requiring updates** (Plan 02):
- docker-wrapper.sh (already uses ds01.*)
- mlc-create-from-image.sh (writes aime.mlc.DS01_* labels)
- Scripts that read labels (container-list, container-info, lifecycle enforcement, etc.)

## Deviations from Plan

None — plan executed exactly as written.

## Technical Decisions

**1. Lowercase label names** — ds01.user not ds01.USER
- **Rationale:** Docker label conventions use lowercase (devcontainer.local_folder, com.docker.compose.project). Consistent with ecosystem standards.
- **Impact:** All label accessors updated. No breaking change (new namespace).

**2. Single ds01.user label** — not both ds01 (bare) and ds01.user
- **Rationale:** Original aime.mlc had both `aime.mlc=username` (bare) and `aime.mlc.USER=username` (explicit). Redundant duplication.
- **Decision:** Consolidate to single `ds01.user` label.
- **Impact:** Filter statements use `label=ds01.user` instead of `label=ds01` (bare).

**3. Fallback in shared libraries** — not inline in each script
- **Rationale:** DRY principle. 10+ scripts read ownership labels. Centralising fallback logic in ds01_core.py and docker-utils.sh provides single update point for future removal.
- **Pattern:** `from ds01_core import get_container_owner_from_labels` — one import, consistent behavior.

**4. TODO comments with verification command**
- **Rationale:** Future developers need to know when it's safe to remove fallback code.
- **Pattern:** Include check command in TODO: `docker ps --filter label=aime.mlc.USER` should return nothing.

**5. Authoritative schema as YAML** — not code comments or wiki
- **Rationale:** Machine-readable, version-controlled, single source of truth. Can be used by validation tools, documentation generators, linters.
- **Future:** Could add schema validation to pre-commit hooks.

## Files Modified

| File | Lines Changed | Purpose |
|------|---------------|---------|
| config/label-schema.yaml | +278 | Authoritative ds01.* namespace definition |
| scripts/docker/mlc-patched.py | +39/-39 | Root label generation (aime.mlc.* → ds01.*) |
| scripts/lib/ds01_core.py | +56/-1 | Python ownership fallback functions |
| scripts/lib/docker-utils.sh | +2/0 | TODO comment for Bash fallback |

**Total:** 4 files, 375 lines changed, 2 atomic commits.

## Verification Results

```
✓ mlc-patched.py compiles cleanly
✓ ds01_core.py compiles cleanly
✓ No aime.mlc references remain (1 in migration comment only)
✓ Label schema exists and parses as valid YAML
✓ container_label = "ds01"
✓ Python fallback function works (ds01.user)
✓ Python fallback function works (aime.mlc.USER legacy)
✓ Bash fallback function has TODO comment
```

All success criteria met.

## Next Steps (Plan 02)

**Update downstream label consumers:**
1. docker-wrapper.sh — verify ds01.* usage (already correct)
2. mlc-create-from-image.sh — migrate aime.mlc.DS01_* to ds01.*
3. Container lifecycle scripts — add fallback support
4. User-facing scripts (container-list, container-info) — add fallback
5. Documentation updates for user scripts

**Testing strategy:**
- Create test container with mlc-patched.py → verify ds01.* labels
- Check legacy container (if any exist) → verify fallback works
- Run full UAT suite from Phase 7 verification

## Self-Check: PASSED

**Created files exist:**
```bash
✓ config/label-schema.yaml exists
```

**Commits exist:**
```bash
✓ 449f3d8 exists (Task 1: label schema + mlc-patched.py)
✓ 80d5e80 exists (Task 2: fallback functions)
```

**Modified files have expected changes:**
```bash
✓ scripts/docker/mlc-patched.py contains 'container_label = "ds01"'
✓ scripts/lib/ds01_core.py contains 'get_container_owner_from_labels'
✓ scripts/lib/docker-utils.sh contains TODO comment
```

All artifacts verified present and functional.
