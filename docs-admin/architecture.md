# DS01 Infrastructure Architecture

## Overview

DS01 is a multi-user GPU server infrastructure built on Docker containers. It provides:
- Per-user container isolation with resource limits
- GPU allocation (full GPUs and MIG instances)
- Monitoring dashboards
- OPA-based authorization

## Container Ownership Tracking

### Problem

Containers created through various tools (docker-compose, docker run, VS Code devcontainers)
may not have DS01 labels. Without ownership tracking, these containers are invisible to the
dashboard and cannot be attributed to users for resource accounting.

### Solution

A multi-layer ownership detection system:

```
┌─────────────────────────────────────────────────────────────────────┐
│                        Container Ownership                          │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────────────┐    Docker Events    ┌─────────────────────┐  │
│  │  Docker Daemon   │───────────────────>│ container-owner-    │  │
│  │                  │  create/destroy     │ tracker.py          │  │
│  └──────────────────┘                     │ (systemd daemon)    │  │
│                                           └──────────┬──────────┘  │
│                                                      │             │
│                                                      │ writes      │
│                                                      ▼             │
│                                           ┌──────────────────────┐ │
│  ┌──────────────────┐     reads           │ container-owners.json│ │
│  │ sync-container-  │◄────────────────────│ /var/lib/ds01/opa/   │ │
│  │ owners.py        │─────────────────────│                      │ │
│  │ (periodic backup)│     writes          └──────────┬───────────┘ │
│  └──────────────────┘     (preserves)                │             │
│                                                      │ reads       │
│            ┌─────────────────────────────────────────┼─────────┐   │
│            │                       │                 │         │   │
│            ▼                       ▼                 ▼         ▼   │
│    ┌──────────────┐       ┌─────────────┐   ┌───────────┐  ┌────┐ │
│    │  OPA Policy  │       │  Dashboard  │   │ GPU State │  │ .. │ │
│    │  (authz)     │       │  (UI)       │   │ Reader    │  │    │ │
│    └──────────────┘       └─────────────┘   └───────────┘  └────┘ │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

### Owner Detection Strategies

The tracker daemon uses 6 strategies in priority order:

| Priority | Strategy | Source | Reliability |
|----------|----------|--------|-------------|
| 1 | `ds01.user` label | DS01 tools | 100% |
| 2 | `aime.mlc.USER` label | AIME/MLC | 100% |
| 3 | Container name pattern | `name._.uid` | 100% |
| 4 | `devcontainer.local_folder` | VS Code | High |
| 5 | Bind mount paths | `/home/{user}/...` | High* |
| 6 | Compose working_dir | compose labels | Moderate |

*Mount paths are validated by checking actual file ownership to prevent spoofing.

### Key Files

| File | Purpose |
|------|---------|
| `/opt/ds01-infra/scripts/docker/container-owner-tracker.py` | Event-driven ownership daemon |
| `/opt/ds01-infra/scripts/docker/sync-container-owners.py` | Periodic sync (backup/catchup) |
| `/var/lib/ds01/opa/container-owners.json` | Ownership data store |
| `/var/lib/ds01/opa/container-owners.lock` | File lock for concurrent access |

### Data Format

```json
{
  "containers": {
    "abc123def456": {
      "owner": "h.baker@hertie-school.lan",
      "owner_uid": 1722830498,
      "name": "myproject",
      "ds01_managed": false,
      "interface": "compose",
      "created_at": "2025-01-07T10:30:45Z",
      "detection_method": "mount_path"
    }
  },
  "admins": ["datasciencelab"],
  "service_users": ["ds01-dashboard"],
  "updated_at": "2025-01-07T10:30:50Z"
}
```

### Interface Types

- `atomic` - Created via DS01 container-create commands
- `compose` - Created via docker-compose
- `devcontainer` - Created via VS Code devcontainers
- `docker` - Created via direct docker run

### Robustness

| Failure Mode | Mitigation |
|--------------|------------|
| Tracker daemon crashes | Systemd auto-restart (5s) |
| Tracker misses events | sync-container-owners.py periodic catchup |
| Owner detection fails | Container works; marked as "unknown" |
| JSON corruption | Atomic writes (temp+rename), file locking |
| Docker unavailable | Tracker waits and reconnects |

### Operations

**Enable tracker daemon:**
```bash
sudo ln -sf /opt/ds01-infra/config/deploy/systemd/ds01-container-owner-tracker.service \
    /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now ds01-container-owner-tracker
```

**Check status:**
```bash
sudo systemctl status ds01-container-owner-tracker
journalctl -u ds01-container-owner-tracker -f
```

**View ownership data:**
```bash
cat /var/lib/ds01/opa/container-owners.json | jq .
```

---

## GPU Allocation

See `gpu-allocation-implementation.md` for details on GPU/MIG allocation.

## OPA Authorization

Container-level authorization uses OPA policies with ownership data from `container-owners.json`.
See `/opt/ds01-infra/config/deploy/opa/` for policy files.
