# Setup Checklist

Condensed from [Installation](./installation.md) — full detail and grounding for each
step lives there. Use this as a fresh-box, top-to-bottom checklist.

## Prerequisites

- [ ] Ubuntu 20.04+ / Debian 11+
- [ ] NVIDIA GPU + driver installed
- [ ] Docker 20.10+ with NVIDIA Container Toolkit
- [ ] Python 3.8+ with PyYAML installed
- [ ] A `datasciencelab` system account with SSH (or HTTPS) access to fetch the repo

## Bootstrap

- [ ] Clone staging: `sudo -u datasciencelab git clone https://github.com/hertie-data-science-lab/ds01-infra /opt/ds01-staging`
- [ ] First release: `sudo /opt/ds01-staging/scripts/system/sync.sh`
  - [ ] Confirm it completed successfully (health-gated; auto-rolls back on failure)
- [ ] Configure Docker cgroups: `sudo /opt/ds01-infra/scripts/system/setup-docker-cgroups.sh`
  - [ ] Verify: `sudo ds01-verify-cgroup`
- [ ] Create resource-limit slices: `sudo /opt/ds01-infra/scripts/system/setup-resource-slices.sh && sudo systemctl daemon-reload`
- [ ] Install log rotation: `sudo cp /opt/ds01-infra/config/deploy/logrotate.d/ds01 /etc/logrotate.d/`

## Per-user onboarding

- [ ] `sudo /opt/ds01-infra/scripts/system/add-user-to-docker.sh <username>`
- [ ] Confirm the user's group placement in `config/runtime/groups/*.members` (see [System configuration](./system-config.md#groups))
- [ ] User logs out and back in
- [ ] User runs `user-setup`

## Verification

- [ ] `which user-setup container-create deploy ds01-sync`
- [ ] `sudo ds01-sync --list` shows a current-sha
- [ ] `version` reports the expected DS01 version and deployed SHA
- [ ] `sudo ds01-health` — no CRITICAL findings
- [ ] `systemctl status ds01.slice` — active
- [ ] `sudo docker run --rm alpine echo ok` — a container actually runs

## Optional

- [ ] `setup-opa-authz.sh` — only if moving off the parked OPA-plugin path
- [ ] `deploy-pam-bashrc.sh` / `deploy-automated-path.sh` — only if `/usr/local/bin` isn't
      showing up in `PATH` for some login path despite `config/deploy/profile.d/ds01-path.sh`

## If migrating an existing Phase-1 (live-git-checkout) prod

See [Installation → One-time cutover to detached prod](./installation.md#one-time-cutover-to-detached-prod)
instead of the bootstrap section above.
