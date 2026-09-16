# Maintenance

Ongoing operations once DS01 is installed: updating code, reapplying system
side-effects, the automated cron jobs, config-drift handling, how the box and its
GitHub workflows tell a human something is wrong, and where the logs live. For first-time setup see [Installation](./installation.md); for the config
model itself see [System configuration](./system-config.md).

## Updating (`ds01-deploy`)

`/opt/ds01-infra` is detached (no `.git`) and is only ever updated through
`ds01-deploy` (`scripts/system/sync.sh`), which builds and smoke-tests each release
in the `/opt/ds01-staging` clone before publishing it:

```bash
sudo ds01-deploy                 # release origin/main
sudo ds01-deploy --ref v1.6.0    # release a specific v* tag (must be an ancestor of main)
sudo ds01-deploy --rollback      # re-release the previous good SHA
sudo ds01-deploy --list          # show release history + current SHA
```

A smoke-check failure in staging aborts before prod is touched. A side-effects or
post-deploy health-gate failure after prod is updated triggers an **automatic
rollback** to the last good SHA - `current-sha` (in `/var/lib/ds01/deploy/`) only
advances after a fully successful, health-gated release. `--rollback` re-runs the
same pipeline against the previous good SHA on demand.

CI triggers this automatically: pushing a `v*.*.*` tag runs
`.github/workflows/deploy.yml` on the self-hosted runner, which calls
`sudo ds01-deploy --ref <tag>`. See [Versioning](./versioning.md) for the release side
of that flow.

## Reapplying side-effects only (`ds01-apply`)

```bash
sudo ds01-apply               # symlinks, permissions, systemd units, sudoers, cron, etc.
sudo ds01-apply --verbose      # show each command being (re)deployed
```

`ds01-apply` (`deploy.sh`) reapplies side-effects - command symlinks into
`/usr/local/bin/`, the permissions manifest, `config/deploy/{profile.d,sudoers.d,
cron.d}/*`, systemd units, and a restart of the code-caching daemons
(`ds01-exporter`, `ds01-container-owner-tracker`, `ds01-container-sync`) - against
whatever code is **already on disk** in prod. It does **not** fetch or change code;
`ds01-deploy` calls it automatically as part of every release, but it's also safe to
run standalone, e.g. after a manual permissions fix or to pick up a config change
without cutting a release.

## Scheduled maintenance (cron)

Installed from `config/deploy/cron.d/` by `deploy.sh` (part of every `ds01-deploy`
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
| Config watchdog (quick) | Daily, noon | Recovers test-crash artifacts - see below |
| Config watchdog (full) | Daily, 01:00 | Verifies live config against the deployed source - see below |
| State validation | Daily, 02:00 | `validate-state.py --fix` - GPU allocation state consistency |
| Health check | Daily, 03:00 | Full `ds01-health-check` run |
| Group membership sync | Daily, 04:30 | Scans `/home/` for new users into `config/runtime/groups/*.members` |
| Downstream backup | Daily, 05:00 | `sync-downstream.sh` - see below |
| Alert/GPU-queue log cleanup | Daily, 04:00 | Prunes old alert and queue-log state |
| Log archiving | Weekly, Sun 02:00 | `backup-logs.sh` |
| Archive cleanup | Monthly, 1st 03:00 | `backup-logs.sh --clean` |
| Monthly report | Monthly, 1st 06:00 | `ds01-monthly-report` - saves the report, posts it to Teams and mails it (see below) |

### `ds01-resource-monitor`

| Job | Schedule | Purpose |
|-----|----------|---------|
| Resource stats collection | Every minute | PSI metrics, per-slice CPU/mem/PID usage, OOM detection |

## Config-watchdog drift handling

`scripts/maintenance/config-watchdog.sh` runs in two modes (both scheduled above):

- **Quick** (no args, daily at noon): recovers **test-crash artifacts** only - a
  disabled cron file (`ds01-maintenance.disabled-by-test`) or a leftover
  `resource-limits.yaml.bak-runtime-test` backup left behind by a crashed test run.
- **Full** (`--full`, daily at 01:00): reads the reference
  `config/runtime/resource-limits.yaml` from the **staging clone at the currently
  deployed SHA** (`/var/lib/ds01/deploy/current-sha`) and compares its hash against
  the live file in prod. On a mismatch it alerts with a diff on both channels - Teams
  if a webhook is configured, mail if `/etc/dsl-alert-mail.env` exists (see `alert()`
  in the script, and [the mail alert](#provisioning-the-mail-alert) below) - then
  **overwrites the live file back to the deployed version**.

**Practical implication:** don't hand-edit `config/runtime/resource-limits.yaml` (or
any file under `config/runtime/`) directly in prod - it will be reverted at the next
`--full` run (or at the next `ds01-deploy`) unless the change also lands via a normal
PR into `main`. Make config changes in a dev clone, land them via PR, then release
with `ds01-deploy`.

## DSL scheduled-release driver

`dsl-scheduled-release.timer` fires at `:00/:15/:30/:45` and runs
`scripts/maintenance/dsl-scheduled-release.sh`, which sends a `scheduled-release`
`repository_dispatch` to every DSL course org's `.github` repo (found by the
`dsl-course-hub` topic) and then reads that org's recent runs back.

Why ds01 drives it: the teaching toolkit's own GitHub Actions cron for that
workflow - which carries every deadline-sensitive action in every course org -
is delivered best-effort, with observed gaps of hours. The two schedules
interleave (ours `:00/:15/:30/:45`, GitHub's `:07/:22/:37/:52`), so a fire lost
on either side costs at most ~8 minutes. Why ds01 also *observes*: on GitHub
every step of that workflow, including the step that opens the "workflow is
failing" issue, uses the same bot token as the work, so a revoked token is a
silent total outage. This read-back is the only signal from outside GitHub.

Installed and enabled by `deploy.sh`, so every `ds01-apply` / `ds01-deploy`
picks it up. Journal-only - no file under `/var/log/ds01/`:

```bash
journalctl -u dsl-scheduled-release -n 50     # recent ticks
systemctl list-timers dsl-scheduled-release   # next fire
```

### Provisioning `/etc/dsl-scheduled-release.env`

The one artefact **not** in the repo, so a release neither overwrites nor leaks
it. Create it once, as root:

```bash
# Device flow - approve in a browser signed in as the DSL bot account, NOT as yourself
gh auth login --hostname github.com --scopes public_repo
gh auth token          # copy the gho_... value

install -m 0600 -o root -g root /dev/null /etc/dsl-scheduled-release.env
printf 'GH_TOKEN=%s\n' 'gho_...' >/etc/dsl-scheduled-release.env
```

`public_repo` is the entire scope needed: the `.github` hub repos are public and
`POST /dispatches` only needs write on them. Device-flow OAuth tokens do not
expire. `GH_TOKEN` from this file also overrides root's own `gh` login, so the
driver can never fall back to an admin credential.

The driver never puts the token on a command line: it writes the `Authorization`
header into a 0600 file inside its own 0700 tempdir and passes `curl -H @file`,
because `/proc` here is world-readable and `ps` would otherwise show the token to
every logged-in user for the length of each call. Don't add `set -x` to it.

### Testing one tick

```bash
sudo systemctl start dsl-scheduled-release.service
journalctl -u dsl-scheduled-release -n 30
```

A healthy tick logs only the summary line, e.g.
`dispatched=26 ok=26 pruned=0 failing=0 silent=0`.

### Reading the log

| Word | Meaning | Action |
|------|---------|--------|
| `prune <org>` | Dispatch returned 404 - the org is gone, GitHub's search index still lists it | None; clears itself |
| `dispatch-refused <org> (<code>)` | That org's dispatch was refused (401/403) while others went through - so it is that org, not the token: usually the hub repo is archived, has Actions disabled, or hit a secondary rate limit | Check that org's `.github` repo **before** reissuing the token |
| `token-dead (all N orgs refused...)` | *Every* org refused the dispatch - the token in the env file is revoked or lost its scope | Reissue the token and rewrite the env file |
| `failing <org>` | That org's last three *completed* runs (ignoring `cancelled`/`skipped`) all failed | Check the org's Actions tab - usually its own `DSL_BOT_TOKEN` or a broken toolkit release |
| `observe-failed <org> (<code>\|parse)` | The read-back of that org's runs returned a non-200, or a body that could not be parsed | Check the workflow exists in that org and that GitHub is healthy |
| `silent <org>` | No run started there in the last 60 min | Both drivers are missing that org - check the workflow exists and is `active` |

Anything above except `prune` (plus a `dispatch-failed`, or a truncated org
search) makes the tick exit non-zero, which starts
`dsl-alert@dsl-scheduled-release.service`: `scripts/maintenance/dsl-alert.sh` posts the
unit's last 20 journal lines to two independent channels, either of which may be
absent. Teams, via the same webhook `config-watchdog.sh` uses
(`DS01_TEAMS_WEBHOOK_URL`, else `config/runtime/teams-webhook-url.txt`); and mail,
via `dsl-alert-mail.py`, when `/etc/dsl-alert-mail.env` sets `DSL_ALERT_TO`. A
channel that fails logs a `WARNING` and never fails the alerter. With neither
configured the alert is a journal-only no-op. The driver prints org names and HTTP
status codes only - never an API response body, which can carry student names.

### Provisioning the mail alert

The tenant disables SMTP AUTH, so mail goes through Microsoft Graph with the lab's
Entra app certificate credential - the same app and the same certificate the
teaching toolkit mails with. It already holds `Mail.Send`, admin-consented and
scoped by an Exchange application access policy to the `datasciencelab` mailbox
alone, so nothing needs granting in Entra.

Nothing here is in the repo. Do all of it as root.

The mailer's one dependency is `cryptography` - the credential is a certificate,
and nothing else in this repo needs it, so nothing installs it. Install it once:

```bash
apt-get install -y python3-cryptography     # or: pip3 install cryptography
python3 -c "import cryptography"            # must print nothing
```

Then the two root-only files:

```bash
# The credential: certificate then its unencrypted private key, in that order -
# the same content as the toolkit org secret GRAPH_CLIENT_CERT.
install -m 0600 -o root -g root /dev/null /etc/dsl-alert-graph.pem
cat cert.cer key.pem >/etc/dsl-alert-graph.pem

install -m 0600 -o root -g root /dev/null /etc/dsl-alert-mail.env
cat >/etc/dsl-alert-mail.env <<'EOF'
GRAPH_TENANT_ID=<tenant uuid>
GRAPH_CLIENT_ID=<app registration uuid>
GRAPH_SENDER=datasciencelab@hertie-school.org
GRAPH_CLIENT_CERT_FILE=/etc/dsl-alert-graph.pem
DSL_ALERT_TO=h.baker@hertie-school.org
DSL_ALERT_CC=datasciencelab@hertie-school.org
EOF
```

| Variable | |
|---|---|
| `GRAPH_TENANT_ID`, `GRAPH_CLIENT_ID`, `GRAPH_SENDER` | the tenant, the app registration, the mailbox to send as |
| `GRAPH_CLIENT_CERT_FILE` | path to the PEM. **On the box, use this one.** |
| `GRAPH_CLIENT_CERT` | the PEM as a value, for GitHub Actions, where a secret is not a file. Setting both is refused rather than resolved: two credentials in one environment is a half-finished rotation, and picking a winner hides it. A multi-line value is also not something a systemd `EnvironmentFile` can carry. |
| `DSL_ALERT_TO` | who is told. Comma-separated for several. |
| `DSL_ALERT_CC` | copied on **everything** the lab sends - `datasciencelab@hertie-school.org` is the archive mailbox, and it is the reason `--cc` on the mailer ADDS to this rather than replacing it. Nothing in a caller can drop it; unsetting the variable is the only way, and that is a deployment decision. |

Set the lot or none: a partly-filled file is reported by variable name and sends
nothing. `dsl-alert@.service` reads the file as an optional `EnvironmentFile`, so a
box without it keeps working.

**Cron jobs do not get an `EnvironmentFile`.** The monthly report and the config
watchdog both run from cron, so `dsl-alert-mail.py` reads `/etc/dsl-alert-mail.env`
itself for any variable that is not already set (override the path with
`DSL_ALERT_ENV_FILE`). The environment always wins over the file, and the file is
parsed rather than sourced - only the variables above are read out of it, so a stray
`PATH=` left in it cannot change what the mailer runs.

### Testing the mail alert

```bash
sudo systemctl start dsl-alert@dsl-scheduled-release.service
journalctl -u dsl-alert -n 20
```

That mails the scheduled-release driver's current journal tail, whether or not the
driver is failing, and logs one line: `alert mailed to h***@hertie-school.org
(202)`. The mailer prints status codes and masked recipients only - never the token
and never a Graph response body, which echoes the message back.

## What tells a human something is wrong

Every channel below is optional and independent: Teams needs a webhook, mail needs
`/etc/dsl-alert-mail.env`, and neither can fail the thing it reports on.

| Source | Teams | Mail | Notes |
|---|---|---|---|
| A failed systemd unit (`OnFailure=dsl-alert@`) | yes | yes | `dsl-alert.sh`, last 20 journal lines |
| Config drift | yes | yes | `config-watchdog.sh --full`, with the diff |
| Prometheus alerts | yes | yes | Alertmanager, mail via the bridge below |
| The monthly report | yes | yes | summary card + full report; mail is the full report |
| A failed unattended GitHub run | no | yes | plus a self-closing issue - see below |

A Teams webhook must be a real `https://` URL. The placeholder this repo ships
(`PASTE_LOGIC_AZURE_URL_HERE`) counts as "not configured" everywhere, and skips the
channel silently rather than failing into a log file - which is what it used to do,
and why no monthly report arrived between May and September 2026.

The monthly report (`ds01-monthly-report`, 1st of the month at 06:00) mails the full
Markdown report as HTML wrapped in a `<pre>` - its heatmap and bar chart are ASCII and
a mail client that reflows them destroys them. `--no-mail` and `--no-teams` each skip
one channel; `--dry-run` prints the report and delivers nothing.

## Alertmanager mail bridge

`dsl-alert-bridge.service` is a small HTTP endpoint on the host that turns an
Alertmanager webhook into a mail. Alertmanager can post a webhook but cannot run a
script, so each receiver in `monitoring/alertmanager/alertmanager.yml` has a
`webhook_configs` beside its `msteamsv2_configs`, and the container reaches the host
over `host.docker.internal` - the same route Prometheus uses for `ds01-exporter`.

That port is on a host interface, and this endpoint **sends mail as the lab**, so the
POST carries a bearer token and the bridge refuses to start without one.
`deploy.sh` generates `config/runtime/alertmanager-mail-token.txt` on first deploy
(git-ignored, `root:65534 0640` - the `prom/alertmanager` container runs as `nobody`
and has to read it; nothing else on the box may). Nothing else needs doing.

```bash
systemctl status dsl-alert-bridge            # `listening on 0.0.0.0:9099`
journalctl -u dsl-alert-bridge -n 20         # one line per alert, names and counts only

# One end-to-end alert, token and all:
curl -sS -o /dev/null -w '%{http_code}\n' -X POST \
  -H "Authorization: Bearer $(cat /opt/ds01-infra/config/runtime/alertmanager-mail-token.txt)" \
  -H 'Content-Type: application/json' \
  -d '{"status":"firing","commonLabels":{"alertname":"SmokeTest"},"alerts":[{"status":"firing","labels":{"alertname":"SmokeTest"},"annotations":{"summary":"ignore me"}}]}' \
  http://127.0.0.1:9099/alert          # 202, then a mail
```

A 401 means Alertmanager and the bridge are reading different token files; restart
the stack after the first deploy that created one. The journal carries alert names,
statuses and counts only - an alert's labels here can name a user or a container, so
they go to the mailbox and nowhere else.

## GitHub Actions alarms

GitHub emails a scheduled run's failure only to whoever last touched the cron file,
which is nobody who reads that mailbox - and two of the faults below produce no
failing run at all:

| Alarm | Watches | Where |
|---|---|---|
| `Deploy is failing` | a tag release that failed | `deploy.yml` |
| `System CI is failing` | the nightly system suite | `ci-system.yml` |
| `ds01-runner is offline` | the self-hosted runner, and any run queued over an hour | `infra-alarms.yml`, hourly |
| `Scheduled-release dispatcher is quiet` | the age of the newest `repository_dispatch` run of `Scheduled release` in any course org | `infra-alarms.yml`, hourly |

Each keeps ONE open issue in this repo, comments on it at most once every six hours,
closes it on the next green run, and mails the maintainer whenever it files or
comments. Every alarm job runs on `ubuntu-latest` and never on `ds01-runner`: a dead
runner would otherwise swallow its own alarm. When the runner is down, `Deploy` and
`System CI` do not fail - they queue, green and pending, indefinitely.

`Infra alarms` rides a GitHub `schedule:`, which GitHub delivers best-effort (2-7% of
fires, measured), so a dropped fire delays detection. Both its checks are stateless,
so nothing is lost - but a quiet hour is not proof of health. The alternative would be
a watcher on ds01, and a watcher on the box cannot report the box being down.

### Actions secrets

Org-level on `hertie-data-science-lab`, visibility **selected**, scoped to `ds01-hub`
and `ds01-infra` - the two repos that mail. Same values as the box's
`/etc/dsl-alert-mail.env`, except that the certificate is the PEM itself:

| Secret | |
|---|---|
| `GRAPH_TENANT_ID` | |
| `GRAPH_CLIENT_ID` | |
| `GRAPH_CLIENT_CERT` | certificate **and** unencrypted private key, one PEM, as `cat cert.cer key.pem` produces |
| `GRAPH_SENDER` | `datasciencelab@hertie-school.org` |

`DSL_ALERT_TO` and `DSL_ALERT_CC` are not secrets and are written into the workflows:
`h.baker@hertie-school.org`, copying `datasciencelab@hertie-school.org`.

Repo-level on `ds01-infra`, optional:

| Secret | |
|---|---|
| `DSL_RUNNER_TOKEN` | fine-grained PAT, **Administration: read** on `ds01-infra`, for the direct runner probe. A workflow's own `GITHUB_TOKEN` cannot be granted that permission at all. Without this secret the probe is skipped with a warning and only the queued-run check runs - which catches the same fault, but only once something is waiting on the runner. |
| `DSL_BOT_TOKEN` | used, if present, for the cross-org read of each course org's `Scheduled release` runs. The hub repos are public, so the ambient token can normally do it. |

None of these workflows has a `pull_request` trigger, and none may ever be given one:
a branch would then be able to read the Graph credential.

## Downstream backup

`scripts/system/sync-downstream.sh` (daily at 05:00, as the `datasciencelab`
checkout owner) mirrors the **full** prod tree - including prod-only, git-ignored
runtime state (`config/runtime/*.members`, `user-overrides.yaml`,
`teams-webhook-url.txt`, `.planning/`, etc.) - to a `downstream` git remote
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
| `journalctl -u dsl-scheduled-release` | DSL scheduled-release driver ticks (journal only, by design) |
| `journalctl -u dsl-alert`, `-u dsl-alert-bridge` | Outgoing alerts: the OnFailure alerter, and the Alertmanager mail bridge |
| `/var/log/ds01/monthly-report.log` | Monthly report generation and delivery |
| `/var/lib/ds01/deploy/current-sha`, `history.log` | Deployed SHA + full release history (`sudo ds01-deploy --list`) |

Log rotation is configured in `config/deploy/logrotate.d/ds01` (daily, 30-day
retention for `*.log`; weekly/dateext for the larger `.jsonl` files) - this is
**not** installed automatically by `deploy.sh`; see
[Installation → Fresh-box bootstrap](./installation.md#fresh-box-bootstrap) (step 6).

## Monitoring

Day-to-day Prometheus/Grafana/Alertmanager operations (dashboards, alert
silencing, stack restarts) live in [Monitoring](./monitoring.md), not here.
