# scripts/docker/CLAUDE.md

GPU allocation, container creation, and Docker wrapper internals.

## Key Components

| File | Purpose |
|------|---------|
| `gpu_allocator_v2.py` | Stateless GPU allocation with file locking (5s timeout, fail-open) |
| `mlc-patched.py` | AIME patch adding `--image` flag + DS01 environment validation |
| `mlc-create-wrapper.sh` | Wrapper that applies resource limits before calling mlc |
| `docker-wrapper.sh` | Universal enforcement wrapper at `/usr/local/bin/docker` |
| `get_resource_limits.py` | YAML parser for config/runtime/resource-limits.yaml |
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

## Docker Wrapper (Universal Container Management)

`/usr/local/bin/docker` intercepts all Docker CLI commands.

**Core principle**: GPU access = ephemeral enforcement, No GPU = permanent OK.

**On `docker run` / `docker create`:**
- Injects `--cgroup-parent=ds01-{group}-{user}.slice`
- Adds `--label ds01.user=<username>`
- Adds `--label ds01.managed=true`

**GPU interception** (when `--gpus` detected):
- Detects container type (devcontainer, compose, docker)
- Calls `gpu_allocator_v2.py allocate-external` for GPU allocation
- Rewrites `--gpus all` → `--gpus device=<allocated-uuid>`
- Blocks if no GPU available (3 minute timeout with retry)

**Container type detection** (in docker-wrapper.sh):
1. `devcontainer.*` labels → devcontainer
2. `com.docker.compose.*` labels → compose
3. Fallback → docker

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

## GPU Allocator Commands

```bash
# Check user limits
python3 get_resource_limits.py <username>

# GPU allocation status
python3 gpu_allocator_v2.py status

# Allocate for ds01 container
python3 gpu_allocator_v2.py allocate <username> <container>

# Allocate for external container (devcontainer, compose, docker)
python3 gpu_allocator_v2.py allocate-external <username> <container_type>

# Release GPU
python3 gpu_allocator_v2.py release <username> <container>

# Validate YAML
python3 -c "import yaml; yaml.safe_load(open('../../config/runtime/resource-limits.yaml'))"
```

**allocate-external** uses `container_types` config in resource-limits.yaml for MIG limits:
- `devcontainer`: student=1, researcher=2, faculty=2, admin=unlimited
- `compose`: student=1, researcher=2, faculty=2, admin=unlimited
- `docker`: student=1, researcher=1, faculty=2, admin=unlimited
- `unknown`: student=1, researcher=1, faculty=1, admin=unlimited

## Phase 3.2 Improvements

**Code hardening (Plan 02):**
- Lock timeout: 5-second SIGALRM timeout prevents indefinite hangs on stuck lockfile (fail-open)
- File pre-checks: mlc-patched.py validates DS01 environment (GPU allocator, state dirs) before operations
- Event size enforcement: 4KB limit (PIPE_BUF guarantee) with truncation and fail-open

**Patterns established:**
- Signal-based timeouts for non-blocking file operations
- Pre-flight validation at script entry points with helpful error messages
- Fail-open error handling maintains availability

---

**Parent:** [/CLAUDE.md](../../CLAUDE.md) | **Related:** [README.md](README.md)
