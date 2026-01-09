# scripts/admin/CLAUDE.md

Admin tools, dashboards, and system management utilities.

## Key Files

| File | Purpose |
|------|---------|
| `dashboard` | Main system dashboard (GPU, containers, system status) |
| `ds01-logs` | Log viewer and search |
| `ds01-users` | User management utilities |
| `mig-configure` | Interactive MIG configuration CLI |
| `alias-list` | List all available DS01 commands |
| `alias-create` | Create command aliases |
| `user-activity-report` | Generate user activity reports |
| `help` | System help |
| `version` | Show DS01 version |

## Common Operations

```bash
# System dashboard
dashboard                    # Default snapshot view
dashboard interfaces         # Containers by interface
dashboard users              # Per-user breakdown
dashboard monitor            # Watch mode (1s refresh)

# Log viewing
ds01-logs                    # View recent logs
ds01-logs gpu                # GPU allocation logs
ds01-logs container          # Container logs

# User management
ds01-users list              # List all users
ds01-users activity          # User activity summary

# MIG configuration
mig-configure                # Interactive MIG setup
mig-configure --reset        # Reset MIG configuration

# Command reference
alias-list                   # Show all DS01 commands
help                         # General help
version                      # Show version
```

## Dashboard Views

The `dashboard` command supports multiple views:
- **Default**: Snapshot of GPU, containers, system
- **interfaces**: Containers grouped by interface (DS01/Docker/Other)
- **users**: Per-user resource breakdown
- **monitor**: Real-time watch mode

## Notes

- Admin commands prefixed with `ds01-` for clarity
- Dashboard reads from `/var/lib/ds01/` state files
- MIG configuration requires root and GPU processes to be stopped
- `bypass-enforce-containers.sh` for emergency container access

---

**Parent:** [/CLAUDE.md](../../CLAUDE.md) | **Related:** [README.md](README.md)
