# scripts/system/CLAUDE.md

System administration, deployment, and user management.

## Key Files

| File | Purpose |
|------|---------|
| `sync.sh` | `ds01-sync` — detached-prod release orchestrator: builds + smoke-tests in `/opt/ds01-staging`, rsyncs to `/opt/ds01-infra`, runs `deploy.sh`, health-gates, auto-rolls-back |
| `deploy.sh` | Side-effects stage (symlinks to /usr/local/bin, manifest/permissions, systemd units, sudoers, code-caching daemon restarts) — invoked by `ds01-sync`, or standalone to reapply side-effects against whatever is already on disk |
| `install-prod-git-guards.sh` | Installs repo-owned git hooks (`.githooks/`) that refuse commits/rebases in the prod checkout — interim belt-and-suspenders, inert once prod has no `.git` |
| `add-user-to-docker.sh` | Add user to docker group with proper setup |
| `setup-resource-slices.sh` | Create systemd cgroup slices |
| `create-user-slice.sh` | Create per-user systemd slice |
| `setup-docker-cgroups.sh` | Configure Docker for cgroup enforcement |
| `setup-opa-authz.sh` | Configure OPA authorization (parked) |
| `deploy-cron-jobs.sh` | Deploy cron job configurations |
| `deploy-pam-bashrc.sh` | Deploy PAM/bashrc configurations |

## Deployment model

`/opt/ds01-infra` (prod) is a **detached** directory — a real tree with no `.git`. It is
never `git pull`ed or checked out directly. Updates go through `ds01-sync`, which builds
and smoke-tests each release in the `/opt/ds01-staging` clone before publishing:

```bash
# Update prod to latest main (or a specific tag)
sudo ds01-sync
sudo ds01-sync --ref v1.6.0
sudo ds01-sync --rollback   # re-release the previous good SHA
sudo ds01-sync --list       # release history + current SHA

# Reapply side-effects only (symlinks/systemd/sudoers) against the CODE ALREADY
# ON DISK in prod — does not fetch or change code
sudo deploy
```

CI triggers `ds01-sync --ref <tag>` on a pushed `v*.*.*` tag via `.github/workflows/deploy.yml`
(self-hosted runner). Dev happens in a separate clone (e.g. `~/workspace/ds01-infra`); never
edit or `git` in `/opt/ds01-infra` or `/opt/ds01-staging`.

## Common Operations

```bash
# Add new user
sudo scripts/system/add-user-to-docker.sh <username>
# User must log out and back in

# Setup systemd slices
sudo scripts/system/setup-resource-slices.sh
sudo systemctl daemon-reload

# Create user-specific slice
sudo scripts/system/create-user-slice.sh <username> <group>
```

## Systemd Slice Hierarchy

```
ds01.slice (root)
├── ds01-student.slice
│   ├── ds01-student-alice.slice
│   └── ds01-student-bob.slice
├── ds01-researcher.slice
│   └── ds01-researcher-carol.slice
└── ds01-admin.slice
    └── ds01-admin-dave.slice
```

## User Addition Workflow

1. `add-user-to-docker.sh` adds user to `docker` group
2. Creates user slice if not exists
3. User logs out and back in
4. User runs `user-setup` for onboarding

## Notes

- All scripts require root/sudo
- Docker wrapper (`/usr/local/bin/docker`) injects cgroup-parent automatically
- OPA authorization currently parked (wrapper handles visibility filtering)
- PAM scripts handle docker group and bashrc for new logins
- `deploy.sh` sources `config/permissions-manifest.sh` for deterministic file permissions

## Phase 3.2 Improvements

**deploy.sh enhancements (Plans 02, 03):**
- YAML validation: Pre-deployment validation prevents broken resource-limits.yaml from reaching production
- Generative config pipeline: `fill_config_template()` function supports template-based configuration
- Config consolidation: Single deployment source (config/deploy/), lifecycle-based hierarchy
- Template pattern: Auto-processes *.template files with variable substitution (envsubst)

**Config structure:**
- `config/deploy/` - Install-time files (TO /etc/)
- `config/runtime/` - Operational configs (read by scripts)
- `config/state/` - Documentation of persistent state structure
- `config/variables.env` - Deploy-time variables for template generation

---

**Parent:** [/CLAUDE.md](../../CLAUDE.md) | **Related:** [README.md](README.md)
