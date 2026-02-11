---
created: 2026-02-11T20:15
title: Review and configure CI/CD pipelines
area: tooling
files:
  - .github/workflows/lint.yml.disabled
  - .github/workflows/release.yml.disabled
  - .github/workflows/sync-docs-to-hub.yml.disabled
---

## Problem

Three GitHub Actions workflows were discovered running on the repo, currently disabled
(renamed to .disabled) because the release pipeline was auto-creating version tag commits
(`chore(release): 1.0.0 [skip ci]`) on every push to main without review.

Workflows:
1. `lint.yml` — runs on PRs to main
2. `release.yml` — runs on push to main (semantic-release, creates version commits)
3. `sync-docs-to-hub.yml` — runs on push to main (syncs docs to ds01-hub repo)

Need to understand what each does, decide what to keep, and configure properly
before re-enabling. The release pipeline in particular needs review — it may be
creating unwanted commits and tags.

## Solution

TBD — review each workflow file, decide on keep/modify/remove per pipeline.
