#!/usr/bin/env bash
# === METADATA ===
# NAME: sync-downstream
# TYPE: utility
# DESCRIPTION: Sync full repo (including git-excluded files) to downstream remote
# ================

# Syncs all files — including .planning/, .product/, hb_learning/, CLAUDE.md,
# .dotconfigs/ — to the private downstream remote using git plumbing.
# Does not affect the working tree or main index.
# Designed to run silently in the background from git hooks.

set -euo pipefail

# Detached-prod backup: prod (/opt/ds01-infra) has no .git, so drive git with
# the STAGING clone's repo (--git-dir) against the PROD work-tree. That keeps
# force-adding the prod-only, git-ignored runtime state (config/runtime/*
# members/overrides, teams-webhook-url.txt, .planning, ...) that a dev clone or
# staging never has — so downstream stays a complete backup.
#
# The prod post-commit hook no longer exists (no .git in prod); this is driven
# by cron/timer (see config/deploy/cron.d/ds01-maintenance) as the checkout
# owner (datasciencelab) for SSH auth + ownership.
#
# Requires: the staging clone has a 'downstream' remote configured.

REPO_DIR="/opt/ds01-infra"               # work-tree (live prod)
STAGING_GIT_DIR="/opt/ds01-staging/.git" # repo (staging clone)
REMOTE="downstream"
BRANCH="main"
LOG_FILE="/tmp/ds01-sync-downstream.log"

# Redirect all output to log (silent when run from cron/timer)
exec >>"$LOG_FILE" 2>&1
echo "--- sync started: $(date -Iseconds) ---"

if [ ! -d "$STAGING_GIT_DIR" ]; then
    echo "staging repo $STAGING_GIT_DIR not found — skipping"
    exit 0
fi

# Drive all git commands against the staging repo with the prod work-tree.
export GIT_DIR="$STAGING_GIT_DIR"
export GIT_WORK_TREE="$REPO_DIR"

if ! git remote get-url "$REMOTE" >/dev/null 2>&1; then
    echo "remote '$REMOTE' not configured in staging — skipping (add it at cutover)"
    exit 0
fi

cd "$REPO_DIR"

# Use a temporary index to avoid touching the real one
TEMP_INDEX=$(mktemp)
export GIT_INDEX_FILE="$TEMP_INDEX"
trap 'rm -f "$TEMP_INDEX"' EXIT

# Start with the current HEAD tree (all tracked files)
git read-tree HEAD

# Force-add dev/planning artifacts kept out of the org repo.
for path in .planning .product hb_learning .dotconfigs; do
    if [ -e "$path" ]; then
        git add --force "$path"
    fi
done

# Force-add per-user data so the full/downstream repo keeps a complete copy.
# .gitignore is the single source of truth: whatever it git-excludes under
# config/runtime/ is data the org repo drops but downstream must retain.
git ls-files -z --others --ignored --exclude-standard -- config/runtime |
    while IFS= read -r -d '' path; do
        git add --force "$path"
    done

# Add all CLAUDE.md and claude_*.md files anywhere in the repo
find . -maxdepth 5 \( -name "CLAUDE.md" -o -name "claude_*.md" \) \
    -not -path "./.git/*" -exec git add --force {} + 2>/dev/null || true

# Create tree object from the combined index
TREE=$(git write-tree)

# Fetch latest downstream state (quiet, tolerate failure)
git fetch "$REMOTE" --quiet 2>/dev/null || true

# Get the current downstream branch HEAD as parent (if it exists)
PARENT=$(git rev-parse "$REMOTE/$BRANCH" 2>/dev/null) || PARENT=""

# Skip if tree is identical to last sync (no changes)
if [ -n "$PARENT" ]; then
    PARENT_TREE=$(git rev-parse "${PARENT}^{tree}" 2>/dev/null) || PARENT_TREE=""
    if [ "$TREE" = "$PARENT_TREE" ]; then
        echo "no changes — skipping"
        exit 0
    fi
fi

# Build commit message from the latest source commit
SOURCE_MSG=$(git log -1 --format='%s' HEAD)
SOURCE_SHA=$(git rev-parse --short HEAD)
COMMIT_MSG="sync: ${SOURCE_MSG} (${SOURCE_SHA})"

# Create commit object (with parent if one exists)
if [ -n "$PARENT" ]; then
    COMMIT=$(echo "$COMMIT_MSG" | git commit-tree "$TREE" -p "$PARENT")
else
    COMMIT=$(echo "$COMMIT_MSG" | git commit-tree "$TREE")
fi

# Push to downstream
if git push "$REMOTE" "$COMMIT:refs/heads/$BRANCH" --quiet 2>&1; then
    echo "pushed $COMMIT to $REMOTE/$BRANCH"
else
    echo "push failed (network issue?) — will retry next commit"
fi
