# Configuration - Resource Limits & Policies

Central configuration for DS01 resource management.

## Overview

DS01 configuration follows a **lifecycle-based hierarchy**:

| Directory | Purpose | Lifecycle | Examples |
|-----------|---------|-----------|----------|
| `runtime/` | Operational configs read during execution | Per-operation | resource-limits.yaml, groups/*.members |
| `deploy/` | Files deployed TO /etc/ during installation | Install-time | systemd units, profile.d scripts |
| `state/` | Documents persistent state structure | Runtime persistence | /var/lib/ds01 layout |

**Key principle:** Clear separation between install-time configuration (deploy/), runtime configuration (runtime/), and persistent state (state/).

## Directory Structure

```
config/
├── variables.env            # Deploy-time variables
├── runtime/                 # Runtime configuration (read by scripts)
│   ├── resource-limits.yaml # Main config (defaults, groups, policies)
│   ├── user-overrides.yaml  # Per-user exceptions
│   ├── group-overrides.txt  # Group assignment overrides
│   └── groups/              # Group membership lists
│       ├── student.members
│       ├── researcher.members
│       ├── faculty.members
│       └── admin.members
├── deploy/                  # Install-time configs (deployed TO /etc/)
│   ├── systemd/             # Service units → /etc/systemd/system/
│   ├── profile.d/           # Environment scripts → /etc/profile.d/
│   ├── sudoers.d/           # Sudo rules → /etc/sudoers.d/
│   ├── cron.d/              # Cron jobs → /etc/cron.d/
│   ├── logrotate.d/         # Log rotation → /etc/logrotate.d/
│   ├── docker/              # Docker daemon config
│   ├── modprobe.d/          # Kernel module config
│   ├── udev/                # Udev rules
│   └── wrappers/            # Binary wrappers → /usr/local/bin/
├── state/                   # State directory documentation
│   └── README.md            # Documents /var/lib/ds01 structure
├── permissions-manifest.sh  # File permission definitions (sourced by deploy.sh)
├── container-aliases.sh     # Docker command aliases
└── README.md                # This file
```

## Configuration Lifecycle

### 1. Runtime Configuration (runtime/)

**Read by:** Scripts during normal operation
**When:** Every container creation, allocation, access check
**Reloads:** Automatically (no restart needed)

**Files:**
- `resource-limits.yaml` - User limits, group settings, policies
- `user-overrides.yaml` - Per-user exceptions
- `group-overrides.txt` - Group assignment overrides
- `groups/*.members` - Group membership lists

**Usage:**
```bash
# Changes take effect immediately
python3 scripts/docker/get_resource_limits.py alice

# Validate YAML syntax
python3 -c "import yaml; yaml.safe_load(open('config/runtime/resource-limits.yaml'))"
```

### 2. Deploy-Time Configuration (deploy/)

**Deployed by:** `sudo deploy` (deploy.sh script)
**When:** Installation, upgrades, config changes
**Target:** System directories (/etc/, /usr/local/bin/)

**Deployment:**
```bash
# Deploy all configs
sudo deploy

# Or manually
sudo cp config/deploy/systemd/ds01-*.service /etc/systemd/system/
sudo systemctl daemon-reload
```

**Template support:**
Files ending in `.template` are processed through envsubst with variables from `variables.env`.

### 3. Persistent State (state/)

**Location:** `/var/lib/ds01/`
**Purpose:** Runtime state files (grants, rate-limits, workload inventory)
**Documentation:** See [state/README.md](state/README.md)

## Source of Truth Files

### resource-limits.yaml
**Location:** `config/runtime/resource-limits.yaml`
**Purpose:** Main configuration for resource limits and policies

**Key sections:**
- `defaults` - Fallback limits for all users
- `groups` - Group-based limit profiles
- `gpu_allocation` - GPU/MIG configuration
- `policies` - System-wide policies
- `container_types` - External container settings
- `bare_metal_access` - Host GPU access control
- `access_control` - Docker wrapper settings

**Priority order:** user_overrides > groups > defaults

### groups/*.members
**Location:** `config/runtime/groups/*.members`
**Format:** One username per line, # for comments

```
# config/runtime/groups/researcher.members
204214@hertie-school.lan          # Silke Kaiser (PhD)
c.fusarbassini@hertie-school.lan  # Chiara Fusarbassini
```

### user-overrides.yaml
**Location:** `config/runtime/user-overrides.yaml`
**Purpose:** Per-user exceptions to group limits

```yaml
204214@hertie-school.lan:
  idle_timeout: null      # No timeout
  max_runtime: null       # No runtime limit
  # Reason: Thesis work - approved 2025-XX-XX
```

### group-overrides.txt
**Location:** `config/runtime/group-overrides.txt`
**Purpose:** Override automatic group classification
**Format:** `username:group`

```
204214@hertie-school.lan:researcher     # PhD student
h.baker@hertie-school.lan:admin         # Admin account
```

## Deploy Configuration

### Profile.d Scripts
**Source:** `config/deploy/profile.d/`
**Target:** `/etc/profile.d/`
**Purpose:** Environment setup for login shells

**Key scripts:**
- `ds01-gpu-awareness.sh` - CUDA_VISIBLE_DEVICES control
- `ds01-docker-group.sh` - Auto-add users to docker group
- `ds01-path.sh` - PATH configuration
- `ds01-motd.sh` - Login messages
- `ds01-warnings.sh` - Security warnings
- `ds01-home-enforce.sh` - Home directory enforcement

### Systemd Units
**Source:** `config/deploy/systemd/`
**Target:** `/etc/systemd/system/`

**Services:**
- `ds01-workload-detector.timer/service` - GPU workload detection (60s)
- `ds01-container-owner-tracker.service` - Container ownership tracking
- `ds01-dcgm-exporter.service` - DCGM metrics exporter
- `ds01-exporter.service` - Node exporter

### Sudoers Rules
**Source:** `config/deploy/sudoers.d/`
**Target:** `/etc/sudoers.d/`
**Permissions:** 440 (read-only by sudo)

**Files:**
- `ds01-docker-group` - Allow docker group addition
- `ds01-user-slice` - Allow user slice creation

### Cron Jobs
**Source:** `config/deploy/cron.d/`
**Target:** `/etc/cron.d/`

**Jobs:**
- `ds01-maintenance` - Cleanup and maintenance tasks

### Logrotate Rules
**Source:** `config/deploy/logrotate.d/`
**Target:** `/etc/logrotate.d/`

**Files:**
- `ds01` - DS01 log rotation (copytruncate for JSONL)

## Variables (variables.env)

**Purpose:** Deploy-time variables for template generation and environment-specific values

**Current variables:**
```bash
INFRA_ROOT="/opt/ds01-infra"
STATE_DIR="/var/lib/ds01"
LOG_DIR="/var/log/ds01"
DS01_ADMIN_GROUP="ds01-admin"
DOCKER_GROUP="docker"
```

**Sourced by:** deploy.sh during deployment

**Template usage:**
```bash
# In template file (*.template)
export INFRA_ROOT="${INFRA_ROOT}"

# Processed by fill_config_template() function
# Variables substituted via envsubst
```

## Generative Config Pipeline

**Function:** `fill_config_template()` in deploy.sh

**Usage:**
1. Create template file: `config/deploy/profile.d/example.sh.template`
2. Use variable syntax: `${INFRA_ROOT}`, `${STATE_DIR}`
3. Deploy.sh automatically processes `.template` files
4. Validates no unsubstituted variables remain

**Example template:**
```bash
# example.sh.template
export PATH="${INFRA_ROOT}/scripts/user/dispatchers:$PATH"
export DS01_STATE="${STATE_DIR}"
```

**Validation:**
```bash
# Automatic during deploy.sh
# - Sources variables.env
# - Runs envsubst on template
# - Checks for ${VAR} patterns in output
# - Warns if unsubstituted variables found
```

## Configuration Priority

Limits resolved with this precedence (highest to lowest):
1. **user_overrides.<username>** - Explicit per-user settings
2. **groups.<group>** - Group membership
3. **defaults** - System fallback

**Example:**
```yaml
defaults:
  max_mig_instances: 1
  memory: "32g"

groups:
  researcher:
    max_mig_instances: 2
    memory: "64g"

user_overrides:
  alice:
    max_mig_instances: 3
    # memory: "64g" inherited from group
```

**Alice's final limits:**
- max_mig_instances: 3 (from user_overrides)
- memory: "64g" (from group)
- Everything else from defaults

## Common Operations

### Modify User Limits

**Add user to group:**
```bash
# Edit group member file
nano config/runtime/groups/researcher.members
# Add line: username@domain

# Test
python3 scripts/docker/get_resource_limits.py username@domain

# No restart needed - changes immediate
```

**Add user override:**
```bash
# Edit overrides file
nano config/runtime/user-overrides.yaml

# Add:
username@domain:
  max_mig_instances: 4
  idle_timeout: null
  # Reason: Special project

# Test
python3 scripts/docker/get_resource_limits.py username@domain
```

### Modify Group Limits

```bash
# Edit resource limits
nano config/runtime/resource-limits.yaml

# Change group settings
groups:
  researcher:
    max_mig_instances: 3  # Changed from 2
    memory: "96g"         # Changed from 64g

# Validate
python3 -c "import yaml; yaml.safe_load(open('config/runtime/resource-limits.yaml'))"

# No restart needed
```

### Deploy Configuration Changes

```bash
# After modifying deploy/ files
sudo deploy

# View verbose output
sudo deploy --verbose

# Check specific deployments
ls -l /etc/profile.d/ds01-*
ls -l /etc/systemd/system/ds01-*
```

### Validate Configuration

**YAML syntax:**
```bash
python3 -c "import yaml; yaml.safe_load(open('config/runtime/resource-limits.yaml'))"
# No output = valid
```

**User limits:**
```bash
# Check specific user
python3 scripts/docker/get_resource_limits.py alice

# Check multiple users
for user in alice bob charlie; do
    echo "=== $user ==="
    python3 scripts/docker/get_resource_limits.py $user
done
```

**Template generation:**
```bash
# Manual test
source config/variables.env
envsubst < config/deploy/profile.d/example.sh.template
```

## Migration Notes (Phase 3.2-03)

**Changed:**
- `config/resource-limits.yaml` → `config/runtime/resource-limits.yaml`
- `config/groups/` → `config/runtime/groups/`
- `config/user-overrides.yaml` → `config/runtime/user-overrides.yaml`
- `config/group-overrides.txt` → `config/runtime/group-overrides.txt`
- `config/etc-mirrors/profile.d/` → Consolidated into `config/deploy/profile.d/`
- `config/etc-mirrors/sudoers.d/` → Consolidated into `config/deploy/sudoers.d/`

**Removed:**
- `config/etc-mirrors/` - Marked deprecated, absorbed into deploy/

**Added:**
- `config/variables.env` - Deploy-time variables
- `config/runtime/` - Runtime configuration hierarchy
- `config/state/` - State documentation
- `fill_config_template()` function in deploy.sh
- YAML validation in deploy.sh

**Script updates:**
- `scripts/docker/get_resource_limits.py` - Updated paths to runtime/
- `config/deploy/profile.d/ds01-gpu-awareness.sh` - Updated resource-limits.yaml path
- `scripts/system/deploy.sh` - Removed etc-mirrors loop, added validation

## Troubleshooting

### Config File Not Found

```bash
# Check file location
ls -l config/runtime/resource-limits.yaml

# Verify script paths
grep "resource-limits.yaml" scripts/docker/get_resource_limits.py
```

### YAML Syntax Error

```bash
# Validate and see error
python3 -c "import yaml; yaml.safe_load(open('config/runtime/resource-limits.yaml'))"

# Common issues:
# - Incorrect indentation (use spaces, not tabs)
# - Missing colon after key
# - Unquoted special characters
```

### Changes Not Applied

**Runtime configs:** Take effect immediately (no restart)
```bash
python3 scripts/docker/get_resource_limits.py username
```

**Deploy configs:** Need deploy.sh run
```bash
sudo deploy
sudo systemctl daemon-reload  # If systemd units changed
```

### Template Variables Not Substituted

```bash
# Check variables.env exists and is sourced
ls -l config/variables.env
source config/variables.env
echo $INFRA_ROOT

# Check template syntax
grep '\${' config/deploy/profile.d/*.template

# Run deploy with verbose
sudo deploy --verbose
```

## Related Documentation

- [state/README.md](state/README.md) - Persistent state structure
- [runtime/groups/README.md](runtime/groups/README.md) - Group membership format
- [scripts/docker/README.md](../scripts/docker/README.md) - How limits are enforced
- [scripts/system/README.md](../scripts/system/README.md) - Deployment internals
