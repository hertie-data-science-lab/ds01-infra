#!/usr/bin/env bash
# ds01-sync — detached-prod release orchestrator (Phase 2).
#
# Projects GitHub `main` (or a v* tag) into the live runtime at /opt/ds01-infra,
# which is a REAL directory with NO .git. The canonical checkout lives in a
# staging clone at /opt/ds01-staging; every release is built and smoke-tested
# THERE before prod is touched, then published with an atomic per-file rsync.
# current-sha + history live outside the tree in /var/lib/ds01/deploy/.
#
# Usage (root):
#   ds01-sync                  release origin/main
#   ds01-sync --ref v1.2.3     release a specific v* tag (must be an ancestor of main)
#   ds01-sync --rollback       re-release the previous good SHA
#   ds01-sync --list           show release history + current SHA
#
# Safety model: a smoke failure aborts before prod is mutated; a side-effect
# failure auto-rolls-back to the last good SHA; current-sha only advances after
# a fully successful release.

set -euo pipefail

# --- Constants -------------------------------------------------------------
INFRA_ROOT=/opt/ds01-infra
STAGING=/opt/ds01-staging
STATE_DIR=/var/lib/ds01/deploy
LOCK_FILE=/var/lib/ds01/deploy.lock
CURRENT_SHA_FILE="$STATE_DIR/current-sha"
HISTORY_LOG="$STATE_DIR/history.log"
OWNER=datasciencelab
DEPLOY="$INFRA_ROOT/scripts/system/deploy.sh"
REF_RE='^v[0-9][A-Za-z0-9._-]*$'

RED=$'\033[0;31m'
GREEN=$'\033[0;32m'
YELLOW=$'\033[1;33m'
BOLD=$'\033[1m'
NC=$'\033[0m'

log() { echo "${BOLD}ds01-sync:${NC} $*"; }
warn() { echo "${YELLOW}ds01-sync:${NC} $*" >&2; }
die() {
    echo "${RED}ds01-sync error:${NC} $*" >&2
    exit 1
}

usage() { sed -n '2,20p' "$0" | sed 's/^# \{0,1\}//'; }

# git in the staging clone, always as the checkout owner (SSH auth + ownership;
# root would trip git's dubious-ownership guard and lack the SSH key).
git_owner() { runuser -u "$OWNER" -- git -C "$STAGING" "$@"; }

now() { date '+%Y-%m-%dT%H:%M:%S%z'; }

# <outcome> <sha> [detail...]  — append one tab-separated record to history.log
record() {
    local outcome=$1 sha=$2
    shift 2
    printf '%s\t%s\t%s\t%s\n' "$(now)" "$outcome" "$sha" "$*" >>"$HISTORY_LOG"
}

current_sha() { [ -f "$CURRENT_SHA_FILE" ] && cat "$CURRENT_SHA_FILE" || true; }

# Most recent successful SHA strictly before the current one (for --rollback).
previous_good_sha() {
    local cur
    cur=$(current_sha)
    awk -F'\t' '$2=="success"{print $3}' "$HISTORY_LOG" 2>/dev/null |
        tac | awk '!seen[$0]++' | grep -vxF "$cur" | head -1
}

fetch_staging() {
    log "fetching origin in staging ($STAGING) as $OWNER"
    git_owner fetch --prune origin
}

# [--ref <tag>]  — echo the validated target SHA on stdout; errors to stderr.
resolve_target() {
    if [ "${1:-}" = "--ref" ]; then
        local ref=${2:-} sha
        [[ $ref =~ $REF_RE ]] || {
            warn "invalid --ref '$ref' (must match $REF_RE, no leading dash)"
            return 1
        }
        sha=$(git_owner rev-parse --verify "refs/tags/$ref^{commit}" 2>/dev/null) || {
            warn "tag '$ref' not found in staging (fetched?)"
            return 1
        }
        # A stray tag must not deploy an orphan commit as root.
        git_owner merge-base --is-ancestor "$sha" origin/main 2>/dev/null || {
            warn "tag '$ref' ($sha) is not an ancestor of origin/main — refusing"
            return 1
        }
        echo "$sha"
    else
        git_owner rev-parse --verify origin/main
    fi
}

# <sha>  — check out and smoke-test in staging. Returns non-zero on failure.
build_and_smoke() {
    local sha=$1
    log "building $sha in staging"
    git_owner checkout -f "$sha" >/dev/null 2>&1 || {
        warn "checkout of $sha failed in staging"
        return 1
    }
    log "smoke-testing staging tree"
    python3 -c "import sys; sys.path.insert(0, '$STAGING/scripts/docker'); import gpu_state_reader" ||
        return 1
    python3 "$STAGING/scripts/docker/get_resource_limits.py" --help >/dev/null 2>&1 ||
        return 1
    python3 -c "import yaml; yaml.safe_load(open('$STAGING/config/runtime/resource-limits.yaml'))" ||
        return 1
    return 0
}

# <prev_sha> <new_sha>  — tracked files deleted between prev and new
compute_deletions() {
    local prev=$1 new=$2
    [ -n "$prev" ] || return 0
    git_owner diff --name-only --diff-filter=D "$prev" "$new" 2>/dev/null || true
}

# <prev_sha> <new_sha>  — publish staging -> prod atomically, then remove the
# tracked files that git deleted between prev and new (rsync runs WITHOUT
# --delete, so prod-only runtime state that never existed in staging survives).
release_to_prod() {
    local prev=$1 new=$2 f
    log "publishing staging -> prod (rsync, no --delete)"
    rsync -a --delay-updates \
        --exclude='.git' \
        --exclude='aime-ml-containers/' \
        "$STAGING/" "$INFRA_ROOT/"
    if [ -n "$prev" ]; then
        while IFS= read -r f; do
            [ -n "$f" ] || continue
            [ "${f#aime-ml-containers/}" != "$f" ] && continue
            rm -f "$INFRA_ROOT/$f"
        done < <(compute_deletions "$prev" "$new")
    fi
}

run_side_effects() {
    log "running side-effects (deploy.sh) from the updated prod tree"
    "$DEPLOY"
}

# <target_sha>  — full release pipeline used by both deploy and rollback.
do_release() {
    local new=$1 prev
    prev=$(current_sha)

    if ! build_and_smoke "$new"; then
        record attempt "$new" "smoke FAILED in staging; prod untouched"
        die "smoke check failed in staging — prod NOT touched"
    fi
    record attempt "$new" "smoke passed (prev=${prev:-none})"

    release_to_prod "$prev" "$new"

    if ! run_side_effects; then
        warn "side-effects FAILED for $new — auto-rolling back to ${prev:-none}"
        record failure "$new" "side-effects failed; rolling back to ${prev:-none}"
        if [ -n "$prev" ] && [ "$prev" != "$new" ]; then
            if build_and_smoke "$prev" && release_to_prod "$new" "$prev" && run_side_effects; then
                record rollback "$prev" "auto-rollback after failed release of $new"
                die "release of $new failed; rolled back to $prev (current-sha unchanged)"
            fi
            die "ROLLBACK FAILED after failed release of $new — prod may be inconsistent; investigate NOW"
        fi
        die "release of $new failed and there is no previous SHA to roll back to"
    fi

    # Success — advance current-sha ONLY now, never ahead of what is live.
    echo "$new" >"$CURRENT_SHA_FILE"
    record success "$new" "released (prev=${prev:-none})"
    log "${GREEN}released $new${NC}"
}

main() {
    local mode=deploy ref=""
    while [ $# -gt 0 ]; do
        case $1 in
            --ref)
                ref=${2:-}
                shift 2
                ;;
            --rollback)
                mode=rollback
                shift
                ;;
            --list)
                mode=list
                shift
                ;;
            -h | --help)
                usage
                exit 0
                ;;
            *) die "unknown argument: $1 (see --help)" ;;
        esac
    done

    if [ "$mode" = list ]; then
        if [ -f "$HISTORY_LOG" ]; then cat "$HISTORY_LOG"; else echo "(no history)"; fi
        echo "current-sha: $(current_sha || echo none)"
        exit 0
    fi

    [ "$(id -u)" -eq 0 ] || die "must run as root (sudo ds01-sync)"
    [ ! -e "$INFRA_ROOT/.git" ] ||
        die "$INFRA_ROOT/.git exists — prod is not detached (cutover not done?); refusing"
    [ -d "$STAGING/.git" ] || die "staging clone not found at $STAGING"

    mkdir -p "$STATE_DIR"

    # Mandatory mutex: prevents CI + manual (or two admins) interleaving into a
    # chimera tree.
    exec 9>"$LOCK_FILE"
    flock -n 9 || die "another ds01-sync is already running (lock: $LOCK_FILE)"

    fetch_staging

    local target
    case $mode in
        deploy)
            if [ -n "$ref" ]; then
                target=$(resolve_target --ref "$ref") || die "could not resolve --ref $ref"
            else
                target=$(resolve_target) || die "could not resolve origin/main"
            fi
            log "target: $target${ref:+ (ref $ref)}"
            do_release "$target"
            ;;
        rollback)
            target=$(previous_good_sha) || true
            [ -n "$target" ] || die "no previous good SHA in history to roll back to"
            log "rolling back to previous good SHA: $target"
            do_release "$target"
            ;;
    esac
}

main "$@"
