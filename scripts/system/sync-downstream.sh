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

REPO_DIR="/opt/ds01-infra"
REMOTE="downstream"
BRANCH=$(git -C "$REPO_DIR" rev-parse --abbrev-ref HEAD 2>/dev/null || echo "main")
LOG_FILE="/tmp/ds01-sync-downstream.log"

# Redirect all output to log (silent when run from hooks)
exec >>"$LOG_FILE" 2>&1
echo "--- sync started: $(date -Iseconds) branch=$BRANCH ---"

cd "$REPO_DIR"

# Use a temporary index to avoid touching the real one
TEMP_INDEX=$(mktemp)
export GIT_INDEX_FILE="$TEMP_INDEX"
trap 'rm -f "$TEMP_INDEX"' EXIT

# Start with the current HEAD tree (all tracked files)
git read-tree HEAD

# Force-add all excluded directories and files
for path in .planning .product hb_learning .dotconfigs; do
    if [ -e "$path" ]; then
        git add --force "$path"
    fi
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
