#!/usr/bin/env bash
# install-prod-git-guards.sh — activate the repo-owned git guard hooks on THIS
# checkout by pointing core.hooksPath at the tracked .githooks/ directory.
#
# The guards (see .githooks/) refuse commits/rebases and warn on branch switches
# when the checkout is the production dir /opt/ds01-infra; elsewhere they are
# inert. Every hook chains through to the repo-default hooks (the dotconfigs
# symlinks under .git/hooks/), so activating this drops nothing.
#
# Idempotent and reversible:
#     git config --unset core.hooksPath
#
# Intended for the production checkout during the Phase 1 interim. Obsolete
# after the Phase 2 cutover removes prod's .git (core.hooksPath then has no
# effect, since there is no repository to run hooks).

set -euo pipefail

toplevel="$(git rev-parse --show-toplevel)"
hooks_dir="$toplevel/.githooks"

if [ ! -d "$hooks_dir" ]; then
    echo "error: $hooks_dir not found (run from within the ds01-infra checkout)" >&2
    exit 1
fi

git -C "$toplevel" config core.hooksPath "$hooks_dir"

echo "prod-git-guard: core.hooksPath -> $hooks_dir"
if [ "$toplevel" = "/opt/ds01-infra" ]; then
    echo "  guards ENFORCED (this is the production checkout)"
else
    echo "  guards inert here (not /opt/ds01-infra); default hooks still chained"
fi
echo "  reverse with: git -C $toplevel config --unset core.hooksPath"
