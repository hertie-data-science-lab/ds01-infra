#!/bin/bash
# Pre-commit guard: block commits when root-owned files appear at the repo root.
#
# Catches the #56 failure mode, where a `sudo tee <path> chmod 600 <path>` typo
# made `tee` scatter a secret into stray root-owned files (`sudo`, `chmod`, `600`)
# at the repo root. Wired in as a `language: system` pre-commit hook.
set -euo pipefail

bad="$(find . -maxdepth 1 -user root -not -path "./.git" -print 2>/dev/null || true)"
if [ -n "$bad" ]; then
    echo "Root-owned files at the repo root (possible leaked-secret / sudo accident):" >&2
    echo "$bad" >&2
    echo "Remove them (use 'shred' if they may hold a secret) before committing." >&2
    exit 1
fi
