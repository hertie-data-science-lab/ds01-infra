# System Configuration

The config model behind DS01's resource limits, group membership, and deployed
system files. For the exhaustive directory-by-directory reference (every file,
every target path) see
[config/CLAUDE.md](https://github.com/hertie-data-science-lab/ds01-infra/blob/main/config/CLAUDE.md) —
this page is the conceptual overview and doesn't duplicate that table.

## `config/runtime/` vs `config/deploy/` vs `config/state/`

| Directory | What it is | Read/deployed by | Lifecycle |
|-----------|-----------|-------------------|-----------|
| `runtime/` | Operational config read live by scripts (`resource-limits.yaml`, per-user/group overrides) | Read directly from `/opt/ds01-infra/config/runtime/` on every operation | Changes apply immediately, no restart |
| `deploy/` | Source files installed **to** system locations (`/etc/systemd/`, `/etc/sudoers.d/`, `/etc/cron.d/`, `/etc/profile.d/`, …) | Installed by `sudo deploy` (`deploy.sh`), which runs automatically as part of every `ds01-sync` release | Install-time; a change here needs a release + `deploy` run to take effect |
| `state/` | **Documentation only** — describes the `/var/lib/ds01/` runtime-state layout | N/A (nothing under `config/state/` is deployed) | Reference |

See [Maintenance](./maintenance.md) for how updates and the `deploy`/`ds01-sync` split
actually run.

## `resource-limits.yaml`

Location: `config/runtime/resource-limits.yaml`. Central YAML defining per-user and
per-group GPU/CPU/memory limits, idle/runtime timeouts, and policies. Resolution
priority: `user_overrides` (in the same file, or in an optional standalone
`config/runtime/user-overrides.yaml`) → `groups.<group>` → `defaults`.

- Field-by-field reference and the GPU-equivalent (`gpueq`) quota model:
  [Quick reference](./quick-reference.md).
- Full directory/priority/override semantics: `config/CLAUDE.md`.
- Test a specific user's resolved limits: `python3 scripts/docker/get_resource_limits.py <username>`.
- Validate syntax: `python3 -c "import yaml; yaml.safe_load(open('config/runtime/resource-limits.yaml'))"`
  (also run automatically by `deploy.sh` before every deploy, and by `ds01-sync`'s
  pre-release smoke check).

**Don't hand-edit this file in prod** — `config-watchdog.sh --full` compares it
against the deployed source daily and reverts drift. See
[Maintenance → Config-watchdog drift handling](./maintenance.md#config-watchdog-drift-handling).

## Groups

Group membership (student/researcher/faculty/admin) is tracked in
`config/runtime/groups/*.members` (one file per group, plain username-per-line
lists) and kept in sync with `/home/` by `scripts/system/sync-group-membership.sh`
(daily cron, merge-only — never removes an entry). Two override files sit alongside
it in `config/runtime/`:

- `group-overrides.txt` — force a specific user into a group regardless of the
  username-pattern auto-classification (e.g. a PhD student with a numeric ID that
  would otherwise auto-classify as `student`).
- `user-overrides.yaml` — per-user resource-limit exceptions, independent of group.

Full mechanics (data flow, archiving users, troubleshooting a misclassified user):
`config/runtime/groups/README.md`.

## Permissions manifest

`config/permissions-manifest.sh` is the single source of truth for DS01 file
permissions, sourced by `deploy.sh` on every deploy. It re-asserts:

- `755` on the runtime tree (scripts, `config/`, `config/runtime/`) — a release built
  in the staging clone inherits that account's restrictive `umask 0077`, so this step
  is what keeps prod world-traversable after each `rsync`.
- `644` on YAML/env config files, `755` on executable scripts and `.so` libraries.
- Fixed, policy-specific modes on `/var/lib/ds01/` and `/var/log/ds01/` subdirectories
  (e.g. `1777` sticky on `rate-limits/`, `711` on `bare-metal-grants/`).

It's also re-run standalone every 15 minutes by cron (`ds01-maintenance`) to fix
drift from umask-affected manual edits — see
[Maintenance → Scheduled maintenance](./maintenance.md#scheduled-maintenance-cron).

## `variables.env`

`config/variables.env` holds the small set of deploy-time variables
(`INFRA_ROOT`, `STATE_DIR`, `LOG_DIR`, `DS01_ADMIN_GROUP`, `DOCKER_GROUP`) that
`deploy.sh` sources and substitutes into any `config/deploy/**/*.template` file via
`envsubst` (`fill_config_template()` in `deploy.sh`). Add a variable here only if it
appears in two or more config files.

## Related

- [config/CLAUDE.md](https://github.com/hertie-data-science-lab/ds01-infra/blob/main/config/CLAUDE.md) — full directory/file reference
- [Installation](./installation.md) — where these files come from on a fresh box
- [Maintenance](./maintenance.md) — how config changes actually reach prod, and drift handling
- [Quick reference](./quick-reference.md) — resource-limit values and the GPU-slot model
