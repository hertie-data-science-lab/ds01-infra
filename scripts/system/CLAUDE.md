# scripts/system/CLAUDE.md

System administration, deployment, and user management.

## Key Files

| File | Purpose |
|------|---------|
| `deploy.sh` | Deploy DS01 commands to /usr/local/bin |
| `add-user-to-docker.sh` | Add user to docker group with proper setup |
| `setup-resource-slices.sh` | Create systemd cgroup slices |
| `create-user-slice.sh` | Create per-user systemd slice |
| `setup-docker-cgroups.sh` | Configure Docker for cgroup enforcement |
| `setup-opa-authz.sh` | Configure OPA authorization (parked) |
| `deploy-cron-jobs.sh` | Deploy cron job configurations |
| `deploy-pam-bashrc.sh` | Deploy PAM/bashrc configurations |

## Common Operations

```bash
# Deploy commands (after editing scripts)
sudo scripts/system/deploy.sh
# or use alias:
sudo deploy

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

---

**Parent:** [/CLAUDE.md](../../CLAUDE.md) | **Related:** [README.md](README.md)
