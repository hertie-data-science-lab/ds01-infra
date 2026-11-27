#!/usr/bin/env bash
# monthly-update.sh - the monthly maintenance window (last Friday, 10:00-10:30).
#
#   monthly-update.sh              full run: upgrade, prune, check the driver, reboot
#   monthly-update.sh --check      list what would be upgraded; change nothing
#   monthly-update.sh --no-reboot  full run, but leave the reboot to the admin
#   monthly-update.sh --verify     post-reboot checks (ds01-post-maintenance.service)
#
# Run by hand as `sudo ds01-monthly-update`, or by ds01-monthly-update.timer once
# that is enabled. Security updates already land nightly via unattended-upgrades;
# config/deploy/apt.conf.d/52ds01-unattended-upgrades keeps kernel and NVIDIA
# packages out of that, so they only ever change here, next to a reboot.
#
# The reboot is refused unless the NVIDIA module exists for the kernel GRUB will
# boot: a box that comes back without GPUs is the failure that matters here.
# --verify then compares running kernel, GPU count and ds01-health-check against
# what was recorded before the reboot, and exits non-zero (-> OnFailure alert) on
# anything that got worse. Health checks that already failed before are reported
# but do not fail the run.

set -euo pipefail

STATE_DIR=${DS01_MAINT_STATE_DIR:-/var/lib/ds01/monthly-update}
LOG_FILE=${DS01_MAINT_LOG:-/var/log/ds01/monthly-update.log}
GRUB_CFG=${DS01_GRUB_CFG:-/boot/grub/grub.cfg}
MODULES_DIR=${DS01_MODULES_DIR:-/lib/modules}
REBOOT_FLAG=${DS01_REBOOT_FLAG:-/var/run/reboot-required}
HEALTH_CHECK=${DS01_HEALTH_CHECK:-/opt/ds01-infra/scripts/monitoring/ds01-health-check}
REBOOT_DELAY_MIN=2

PENDING="$STATE_DIR/verify-pending"

export DEBIAN_FRONTEND=noninteractive
APT=(apt-get -y -o DPkg::Lock::Timeout=600
    -o Dpkg::Options::=--force-confdef -o Dpkg::Options::=--force-confold)

log() { echo "[$(date '+%F %T')] $*"; }
die() {
    log "ERROR: $*"
    exit 1
}

# The kernel GRUB boots by default: the first `linux /boot/vmlinuz-<ver>` line.
# Not /boot/vmlinuz, which tracks the most recently *installed* kernel and on this
# box points at a 5.15 kernel GRUB never picks.
boot_kernel() {
    sed -n 's|^[[:space:]]*linux[[:space:]][[:space:]]*/boot/vmlinuz-\([^[:space:]]*\).*|\1|p' "$GRUB_CFG" | head -1
}

gpu_count() { nvidia-smi -L 2>/dev/null | grep -c '^GPU ' || true; }

# Names of failing ds01-health-check checks, one per line. It exits 1 whenever any
# check fails, so its status says nothing; only unparseable output counts as broken.
health_failures() {
    local json
    json=$("$HEALTH_CHECK" --json 2>/dev/null) || true
    python3 -c 'import json,sys
for c in json.loads(sys.argv[1])["checks"]:
    if not c["passed"]: print(c["check"])' "$json" 2>/dev/null || echo "health-check-unavailable"
}

# /lib/modules/<ver> directories no package owns: left behind by DKMS builds of
# kernels that have long been purged. Never the running kernel.
prune_module_dirs() {
    local d running
    running=$(uname -r)
    for d in "$MODULES_DIR"/*/; do
        d=${d%/}
        [ "$(basename "$d")" = "$running" ] && continue
        dpkg -S "$d" >/dev/null 2>&1 && continue
        log "removing orphaned $d"
        rm -rf -- "$d"
    done
}

cmd_check() {
    apt-get update -qq
    log "upgradable:"
    apt list --upgradable 2>/dev/null | tail -n +2
    log "boot kernel: $(boot_kernel), running: $(uname -r)"
    [ -e "$REBOOT_FLAG" ] && log "reboot pending since $(date -r "$REBOOT_FLAG" '+%F')"
    return 0
}

cmd_update() {
    local reboot=$1 kernel

    log "recording pre-maintenance state"
    docker ps --format '{{.Names}}\t{{.Image}}\t{{.Status}}' >"$STATE_DIR/containers-before.txt" || true
    log "$(wc -l <"$STATE_DIR/containers-before.txt") running containers recorded in $STATE_DIR/containers-before.txt"
    gpu_count >"$STATE_DIR/gpus-before"
    health_failures >"$STATE_DIR/health-before"

    log "apt-get update"
    "${APT[@]}" update
    log "apt-get full-upgrade"
    "${APT[@]}" full-upgrade
    log "apt-get autoremove --purge"
    "${APT[@]}" autoremove --purge
    prune_module_dirs

    kernel=$(boot_kernel)
    [ -n "$kernel" ] || die "could not read the default kernel from $GRUB_CFG"
    modinfo -k "$kernel" nvidia >/dev/null 2>&1 ||
        die "no nvidia module for $kernel (GRUB's default) - NOT rebooting; check 'dkms status'"
    log "nvidia module present for boot kernel $kernel"

    if [ ! -e "$REBOOT_FLAG" ] && [ "$kernel" = "$(uname -r)" ]; then
        log "no reboot needed"
        cmd_verify "$kernel"
        return
    fi

    if [ "$reboot" = no ]; then
        log "reboot needed (boot kernel $kernel, running $(uname -r)) - left to you (--no-reboot)"
        return 0
    fi

    # The post-maintenance unit runs --verify on the next boot only if this exists.
    echo "$kernel" >"$PENDING"
    log "rebooting in $REBOOT_DELAY_MIN min into $kernel"
    shutdown -r "+$REBOOT_DELAY_MIN" "DS01 monthly maintenance: rebooting in $REBOOT_DELAY_MIN minutes. Running containers will stop."
}

# Compares against the pre-maintenance baseline. Docker health is covered by
# ds01-health-check's own docker_daemon check, so a dead docker is a new failure.
cmd_verify() {
    local expected=$1 want have failed=0 new old

    if [ "$(uname -r)" = "$expected" ]; then
        log "OK   kernel $expected"
    else
        log "FAIL kernel: running $(uname -r), expected $expected"
        failed=1
    fi

    want=$(cat "$STATE_DIR/gpus-before" 2>/dev/null || echo 0)
    have=$(gpu_count)
    if [ "$have" -gt 0 ] && [ "$have" -ge "$want" ]; then
        log "OK   $have GPUs visible"
    else
        log "FAIL $have GPUs visible, $want before maintenance"
        failed=1
    fi

    health_failures >"$STATE_DIR/health-after"
    new=$(grep -vxFf "$STATE_DIR/health-before" "$STATE_DIR/health-after" 2>/dev/null || true)
    if [ -n "$new" ]; then
        log "FAIL new health-check failures: $(echo "$new" | paste -sd, -)"
        failed=1
    else
        log "OK   no new health-check failures"
    fi
    old=$(grep -xFf "$STATE_DIR/health-before" "$STATE_DIR/health-after" 2>/dev/null || true)
    [ -z "$old" ] || log "     (still failing, as before: $(echo "$old" | paste -sd, -))"

    [ "$failed" -eq 0 ] || die "post-maintenance checks failed"
    log "maintenance complete"
}

main() {
    local mode=update reboot=yes
    while [ $# -gt 0 ]; do
        case "$1" in
            --check) mode=check ;;
            --verify) mode=verify ;;
            --no-reboot) reboot=no ;;
            -h | --help)
                sed -n '2,8p' "$0" | sed 's/^# \{0,1\}//'
                return 0
                ;;
            *) die "unknown option: $1" ;;
        esac
        shift
    done

    [ "$(id -u)" -eq 0 ] || die "must run as root (sudo ds01-monthly-update)"
    mkdir -p "$STATE_DIR" "$(dirname "$LOG_FILE")"
    exec > >(tee -a "$LOG_FILE") 2>&1

    # A manual run and the timer must never overlap.
    exec 9>"$STATE_DIR/lock"
    flock -n 9 || die "another monthly-update is running"

    log "monthly-update $mode starting"
    case "$mode" in
        check) cmd_check ;;
        verify)
            [ -f "$PENDING" ] || die "nothing to verify ($PENDING missing)"
            # One attempt: a failure alerts once, not on every later boot.
            local kernel
            kernel=$(cat "$PENDING")
            rm -f "$PENDING"
            cmd_verify "$kernel"
            ;;
        update) cmd_update "$reboot" ;;
    esac
}

main "$@"
