# CI/CD Pipeline

## Overview

Two-tier CI with path-based filtering, local development mirror via Makefile, manual tag-triggered releases, and automated dependency updates.

| Workflow | File | Trigger | Purpose |
|----------|------|---------|---------|
| CI | `ci.yml` | PR to main, dispatch | Tier 1 — lint + test on every PR |
| System CI | `ci-system.yml` | Nightly 03:00 UTC, dispatch, callable | Tier 2 — full suite on GPU hardware |
| Release | `release.yml` | Tag push `v*.*.*`, dispatch | Create GitHub Release |
| Docs sync | `sync-docs-to-hub.yml` | Push to main (docs changes), dispatch | Sync docs-user/ to ds01-hub |

All workflows support `workflow_dispatch` for manual triggering.

## Tier 1: CI (`ci.yml`)

Runs on every PR to main. Uses [dorny/paths-filter](https://github.com/dorny/paths-filter) to skip irrelevant jobs — a docs-only PR runs nothing; a Python-only change skips shell checks.

**Jobs:**

| Job | Condition | What it does | ~Time |
|-----|-----------|-------------|-------|
| Detect changes | Always | Path filter → outputs `python`, `shell`, `workflows` | 7s |
| Ruff | Python changed | `ruff format --check` + `ruff check` via [astral-sh/ruff-action](https://github.com/astral-sh/ruff-action) | 7s |
| Shell format | Shell changed | `shfmt -d -i 4 -ci -s` via [mfinelli/setup-shfmt](https://github.com/mfinelli/setup-shfmt) | 4s |
| Shellcheck | Shell changed | `shellcheck -x -S warning` on all scripts | 12s |
| Tests | Python or shell changed | `pytest -m "not system"` (unit + integration) | 19s |
| Lint workflows | Workflows changed | [actionlint](https://github.com/rhysd/actionlint) on workflow YAML | 13s |
| **CI** | **Always** | **Gate job — passes if all above pass or skip** | 3s |

**Branch protection** requires the single `CI` gate job. Individual jobs can be skipped by path filtering without blocking the PR.

**Concurrency:** Cancels previous runs on the same PR branch (`ci-${{ github.ref }}`).

### Path filter groups

| Group | Patterns |
|-------|----------|
| `python` | `**/*.py`, `pyproject.toml` |
| `shell` | `scripts/**`, `.shellcheckrc` |
| `workflows` | `.github/workflows/**` |

## Tier 2: System CI (`ci-system.yml`)

Runs nightly at 03:00 UTC on the self-hosted GPU runner (`[self-hosted, linux, gpu]`). Executes the **full** test suite with no marker filter — a superset of Tier 1 plus the 32 system tests requiring real Docker, GPU, and sudo.

```bash
sudo /home/datasciencelab/anaconda3/bin/python -m pytest . -v --tb=short
```

On failure: checks for an existing open issue before creating a new one. If one exists, adds a comment instead.

Also supports `workflow_call` for use as a release gate if needed.

## Release (`release.yml`)

Manual tag-triggered releases. No automated semantic-release.

### Release process

1. Update the `VERSION` file with the new version (e.g. `1.5.0`)
2. Commit: `chore: bump version to 1.5.0`
3. Tag and push:
   ```bash
   git tag v1.5.0
   git push --tags
   ```
4. Workflow validates:
   - Tag matches semver format (`vX.Y.Z`)
   - `VERSION` file matches the tag
5. Creates GitHub Release with auto-generated notes

Can also be triggered via dispatch (enter tag manually).

## Dependabot (`.github/dependabot.yml`)

Monthly updates, grouped as single PRs:

| Ecosystem | What it updates | Schedule |
|-----------|----------------|----------|
| `github-actions` | Action versions in workflows | Monthly (Monday 06:00 CET) |
| `pip` | Python dependencies (pytest, pyyaml, ruff) | Monthly (Monday 06:00 CET) |

Minor + patch updates are grouped into a single PR per ecosystem.

## Local development

### Makefile

The Makefile mirrors CI locally. All developers should run `make check` before pushing.

```bash
make help          # Show all targets
make check         # Full CI locally (lint + test)
make lint          # lint-python + lint-shell
make fmt           # Auto-format everything (ruff + shfmt)
make test          # pytest -m "not system" (unit + integration)
make test-all      # sudo pytest (all tiers including system)
```

### Pre-commit hooks (`.pre-commit-config.yaml`)

Installed with `pre-commit install --hook-type commit-msg`. Runs automatically on `git commit`.

| Hook | What it does |
|------|-------------|
| `validate-commit-message` | Conventional commit format + blocks AI attribution |
| `trailing-whitespace` | Removes trailing whitespace |
| `end-of-file-fixer` | Ensures files end with newline |
| `check-yaml` | Validates YAML syntax |
| `check-added-large-files` | Blocks files > 500KB |
| `check-merge-conflict` | Detects merge conflict markers |
| `check-executables-have-shebangs` | Shell script validation |
| `no-commit-to-branch` | Prevents direct commits to main |
| `shellcheck` | Shell script linting (`-x` flag) |
| `shfmt` | Shell formatting (`-i 4 -ci -s`) |
| `ruff` | Python linting + auto-fix |
| `ruff-format` | Python formatting |

## Configuration files

| File | Purpose |
|------|---------|
| `.shellcheckrc` | Shellcheck suppressions (SC1090, SC1091, SC2154, SC2034, SC2155) |
| `.github/actionlint.yaml` | Declares `gpu` as valid self-hosted runner label |
| `pyproject.toml` | Ruff config (line-length 100, py310, isort) |

### Shellcheck suppressions

| Code | Reason |
|------|--------|
| SC1090 | Can't follow non-constant source (dynamic paths) |
| SC1091 | Not following sourced files (unavailable at check time) |
| SC2154 | Variable referenced but not assigned (set via sourced init scripts) |
| SC2034 | Variable appears unused (used by callers of sourced libraries) |
| SC2155 | Declare and assign separately (pervasive `local var=$(cmd)` pattern) |

## Test structure

Three tiers, mapped to CI:

| Tier | Directory | Count | Marker | Runs in |
|------|-----------|-------|--------|---------|
| Unit | `testing/unit/` | 648 | `unit` | Tier 1 + Tier 2 |
| Integration | `testing/integration/` | 143 | `integration` | Tier 1 + Tier 2 |
| System | `testing/system/` | 32 | `system` | Tier 2 only |

Tier 1 runs `pytest -m "not system"` (791 tests). Tier 2 runs everything (823 tests).

See [testing/README.md](../testing/README.md) for test details.

## Troubleshooting

### CI gate job fails but individual jobs passed

Check if any individual job was *cancelled* (not just skipped). The gate job treats both `failure` and `cancelled` as failures.

### Shellcheck fails on new code

Run locally: `make lint-shell`. Shellcheck reads `.shellcheckrc` for suppressions. If you get SC2155 (declare and assign separately), it's suppressed — ensure `.shellcheckrc` is present.

### shfmt fails

Run `make fmt-shell` to auto-format, then commit the changes.

### Tests fail locally but pass in CI

CI runs on Ubuntu with Python 3.13. Locally you may be using conda. Ensure pytest and pyyaml are installed in your active Python environment.

### Nightly system CI creates duplicate issues

It shouldn't — the workflow checks for existing open issues with "System CI failed" before creating new ones. If duplicates appear, check the `gh issue list --search` logic in `ci-system.yml`.
