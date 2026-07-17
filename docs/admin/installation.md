# Installation

How DS01 is bootstrapped on a fresh box, and how an existing Phase-1-style
install (prod as a live git checkout) is cut over to the current **detached-prod**
model. For the day-to-day update/rollback flow once installed, see
[Maintenance](./maintenance.md); for the release/tag mechanics, see
[Versioning](./versioning.md).

## The model, in one paragraph

Prod (`/opt/ds01-infra`) is a **detached** directory — a real tree with **no `.git`**.
It is never `git pull`ed or checked out directly. The canonical checkout lives in a
**staging clone** at `/opt/ds01-staging`; every release is built and smoke-tested there
by `ds01-sync` (`scripts/system/sync.sh`) before being rsynced to prod, side-effected
(`deploy.sh`), and health-gated. See [scripts/system/CLAUDE.md](https://github.com/hertie-data-science-lab/ds01-infra/blob/main/scripts/system/CLAUDE.md) for the full deploy-model
writeup this doc builds on.

## Prerequisites

| Requirement | Notes |
|-------------|-------|
| OS | Ubuntu 20.04+ / Debian 11+ |
| GPU | NVIDIA GPU with MIG support (A100, H100) or any CUDA GPU |
| Docker | 20.10+ with NVIDIA Container Toolkit |
| Python | 3.8+ with PyYAML (`sudo pip3 install pyyaml` or `sudo apt install python3-yaml`) |
| A `datasciencelab` system account | Owns the staging clone and runs `ds01-sync`'s git operations; needs SSH (or HTTPS, since the repo is public) access to fetch `origin` |

## Fresh-box bootstrap

**1. Create the staging clone** (owned by `datasciencelab` — `ds01-sync` always runs
git as this user, never as root, to avoid tripping git's dubious-ownership guard and
because SSH auth lives in that account):

```bash
sudo -u datasciencelab git clone https://github.com/hertie-data-science-lab/ds01-infra /opt/ds01-staging
```

**2. First release.** Prod doesn't exist yet, so run `sync.sh` directly from staging
(before `deploy.sh` has had a chance to symlink `ds01-sync` into `/usr/local/bin/`):

```bash
sudo /opt/ds01-staging/scripts/system/sync.sh
```

This builds + smoke-tests `origin/main` in staging, rsyncs it to `/opt/ds01-infra`
(creating it), and — as part of the same run — executes `deploy.sh`'s side-effects:
symlinks all commands into `/usr/local/bin/` (including `deploy` and `ds01-sync`
themselves), installs `config/deploy/{profile.d,sudoers.d,cron.d}/*` into `/etc/`,
installs the workload-detector and code-caching-daemon systemd units, and enforces
the permissions manifest. It then health-gates the result and only advances
`current-sha` (in `/var/lib/ds01/deploy/`) on success. From here on, `ds01-sync` is
on `PATH`.

**3. Configure Docker for cgroup enforcement** (one-time host config; not part of the
per-release `deploy.sh` flow):

```bash
sudo /opt/ds01-infra/scripts/system/setup-docker-cgroups.sh
```

Sets `native.cgroupdriver=systemd` and `cgroup-parent=ds01.slice` in
`/etc/docker/daemon.json`, configures the `nvidia` runtime, creates `ds01.slice` if
missing, and restarts Docker. Verify with `sudo ds01-verify-cgroup` (deployed by step 2;
wraps `verify-cgroup-driver.sh`).

**4. Create the resource-limit systemd slices:**

```bash
sudo /opt/ds01-infra/scripts/system/setup-resource-slices.sh
sudo systemctl daemon-reload
```

Reads `config/runtime/resource-limits.yaml` and creates `ds01.slice` +
`ds01-{group}.slice` per group (accounting only — per-container limits are enforced
via Docker flags, not slice quotas; see [system-config.md](./system-config.md)).
Per-user slices (`ds01-{group}-{username}.slice`) are created automatically on a
user's first container, via `create-user-slice.sh`.

**5. Add users:**

```bash
sudo /opt/ds01-infra/scripts/system/add-user-to-docker.sh <username>
```

Adds the user to the `docker` and `video` groups (Linux users must already exist —
this script doesn't create accounts). The user must log out and back in, then run
`user-setup` for onboarding. Group membership for resource limits (student/researcher/
faculty) is populated separately — see [system-config.md](./system-config.md#groups).

**6. Install log rotation** (not installed automatically by `deploy.sh`):

```bash
sudo cp /opt/ds01-infra/config/deploy/logrotate.d/ds01 /etc/logrotate.d/
```

**7. Optional / not required for a standard install:**

- `setup-opa-authz.sh` — OPA Docker-authorization plugin. Currently **parked**: the
  Docker wrapper (`docker-wrapper.sh`, deployed as `/usr/local/bin/docker` in step 2)
  already handles container-visibility filtering and cgroup-parent injection.
- `deploy-pam-bashrc.sh` / `deploy-automated-path.sh` — supplementary PATH/`.bashrc`
  robustness for login paths that don't source `/etc/profile.d` (which `deploy.sh`
  already installs `ds01-path.sh` into via step 2, covering normal SSH logins). Not
  wired into `deploy.sh`; run manually only if some login path isn't picking up
  `/usr/local/bin`.

  > **TODO:** whether these PAM/bashrc scripts are still needed on top of
  > `config/deploy/profile.d/ds01-path.sh` for this box's actual login paths isn't
  > established in code — verify against a real login session before relying on them.

**8. Verify:**

```bash
which user-setup container-create deploy ds01-sync
sudo ds01-sync --list          # current-sha + release history
version                        # DS01 version, deployed SHA, GPU/Docker info
sudo ds01-health                # post-deploy health probe (same checks ds01-sync runs)
systemctl status ds01.slice
```

See [Setup checklist](./setup-checklist.md) for a condensed version of the above.

## One-time cutover to detached prod

This section applies only when migrating a box where `/opt/ds01-infra` **already
exists as a live git checkout** (the pre-`ds01-sync` "Phase 1" interim model) to the
current detached-prod model. On a genuinely fresh box (bootstrap above), prod is
created directly by `rsync` and never has a `.git` — there is nothing to cut over.

> **TODO:** the exact sequence used historically for this deployment's own cutover
> isn't recorded in code or commit history available to this doc. The steps below are
> the minimum the current scripts require/support; verify order and specifics before
> repeating this on another box.

1. **Ensure the staging clone exists** at `/opt/ds01-staging` (step 1 above), with a
   full history of `main` — `ds01-sync` will build releases from it going forward.
2. **Add a `downstream` remote to the staging clone**, if off-site backup via
   `sync-downstream.sh` is wanted (see [Maintenance → Downstream backup](./maintenance.md#downstream-backup)):
   ```bash
   sudo -u datasciencelab git -C /opt/ds01-staging remote add downstream <remote-url>
   ```
3. **Back up the existing prod checkout** before touching it — it may contain
   uncommitted or git-ignored runtime state (`config/runtime/*.members`,
   `user-overrides.yaml`, etc.) that must survive the cutover:
   ```bash
   sudo tar -czf /root/ds01-infra-precutover-$(date +%Y%m%d).tar.gz -C /opt ds01-infra
   ```
4. **Reconcile any prod-only state** into the staging clone or into
   `config/runtime/` on disk (it's git-ignored there and survives an `rsync` without
   `--delete` — see `sync.sh`'s `release_to_prod`), so nothing is lost when `.git` is
   removed.
5. **Remove prod's `.git`** — this is what "detaches" prod and is what `ds01-sync`
   checks for (`sync.sh` refuses to run while `/opt/ds01-infra/.git` exists):
   ```bash
   sudo rm -rf /opt/ds01-infra/.git
   ```
6. **Run the first detached release:**
   ```bash
   sudo /opt/ds01-staging/scripts/system/sync.sh
   ```
   `current-sha` didn't exist before this point; `sync.sh` treats that as "no previous
   SHA" and simply publishes the release, populating `/var/lib/ds01/deploy/current-sha`
   on success — no manual state-seeding needed.
7. **Retire the Phase-1 interim safety net.** If `install-prod-git-guards.sh` had been
   run against the old prod checkout (it points `core.hooksPath` at `.githooks/` to
   block commits/rebases in prod while it still had `.git`), it's now inert — there's
   no repository left for hooks to run against. No action needed; it's harmless to
   leave configured.

From this point on, prod is managed exclusively via `ds01-sync` — see
[Maintenance](./maintenance.md).
