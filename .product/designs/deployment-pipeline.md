# Deployment Pipeline

How DS01 configuration and scripts are deployed to the system via `deploy.sh`.

## Overview

`deploy.sh` is the master deployment script. It processes templates, validates configuration, deploys files to system locations, and enforces deterministic permissions. Designed to be idempotent — running it multiple times produces the same result.

## Pipeline Stages

```
deploy.sh invoked (sudo required)
    │
    ├── 1. Self-bootstrap re-exec
    │   └── Deployed copy re-execs from source to ensure latest version runs
    │
    ├── 2. Source variables
    │   └── config/variables.env → INFRA_ROOT, STATE_DIR, LOG_DIR, etc.
    │
    ├── 3. Validate configuration
    │   └── YAML syntax check on resource-limits.yaml
    │   └── Abort on invalid config (prevents broken deploy)
    │
    ├── 4. Process templates
    │   └── config/deploy/**/*.template → envsubst → validate no unsubstituted vars
    │
    ├── 5. Deploy to system locations
    │   ├── config/deploy/systemd/    → /etc/systemd/system/
    │   ├── config/deploy/profile.d/  → /etc/profile.d/
    │   ├── config/deploy/cron.d/     → /etc/cron.d/
    │   ├── config/deploy/sudoers.d/  → /etc/sudoers.d/
    │   ├── config/deploy/docker/     → /etc/docker/
    │   ├── config/deploy/modprobe.d/ → /etc/modprobe.d/
    │   ├── config/deploy/udev/       → /etc/udev/rules.d/
    │   └── config/deploy/wrappers/   → /usr/local/bin/
    │
    ├── 6. Generate systemd slices
    │   └── Per-user drop-in files for aggregate resource limits
    │
    ├── 7. Enforce permissions
    │   └── Source config/permissions-manifest.sh
    │   └── Deterministic chmod/chown on all deployed files
    │
    ├── 8. Sync video group
    │   └── Add exempt users, remove non-exempt users
    │
    ├── 9. Reload services
    │   └── systemctl daemon-reload
    │   └── Restart affected services
    │
    └── 10. Verify deployment
        └── Check critical files exist with correct permissions
```

## Template System

Files ending in `.template` contain variables like `${INFRA_ROOT}`, `${STATE_DIR}`, `${LOG_DIR}`.

Processing:
1. `fill_config_template()` reads template file.
2. `envsubst` substitutes variables from `config/variables.env`.
3. Validation: check for any remaining `${...}` patterns (indicates missing variable).
4. Write processed file to deployment target.

## Permissions Manifest

`config/permissions-manifest.sh` is the single source of truth for file permissions. Contains explicit `chmod`/`chown` commands for every deployed file and directory.

Key permission policies:
- Scripts: 755 (executable by all)
- Config files: 644 (readable by all)
- State directories: 775 root:docker (docker group can write)
- Event log: 664 root:docker (non-root users can log events)
- Bare-metal grants: 711 (traverse without listing)
- Rate limits: 1777 (world-writable with sticky bit)

Runs on every deploy — ensures correct state regardless of git checkout umask.

## Safety Features

- **YAML validation before deploy:** Catches syntax errors before they reach production.
- **Self-bootstrap:** Eliminates "run twice" bug where first deploy uses outdated copy of itself.
- **Idempotent:** Safe to run repeatedly. Skips unchanged files, removes stale configs.
- **Atomic operations:** Template files written via temp-file-then-rename.

## Invocation

```bash
sudo /opt/ds01-infra/scripts/system/deploy.sh
# or via deployed alias:
sudo deploy
```
