#!/bin/bash
# DS01 monitoring config permissions
# ==================================
# Single source of truth for the permissions on the bind-mounted monitoring
# config trees. The containerised services read these files as non-root users
# (Prometheus: nobody, Grafana: 472, Alertmanager: nobody), so the files must be
# world-readable (644) with traversable directories — otherwise a Prometheus
# reload or Grafana provisioning load fails with permission-denied. The deploy
# account's umask (0077) makes a `git pull`/checkout write newly-created files
# mode 600, which is exactly what this normalises.
#
# Sourced by:
#   - config/permissions-manifest.sh  (deploy time, as root — canonical reset)
#   - scripts/admin/monitoring-manage (runtime self-heal, as the file owner)
#
# Idempotent: only touches files/dirs that have drifted from the target mode, so
# it is cheap to call on every start/restart/update/reload.

# Normalise perms on the monitoring config trees under <root> (default INFRA_ROOT).
# Echoes the number of files it had to fix (0 when already correct).
normalize_monitoring_perms() {
    local root="${1:-${INFRA_ROOT:?INFRA_ROOT not set}}"
    local mon="$root/monitoring"
    local fixed=0 dir file

    for dir in "$mon/prometheus" "$mon/alertmanager" "$mon/grafana/provisioning"; do
        [[ -d $dir ]] || continue

        # Config files → 644 (world-readable)
        while IFS= read -r -d '' file; do
            if chmod 644 "$file" 2>/dev/null; then
                fixed=$((fixed + 1))
            fi
        done < <(find "$dir" -type f ! -perm 644 -print0 2>/dev/null)

        # Directories → traversable (other-execute)
        find "$dir" -type d ! -perm -o=x -exec chmod o+x {} + 2>/dev/null || true
    done

    printf '%s\n' "$fixed"
}
