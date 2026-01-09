# scripts/docker/CLAUDE.md

GPU allocation, container creation, and Docker wrapper internals.

## Key Components

| File | Purpose |
|------|---------|
| `gpu_allocator_v2.py` | Stateless GPU allocation with file locking (race-safe) |
| `mlc-patched.py` | AIME patch adding `--image` flag for custom images |
| `mlc-create-wrapper.sh` | Wrapper that applies resource limits before calling mlc |
| `docker-wrapper.sh` | Universal enforcement wrapper at `/usr/local/bin/docker` |
| `get_resource_limits.py` | YAML parser for resource-limits.yaml |
| `container-owner-tracker.py` | Real-time container ownership tracking daemon |
| `event-logger.py` | Append-only JSON event log |

## GPU Allocation Flow

### Container Creation
```
container-create → mlc-create-wrapper.sh
    → get_resource_limits.py (read user limits)
    → gpu_allocator.py allocate (check limits, find GPU)
    → mlc-patched.py --image (create container)
    → Container launched with --gpus device=X
```

### Container Stop
```
container-stop → mlc-stop
    → gpu_allocator.py mark-stopped (record timestamp)
    → GPU held for gpu_hold_after_stop duration
```

### Automatic Cleanup (Cron)
| Job | Schedule | Action |
|-----|----------|--------|
| `enforce-max-runtime.sh` | :45/hour | Stop containers exceeding max_runtime |
| `check-idle-containers.sh` | :30/hour | Stop containers idle beyond idle_timeout |
| `cleanup-stale-gpu-allocations.sh` | :15/hour | Release GPUs after gpu_hold_after_stop |
| `cleanup-stale-containers.sh` | :00/hour | Remove containers after container_hold_after_stop |

## Docker Wrapper

`/usr/local/bin/docker` intercepts all Docker commands:

**On `docker run` / `docker create`:**
- Injects `--cgroup-parent=ds01-{group}-{user}.slice`
- Adds `--label ds01.user=<username>`
- Adds `--label ds01.managed=true`

**Ownership detection:**
1. `ds01.user` label
2. `aime.mlc.USER` label
3. `devcontainer.local_folder` label (extracts from path)

## mlc-patched.py

Minimal 2.5% modification to AIME's mlc-create:
- Adds `--image` flag to bypass AIME catalog
- Validates local image existence
- Adds DS01 labels (`DS01_MANAGED`, `CUSTOM_IMAGE`)
- 97.5% of AIME logic preserved

## State Files

| Path | Purpose |
|------|---------|
| `/var/lib/ds01/gpu-state.json` | Current GPU allocations |
| `/var/lib/ds01/container-metadata/` | Per-container metadata |
| `/var/lib/ds01/opa/container-owners.json` | Container ownership for OPA |
| `/var/log/ds01/events.jsonl` | Centralised event log |
| `/var/log/ds01/gpu-allocations.log` | GPU allocation history |

## MIG Support

- Tracked as `"physical_gpu:instance"` (e.g., `"0:0"`, `"0:1"`)
- Auto-detected via `nvidia-smi mig -lgi`
- Profile configured in `config/resource-limits.yaml` → `gpu_allocation.mig_profile`

## Testing

```bash
# Check user limits
python3 get_resource_limits.py <username>

# GPU allocation status
python3 gpu_allocator.py status

# Validate YAML
python3 -c "import yaml; yaml.safe_load(open('../../config/resource-limits.yaml'))"
```

---

**Parent:** [/CLAUDE.md](../../CLAUDE.md) | **Related:** [README.md](README.md)
