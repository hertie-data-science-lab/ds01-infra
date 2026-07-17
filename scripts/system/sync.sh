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
# Safety model: a smoke failure aborts before prod is mutated; a side-effect OR
# post-deploy-health-gate failure auto-rolls-back to the last good SHA;
# current-sha only advances after a fully successful, health-gated release.

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
    chmod 644 "$HISTORY_LOG" 2>/dev/null || true
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
    # --chmod=D755: force transferred directories to 755. The staging clone is
    # made under the owner's umask (077 → 0700 dirs); without this, rsync -a
    # would propagate 0700 onto prod and lock users out of the runtime tree.
    # Files keep their source perms (the permissions-manifest re-enforces them).
    rsync -a --delay-updates --chmod=D755 \
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

# Post-deploy health gate: probe the LIVE system after side-effects. Returns
# non-zero (→ rollback) only on deploy-breaking conditions. Full regression is
# NOT re-run here — it runs pre-merge (ci.yml) and nightly (ci-system); the
# @system tests allocate real GPUs and would fight users' jobs. This is a fast,
# non-destructive probe instead.
health_gate() {
    log "post-deploy health gate"
    local bad=0 svc dw hc

    # Invariants a good release MUST preserve.
    for svc in ds01-exporter ds01-container-owner-tracker ds01-container-sync; do
        systemctl is-active --quiet "$svc" || {
            warn "health: $svc is not active"
            bad=1
        }
    done

    dw=$(readlink -f /usr/local/bin/docker 2>/dev/null || true)
    if [ "$dw" != "$INFRA_ROOT/scripts/docker/docker-wrapper.sh" ]; then
        warn "health: /usr/local/bin/docker resolves to '${dw:-missing}', not the wrapper (GPU isolation bypass risk)"
        bad=1
    fi

    python3 "$INFRA_ROOT/scripts/docker/get_resource_limits.py" --help >/dev/null 2>&1 ||
        {
            warn "health: get_resource_limits.py --help failed"
            bad=1
        }

    # Broader system integrity. A CRITICAL result (exit >= 2, e.g. Docker down)
    # rolls back; non-critical drift (exit 1) is logged, not rolled back — it is
    # usually pre-existing and handled by config-watchdog / other reconcilers.
    if [ -x "$INFRA_ROOT/scripts/monitoring/ds01-health-check" ]; then
        "$INFRA_ROOT/scripts/monitoring/ds01-health-check" >/dev/null 2>&1
        hc=$?
        if [ "$hc" -ge 2 ]; then
            warn "health: ds01-health-check CRITICAL (exit $hc)"
            bad=1
        elif [ "$hc" -eq 1 ]; then
            log "health: ds01-health-check reported non-critical issues (exit 1); not rolling back"
        fi
    fi

    return "$bad"
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

    # Apply side-effects, then health-gate the LIVE system. Either failing rolls
    # back to the last good SHA.
    local failure=""
    if ! run_side_effects; then
        failure="side-effects"
    elif ! health_gate; then
        failure="post-deploy health gate"
    fi

    if [ -n "$failure" ]; then
        warn "$failure FAILED for $new — auto-rolling back to ${prev:-none}"
        record failure "$new" "$failure failed; rolling back to ${prev:-none}"
        if [ -n "$prev" ] && [ "$prev" != "$new" ]; then
            # Rollback re-runs side-effects but NOT the health gate, to avoid a
            # rollback loop if the gate itself is flaky; $prev was healthy when
            # it was last released.
            if build_and_smoke "$prev" && release_to_prod "$new" "$prev" && run_side_effects; then
                record rollback "$prev" "auto-rollback after $failure failure on $new"
                die "release of $new failed ($failure); rolled back to $prev (current-sha unchanged)"
            fi
            die "ROLLBACK FAILED after $failure failure on $new — prod may be inconsistent; investigate NOW"
        fi
        die "release of $new failed ($failure) and there is no previous SHA to roll back to"
    fi

    # Success — advance current-sha ONLY now, never ahead of what is live.
    echo "$new" >"$CURRENT_SHA_FILE"
    chmod 644 "$CURRENT_SHA_FILE" 2>/dev/null || true
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
    # World-readable so `version` (run by any user) and --list can read
    # current-sha/history; the SHA + release log are not sensitive.
    chmod 755 "$STATE_DIR" 2>/dev/null || true

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
