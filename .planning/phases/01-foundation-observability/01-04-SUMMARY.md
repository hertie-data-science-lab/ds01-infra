---
phase: 01-foundation-observability
plan: 04
subsystem: infra
tags: [semantic-release, github-actions, ruff, ci-cd, automation]

# Dependency graph
requires:
  - phase: project-setup
    provides: Git repository with conventional commits
provides:
  - Automated semantic versioning via semantic-release on merge to main
  - Auto-generated CHANGELOG.md from conventional commits
  - GitHub releases with version tags (vMAJOR.MINOR.PATCH)
  - Ruff linting enforcement on all PRs to main
affects: [all future development - enforces code quality and release automation]

# Tech tracking
tech-stack:
  added: [semantic-release, @semantic-release/changelog, @semantic-release/git, @semantic-release/exec]
  patterns: [semantic versioning, automated releases, pre-commit linting]

key-files:
  created:
    - .github/workflows/lint.yml
    - .releaserc.json
  modified:
    - .github/workflows/release.yml

key-decisions:
  - "Replaced commitizen with semantic-release for more robust automation"
  - "Semantic-release triggers automatically on push to main (not manual workflow_dispatch only)"
  - "Ruff linting runs on PRs affecting Python files or pyproject.toml"

patterns-established:
  - "Release workflow: automatic on merge, generates changelog, creates GitHub release"
  - "PR gating: ruff format check + ruff lint must pass"

# Metrics
duration: 1min
completed: 2026-01-30
---

# Phase 01 Plan 04: Automated Release & Linting Summary

**Semantic-release with auto-trigger on main merges, ruff linting on PRs, and CHANGELOG.md auto-generation**

## Performance

- **Duration:** 1 minute
- **Started:** 2026-01-30T13:13:56Z
- **Completed:** 2026-01-30T13:15:04Z
- **Tasks:** 2
- **Files modified:** 3

## Accomplishments
- Replaced fragile commitizen workflow with robust semantic-release automation
- Auto-trigger releases on push to main (conventional commits determine version bump)
- Added ruff linting workflow that runs on all PRs to main
- CHANGELOG.md and VERSION file auto-generated on each release

## Task Commits

Each task was committed atomically:

1. **Task 1: Replace release workflow with semantic-release** - `237cc15` (feat)
2. **Task 2: Create ruff linting workflow for PRs** - `53de7b0` (feat)

## Files Created/Modified
- `.github/workflows/release.yml` - Semantic-release workflow with auto-trigger on main push
- `.releaserc.json` - Semantic-release configuration with 6 plugins
- `.github/workflows/lint.yml` - Ruff linting workflow for PRs to main

## Decisions Made

**Replaced commitizen with semantic-release:**
- Previous workflow required manual trigger (workflow_dispatch only)
- Semantic-release provides automatic versioning on every merge to main
- More robust commit analysis via @semantic-release/commit-analyzer
- Auto-generates CHANGELOG.md and GitHub releases without manual intervention

**Preserved dry-run capability:**
- Manual workflow_dispatch option retained for testing
- Dry-run mode previews changes without releasing

**Ruff on PRs only:**
- Linting runs on pull requests to main, not on every push
- Only triggers when Python files or pyproject.toml change (efficient)

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None - straightforward workflow replacement.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness

**Ready for:**
- Any future phase merging to main will automatically trigger versioning
- All PRs will be linted before merge
- CHANGELOG.md will continuously track changes

**Notes:**
- First semantic-release run will analyze all commits since last tag
- VERSION file will be created on first release
- Pre-commit hook already enforces conventional commits locally

---
*Phase: 01-foundation-observability*
*Completed: 2026-01-30*
