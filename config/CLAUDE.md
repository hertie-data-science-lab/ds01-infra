# config/CLAUDE.md

Resource configuration and group management.

## Key Files

| File | Purpose |
|------|---------|
| `resource-limits.yaml` | Central resource configuration |
| `groups/*.members` | Group membership lists |
| `deploy/` | Files to deploy TO /etc/ |
| `etc-mirrors/` | Reference copies FROM /etc/ |

## Configuration Priority

Resolution order (highest to lowest):
1. `user_overrides.<username>` - Per-user exceptions (priority 100)
2. `groups.<group>` - Group-based limits (priority varies)
3. `defaults` - Fallback values

## Key Configuration Fields

### Resource Limits
| Field | Description | Example |
|-------|-------------|---------|
| `max_mig_instances` | Max GPUs/MIG instances per user | `2` |
| `max_gpus_per_container` | Max GPUs per single container | `1` |
| `allow_full_gpu` | Access to non-MIG GPUs | `false` |
| `max_cpus` | CPU cores per container | `8` |
| `memory` | RAM per container | `"32g"` |
| `shm_size` | Shared memory | `"8g"` |
| `max_containers_per_user` | Simultaneous containers | `3` |

### Lifecycle Limits
| Field | Description | Example |
|-------|-------------|---------|
| `idle_timeout` | Auto-stop after GPU inactivity | `"48h"` |
| `max_runtime` | Maximum container runtime | `"168h"` |
| `gpu_hold_after_stop` | Hold GPU after stop | `"0.25h"` |
| `container_hold_after_stop` | Auto-remove after stop | `"0.5h"` |

### Special Values
- `null` for `max_mig_instances` = unlimited (admin only)
- `null` for timeouts = disabled

## Group Access Control

| Group | MIG Access | Full GPU | Priority |
|-------|------------|----------|----------|
| `student` | Yes | No | 10 |
| `researcher` | Yes | Yes | 50 |
| `faculty` | Yes | Yes | 75 |
| `admin` | Unlimited | Yes | 100 |

## Example Configuration

```yaml
defaults:
  max_mig_instances: 1
  max_cpus: 8
  memory: "32g"
  max_containers_per_user: 3
  idle_timeout: "48h"
  allow_full_gpu: false
  priority: 10

groups:
  researchers:
    members: [alice, bob]
    max_mig_instances: 2
    memory: "64g"
    allow_full_gpu: true
    priority: 50

user_overrides:
  charlie:
    max_mig_instances: 3
    priority: 100
    reason: "Thesis work - approved 2025-11-15"
```

## MIG Configuration

In `gpu_allocation` section:
```yaml
gpu_allocation:
  enable_mig: true
  mig_profile: "2g.20gb"  # 3 instances per A100
```

MIG instances tracked as `"physical_gpu:instance"` (e.g., `"0:0"`, `"0:1"`).

## Testing Changes

```bash
# Test for specific user
python3 scripts/docker/get_resource_limits.py <username>

# Validate YAML syntax
python3 -c "import yaml; yaml.safe_load(open('resource-limits.yaml'))"

# Changes take effect immediately (no restart needed)
```

## Deploy Directory

Files in `deploy/` are templates to copy TO system locations:
- `deploy/cron.d/` → `/etc/cron.d/`
- `deploy/logrotate.d/` → `/etc/logrotate.d/`
- `deploy/profile.d/` → `/etc/profile.d/`
- `deploy/systemd/` → `/etc/systemd/system/`

---

**Parent:** [/CLAUDE.md](../../CLAUDE.md) | **Related:** [README.md](README.md)
