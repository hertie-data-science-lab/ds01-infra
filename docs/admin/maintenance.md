# Maintenance

Ongoing operations once DS01 is installed: updating code, reapplying system
side-effects, the automated cron jobs, config-drift handling, and where the logs
live. For first-time setup see [Installation](./installation.md); for the config
model itself see [System configuration](./system-config.md).

## Updating (`ds01-sync`)

`/opt/ds01-infra` is detached (no `.git`) and is only ever updated through
`ds01-sync` (`scripts/system/sync.sh`), which builds and smoke-tests each release
in the `/opt/ds01-staging` clone before publishing it:

```bash
sudo ds01-sync                 # release origin/main
sudo ds01-sync --ref v1.6.0    # release a specific v* tag (must be an ancestor of main)
sudo ds01-sync --rollback      # re-release the previous good SHA
sudo ds01-sync --list          # show release history + current SHA
```

A smoke-check failure in staging aborts before prod is touched. A side-effects or
post-deploy health-gate failure after prod is updated triggers an **automatic
rollback** to the last good SHA — `current-sha` (in `/var/lib/ds01/deploy/`) only
advances after a fully successful, health-gated release. `--rollback` re-runs the
same pipeline against the previous good SHA on demand.

CI triggers this automatically: pushing a `v*.*.*` tag runs
`.github/workflows/deploy.yml` on the self-hosted runner, which calls
`sudo ds01-sync --ref <tag>`. See [Versioning](./versioning.md) for the release side
of that flow.

## Reapplying side-effects only (`deploy`)

```bash
sudo deploy               # symlinks, permissions, systemd units, sudoers, cron, etc.
sudo deploy --verbose      # show each command being (re)deployed
```

`deploy` (`deploy.sh`) reapplies side-effects — command symlinks into
`/usr/local/bin/`, the permissions manifest, `config/deploy/{profile.d,sudoers.d,
cron.d}/*`, systemd units, and a restart of the code-caching daemons
(`ds01-exporter`, `ds01-container-owner-tracker`, `ds01-container-sync`) — against
whatever code is **already on disk** in prod. It does **not** fetch or change code;
`ds01-sync` calls it automatically as part of every release, but it's also safe to
run standalone, e.g. after a manual permissions fix or to pick up a config change
without cutting a release.

## Scheduled maintenance (cron)

Installed from `config/deploy/cron.d/` by `deploy.sh` (part of every `ds01-sync`
release). Two files:

### `ds01-maintenance`

| Job | Schedule | Purpose |
|-----|----------|---------|
| GPU utilization recording | Every 5 min | Trend data for dashboards |
| GPU waste check | Every 30 min | Flags allocated-but-idle GPUs |
| GPU queue processing | Every 5 min | Notifies queued users as slots free up |
| Stale GPU allocation cleanup | `:05` hourly | Reconciles allocator state with reality |
| Resource quota alerts | `:10` hourly | Delivers quota-warning alerts |
| Idle container check | `:20` hourly | Stops containers past their idle timeout |
| Max runtime enforcement | `:35` hourly | Stops containers past their max runtime |
| Stale container cleanup | `:50` hourly | Removes stopped containers |
| Permissions drift fix | Every 15 min | Re-runs `config/permissions-manifest.sh` (guards against umask-077 edits breaking world-readability) |
| Config watchdog (quick) | Daily, noon | Recovers test-crash artifacts — see below |
| Config watchdog (full) | Daily, 01:00 | Verifies live config against the deployed source — see below |
| State validation | Daily, 02:00 | `validate-state.py --fix` — GPU allocation state consistency |
| Health check | Daily, 03:00 | Full `ds01-health-check` run |
| Group membership sync | Daily, 04:30 | Scans `/home/` for new users into `config/runtime/groups/*.members` |
| Downstream backup | Daily, 05:00 | `sync-downstream.sh` — see below |
| Alert/GPU-queue log cleanup | Daily, 04:00 | Prunes old alert and queue-log state |
| Log archiving | Weekly, Sun 02:00 | `backup-logs.sh` |
| Archive cleanup | Monthly, 1st 03:00 | `backup-logs.sh --clean` |
| Monthly report | Monthly, 1st 06:00 | `ds01-monthly-report` |

### `ds01-resource-monitor`

| Job | Schedule | Purpose |
|-----|----------|---------|
| Resource stats collection | Every minute | PSI metrics, per-slice CPU/mem/PID usage, OOM detection |

## Config-watchdog drift handling

`scripts/maintenance/config-watchdog.sh` runs in two modes (both scheduled above):

- **Quick** (no args, daily at noon): recovers **test-crash artifacts** only — a
  disabled cron file (`ds01-maintenance.disabled-by-test`) or a leftover
  `resource-limits.yaml.bak-runtime-test` backup left behind by a crashed test run.
- **Full** (`--full`, daily at 01:00): reads the reference
  `config/runtime/resource-limits.yaml` from the **staging clone at the currently
  deployed SHA** (`/var/lib/ds01/deploy/current-sha`) and compares its hash against
  the live file in prod. On a mismatch it Teams-alerts (if a webhook is configured —
  see `alert_teams()` in the script) with a diff, then **overwrites the live file
  back to the deployed version**.

**Practical implication:** don't hand-edit `config/runtime/resource-limits.yaml` (or
any file under `config/runtime/`) directly in prod — it will be reverted at the next
`--full` run (or at the next `ds01-sync`) unless the change also lands via a normal
PR into `main`. Make config changes in a dev clone, land them via PR, then release
with `ds01-sync`.

## Downstream backup

`scripts/system/sync-downstream.sh` (daily at 05:00, as the `datasciencelab`
checkout owner) mirrors the **full** prod tree — including prod-only, git-ignored
runtime state (`config/runtime/*.members`, `user-overrides.yaml`,
`teams-webhook-url.txt`, `.planning/`, etc.) — to a `downstream` git remote
configured on the staging clone. It drives git via the staging repo's `.git` against
prod's work-tree (prod itself has no `.git`), and is a no-op if the staging clone
has no `downstream` remote configured (see [Installation → Cutover](./installation.md#one-time-cutover-to-detached-prod)).
Logs to `/tmp/ds01-sync-downstream.log`.

## Log locations

| Path | Contents |
|------|----------|
| `/var/log/ds01/*.log` | Per-job cron logs (cleanup, idle, runtime enforcement, health check, permissions-fix, etc.) |
| `/var/log/ds01/events.jsonl` | Centralised structured event log |
| `/var/log/ds01/gpu-allocations.log` | GPU allocation history |
| `/var/log/ds01/config-watchdog.log` | Config-watchdog full-check output |
| `/tmp/ds01-sync-downstream.log` | Downstream backup output |
| `/var/lib/ds01/deploy/current-sha`, `history.log` | Deployed SHA + full release history (`sudo ds01-sync --list`) |

Log rotation is configured in `config/deploy/logrotate.d/ds01` (daily, 30-day
retention for `*.log`; weekly/dateext for the larger `.jsonl` files) — this is
**not** installed automatically by `deploy.sh`; see
[Installation → Fresh-box bootstrap](./installation.md#fresh-box-bootstrap) (step 6).

## Monitoring

Day-to-day Prometheus/Grafana/Alertmanager operations (dashboards, alert
silencing, stack restarts) live in [Monitoring](./monitoring.md), not here.
