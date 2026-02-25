# Docker Wrapper

The universal enforcement point that intercepts all Docker CLI commands. Located at `/usr/local/bin/docker`, taking PATH precedence over `/usr/bin/docker`.

## Interception Points

| Command | Wrapper Action |
|---------|---------------|
| `docker run` / `docker create` | GPU allocation, label injection, cgroup assignment, quota check |
| `docker ps` | Filter by `ds01.user` label (show only caller's containers) |
| `docker stop` / `docker rm` / `docker exec` | Verify caller owns target container |
| `docker inspect` | Pass through (read-only, no restriction) |
| All other commands | Pass through to real Docker binary |

## Container Creation Flow

When the wrapper intercepts `docker run` or `docker create`:

1. **Identify caller:** Determine username from `$USER` or process owner.
2. **Read resource limits:** Call `get_resource_limits.py` for caller's group/user limits.
3. **Check aggregate quota:** Read cgroup `memory.current`, count GPU allocations. Reject if over quota.
4. **GPU allocation (if --gpus present):**
   - Call `gpu_allocator_v2.py allocate-external`
   - Rewrite `--gpus all` → `--gpus device=<specific-uuid>`
5. **Inject labels:** `--label ds01.user=<user>`, `--label ds01.managed=true`, interface type, GPU metadata.
6. **Inject cgroup parent:** `--cgroup-parent=ds01-{group}-{user}.slice`
7. **Inject resource limits:** `--cpus`, `--memory`, `--memory-swap`, `--shm-size`, `--pids-limit`
8. **Call real Docker:** Execute `/usr/bin/docker` with modified arguments.

## Isolation Modes

| Mode | Behaviour | Use Case |
|------|-----------|----------|
| `enforced` (default) | Deny cross-user operations, filter `docker ps` | Production |
| `monitoring` | Log denials but allow all operations | Safe rollout, debugging |
| `disabled` | No ownership checks | Development |

Set via `DS01_ISOLATION_MODE` environment variable.

## Admin Bypass

The following identities bypass all isolation checks:
- `root` user
- `datasciencelab` user (system owner)
- Members of `ds01-admin` group

## Rate-Limited Denial Logging

Cross-user operation denials are logged at max 10 per hour per user. First denial always logged at warning level. Prevents log flooding from repeated attempts.

## Emergency Bypass

`DS01_WRAPPER_BYPASS=1` skips all wrapper logic entirely — the command passes directly to `/usr/bin/docker`. For emergency recovery when wrapper has a bug.

## Key Implementation Details

- **Signal timeout:** 5-second SIGALRM prevents hangs in GPU allocation or config reads.
- **Fail-open:** If any infrastructure component fails (config read, cgroup check, allocator), the wrapper logs a warning and allows the operation.
- **Container type detection:** Wrapper detects devcontainer, compose, and docker interfaces via Docker labels and applies type-specific policies.

## File Reference

- Wrapper: `scripts/docker/docker-wrapper.sh` (~1,300 lines)
- Deployed to: `/usr/local/bin/docker` (symlink or copy via `deploy.sh`)
- Real Docker: `/usr/bin/docker` (always accessible for wrapper internals)
