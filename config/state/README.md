# State Directory Structure

This directory documents the persistent state structure at `/var/lib/ds01/`.

## Directory Structure

```
/var/lib/ds01/
├── bare-metal-grants/       # 711 (drwx--x--x) - GPU bare-metal access grants
│   └── <username>.json      # Grant files (JSON)
├── rate-limits/             # 1777 (drwxrwxrwt) - Rate limiting state
│   └── <user>_<operation>   # Rate limit timestamps
├── container-states/        # 700 (drwx------) - Container lifecycle state
├── container-runtime/       # 700 (drwx------) - Runtime container metadata
├── opa/                     # 755 (drwxr-xr-x) - OPA authorization state
├── alerts/                  # 755 (drwxr-xr-x) - Alert state
├── log-archives/            # 700 (drwx------) - Archived logs
├── backups/                 # 700 (drwx------) - Configuration backups
├── workload-inventory.json  # 644 - Current GPU workload inventory
└── gpu-queue.json           # 644 - GPU allocation queue
```

## Directory Purposes

### bare-metal-grants/
**Purpose:** Stores temporary and permanent GPU bare-metal access grants
**Permissions:** `711` - Users can access their own grant file but can't list directory
**Created by:** `bare-metal-access grant <user> [duration]` command
**Read by:** `config/deploy/profile.d/ds01-gpu-awareness.sh` (checks for grant file at login)

**Grant file format:**
```json
{
  "user": "username",
  "granted_at": "2026-02-05T10:30:00Z",
  "expires_at": "2026-02-06T10:30:00Z",
  "granted_by": "admin_user",
  "reason": "Short-term debugging"
}
```

### rate-limits/
**Purpose:** Rate limiting state for denial logging and other rate-limited operations
**Permissions:** `1777` - World-writable with sticky bit (users can only delete own files)
**Used by:** Docker wrapper, GPU allocation, event logging
**Cleanup:** Auto-cleaned by rate limit logic (24h retention)

### container-states/
**Purpose:** Container lifecycle tracking and metadata
**Permissions:** `700` - Root-only access
**Used by:** Container lifecycle management, idle detection

### container-runtime/
**Purpose:** Runtime container metadata and temporary state
**Permissions:** `700` - Root-only access
**Used by:** Container orchestration, resource tracking

### workload-inventory.json
**Purpose:** Current GPU workload inventory (updated by detector)
**Permissions:** `644` - World-readable
**Updated by:** `ds01-workload-detector.timer` (every 60s)
**Read by:** Monitoring dashboards, allocation decisions

### gpu-queue.json
**Purpose:** GPU allocation queue and reservation state
**Permissions:** `644` - World-readable
**Used by:** GPU queue manager, allocation coordination

## Backup and Persistence

**State files are NOT backed up to git** - they are runtime state only.

**Backup strategy:**
- Log archives: Rotated and compressed in `log-archives/`
- Configuration snapshots: Saved in `backups/` by deploy.sh before changes
- State files: Ephemeral - rebuilt from events and current system state

## Related Documentation

- [config/runtime/resource-limits.yaml](../runtime/resource-limits.yaml) - Configuration that drives state creation
- [scripts/admin/bare-metal-access](../../scripts/admin/bare-metal-access) - Grant management CLI
- [scripts/monitoring/detect-workloads.py](../../scripts/monitoring/detect-workloads.py) - Workload inventory updater
