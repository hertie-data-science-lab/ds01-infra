# config/CLAUDE.md

Resource configuration and lifecycle-based hierarchy.

## Key Directories

| Directory | Purpose | Lifecycle |
|-----------|---------|-----------|
| `runtime/` | Operational configs read by scripts | Per-operation |
| `deploy/` | Files deployed TO /etc/ | Install-time |
| `state/` | Documents /var/lib/ds01 structure | Runtime persistence |

## Runtime Configuration (runtime/)

**Files read during normal operation:**

| File | Purpose |
|------|---------|
| `resource-limits.yaml` | Central resource configuration |
| `user-overrides.yaml` | Per-user exceptions |
| `group-overrides.txt` | Group assignment overrides |
| `groups/*.members` | Group membership lists |

**Configuration priority:**
1. `user_overrides.<username>` - Per-user exceptions (priority 100)
2. `groups.<group>` - Group-based limits (priority varies)
3. `defaults` - Fallback values

**Changes take effect immediately** - no restart needed.

## Deploy Configuration (deploy/)

**Directories deployed to system locations:**

| Source | Target | Purpose |
|--------|--------|---------|
| `systemd/` | `/etc/systemd/system/` | Service units, timers |
| `profile.d/` | `/etc/profile.d/` | Environment setup scripts |
| `sudoers.d/` | `/etc/sudoers.d/` | Sudo rules (440) |
| `cron.d/` | `/etc/cron.d/` | Scheduled jobs |
| `logrotate.d/` | `/etc/logrotate.d/` | Log rotation rules |
| `docker/` | `/etc/docker/` | Docker daemon config |
| `modprobe.d/` | `/etc/modprobe.d/` | Kernel module config |
| `udev/` | `/etc/udev/rules.d/` | Udev rules |
| `wrappers/` | `/usr/local/bin/` | Binary wrappers |

**Deployment:** `sudo deploy` runs deploy.sh

## Key Files

### resource-limits.yaml
**Location:** `config/runtime/resource-limits.yaml`

**Key sections:**
- `defaults` - Fallback limits for all users
- `groups` - Group-based limit profiles
- `gpu_allocation` - GPU/MIG configuration
- `policies` - System-wide policies
- `container_types` - External container settings
- `bare_metal_access` - Host GPU access control
- `access_control` - Docker wrapper settings

**Example:**
```yaml
defaults:
  max_mig_instances: 1
  max_cpus: 8
  memory: "32g"

groups:
  researcher:
    max_mig_instances: 2
    memory: "64g"

user_overrides:
  charlie:
    max_mig_instances: 3
    # Reason: Thesis work
```

### groups/*.members
**Location:** `config/runtime/groups/*.members`
**Format:** One username per line, # for comments

```
# config/runtime/groups/researcher.members
204214@hertie-school.lan          # Silke Kaiser (PhD)
c.fusarbassini@hertie-school.lan  # Chiara Fusarbassini
```

### variables.env
**Location:** `config/variables.env`
**Purpose:** Deploy-time variables for template generation

```bash
INFRA_ROOT="/opt/ds01-infra"
STATE_DIR="/var/lib/ds01"
LOG_DIR="/var/log/ds01"
DS01_ADMIN_GROUP="ds01-admin"
DOCKER_GROUP="docker"
```

**Sourced by:** deploy.sh during deployment

### permissions-manifest.sh
**Location:** `config/permissions-manifest.sh`
**Purpose:** Single source of truth for file permissions

**Sourced by:** deploy.sh on every run to enforce deterministic permissions.

## Configuration Lifecycle

### Runtime (runtime/)
- **Read:** During container creation, allocation, access checks
- **Reloads:** Automatic - changes immediate
- **Test:** `python3 scripts/docker/get_resource_limits.py <username>`

### Deploy (deploy/)
- **Deployed:** Via `sudo deploy`
- **Target:** System directories (/etc/, /usr/local/bin/)
- **Reloads:** Requires deploy.sh run

### State (state/)
- **Location:** `/var/lib/ds01/`
- **Purpose:** Runtime state (grants, rate-limits, workload inventory)
- **Documentation:** See [state/README.md](state/README.md)

## Generative Config Pipeline

**Function:** `fill_config_template()` in deploy.sh

**Template pattern:**
1. Create file with `.template` extension
2. Use variable syntax: `${INFRA_ROOT}`, `${STATE_DIR}`
3. deploy.sh automatically processes templates
4. Validates no unsubstituted variables remain

**Example:**
```bash
# example.sh.template
export PATH="${INFRA_ROOT}/scripts/user/dispatchers:$PATH"
```

## Common Operations

### Modify User Limits

```bash
# Add user to group
nano config/runtime/groups/researcher.members
python3 scripts/docker/get_resource_limits.py username

# Add user override
nano config/runtime/user-overrides.yaml
python3 scripts/docker/get_resource_limits.py username
```

### Deploy Configuration

```bash
# Deploy all configs
sudo deploy

# Verbose output
sudo deploy --verbose

# Verify deployment
ls -l /etc/profile.d/ds01-*
```

### Validate Configuration

```bash
# YAML validation
python3 -c "import yaml; yaml.safe_load(open('config/runtime/resource-limits.yaml'))"

# Test user limits
python3 scripts/docker/get_resource_limits.py alice
```

## Migration Notes (Phase 3.2-03)

**Changed structure:**
- `config/resource-limits.yaml` → `config/runtime/resource-limits.yaml`
- `config/groups/` → `config/runtime/groups/`
- `config/etc-mirrors/profile.d/` → Consolidated into `config/deploy/profile.d/`
- `config/etc-mirrors/sudoers.d/` → Consolidated into `config/deploy/sudoers.d/`

**Deprecated:**
- `config/etc-mirrors/` - Marked deprecated, absorbed into deploy/

**Added:**
- `config/variables.env` - Deploy-time variables
- `config/runtime/` - Runtime configuration hierarchy
- `config/state/` - State documentation
- `fill_config_template()` - Template generation function
- YAML validation in deploy.sh

## Related Documentation

- [README.md](README.md) - Comprehensive configuration guide
- [state/README.md](state/README.md) - Persistent state structure
- [runtime/groups/README.md](runtime/groups/README.md) - Group membership format
- [/CLAUDE.md](../CLAUDE.md) - Root project documentation
