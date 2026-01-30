# Architecture

**Analysis Date:** 2026-01-26

## Pattern Overview

**Overall:** Multi-layer command hierarchy with universal Docker wrapper enforcement.

**Key Characteristics:**
- 5-layer abstraction stack (L0 Docker → L4 Wizards)
- Universal enforcement via Docker wrapper at `/usr/local/bin/docker`
- Stateless GPU allocation with file-level locking
- Systemd cgroup-based resource containment
- Ephemeral enforcement for GPU containers, permanent for non-GPU

## Layers

**L0: Docker Foundation**
- Purpose: Base container runtime
- Location: `/usr/bin/docker` (real binary)
- Contains: Native Docker CLI
- Depends on: NVIDIA Container Toolkit
- Used by: Docker wrapper

**L1: AIME ML Containers (Hidden)**
- Purpose: Base image management and container templates
- Location: `/opt/aime-ml-containers`
- Contains: mlc-create, mlc-run, base images
- Depends on: Docker
- Used by: mlc-patched.py

**L2: Docker Wrapper (Universal Enforcement)**
- Purpose: Intercept all `docker run/create` commands, enforce GPU allocation, cgroup injection, labeling
- Location: `/usr/local/bin/docker`
- Contains: Bash wrapper routing to gpu_allocator_v2.py
- Depends on: gpu_allocator_v2.py, get_resource_limits.py, username-utils
- Used by: All user commands, all container creation paths (atomic, orchestrators, wizards, VS Code dev containers, docker-compose, raw docker)

**Key flow:**
1. User runs any docker command (e.g., `docker run`, `docker create`)
2. Wrapper at `/usr/local/bin/docker` intercepts
3. If `--gpus` detected: calls `gpu_allocator_v2.py allocate-external` to find available GPU
4. Rewrites `--gpus all` → `--gpus device=X` (specific device)
5. Injects `--cgroup-parent=ds01-{group}-{user}.slice`
6. Injects labels: `ds01.user`, `ds01.managed`, `ds01.container_type`
7. Passes to real Docker at `/usr/bin/docker`

**L3: Atomic Commands (L2 entry points)**
- Purpose: Single-purpose container/image operations
- Location: `scripts/user/atomic/`
- Contains: `container-create`, `container-start`, `container-run`, `container-stop`, `container-remove`, `container-list`, `container-stats`, `image-create`, `image-list`, etc.
- Depends on: Docker wrapper, lib utilities, resource limits config
- Used by: Orchestrators, direct user invocation

**L4: Orchestrators (L3 coordinators)**
- Purpose: Multi-step workflows composing atomic commands
- Location: `scripts/user/orchestrators/`
- Contains: `container-deploy` (create + run), `container-retire` (stop + remove)
- Depends on: Atomic commands (L2)
- Used by: Wizards, direct user invocation

**L5: Wizards (L4 guided flows)**
- Purpose: Complete guided user onboarding and workflows
- Location: `scripts/user/wizards/`
- Contains: `user-setup`, `project-init`, `project-launch`, `devcontainer-init`
- Depends on: Orchestrators, atomic commands
- Used by: End users, new onboarding

## Data Flow

**Container Creation (Universal):**

```
User command (any source: CLI, VS Code, docker-compose, API)
    ↓
Docker wrapper at /usr/local/bin/docker
    ↓
Is --gpus flag present?
    ├─ YES: gpu_allocator_v2.py allocate-external
    │       ↓
    │       Check user limits (get_resource_limits.py)
    │       ↓
    │       Lock and check /var/lib/ds01/gpu-state.json
    │       ↓
    │       Find available GPU/MIG instance
    │       ↓
    │       Rewrite --gpus all → --gpus device=X
    │
    └─ NO: No GPU restriction
    ↓
Ensure user slice exists (create-user-slice.sh)
    ↓
Inject cgroup-parent=ds01-{group}-{user}.slice
    ↓
Inject labels: ds01.user, ds01.managed, ds01.container_type, ds01.interface
    ↓
Call real /usr/bin/docker
    ↓
Container running with enforced cgroup limits
```

**Container Lifecycle (GPU Containers):**

```
Container creation/start
    ↓
Docker wrapper allocates GPU
    ↓
Record in /var/lib/ds01/gpu-state.json
    ↓
Container running (cgroup limits enforced)
    ├─ IDLE? (check-idle-containers.sh cron :30/hour)
    │   → Stop if idle_timeout exceeded
    │   → Record stop timestamp
    │
    ├─ TOO LONG? (enforce-max-runtime.sh cron :45/hour)
    │   → Stop if max_runtime exceeded
    │
    └─ RUNNING: continue...
    ↓
Container stop (manual or cron)
    ↓
Record stop timestamp in gpu-state.json
    ↓
Hold GPU for gpu_hold_after_stop duration
    ↓
cleanup-stale-gpu-allocations.sh (:15/hour)
    → Release GPU back to pool
    ↓
cleanup-stale-containers.sh (:00/hour)
    → Remove container after container_hold_after_stop
```

**State Management:**

All state is stored in JSON files under `/var/lib/ds01/`:
- `gpu-state.json` - Current GPU allocations: `{physical_gpu: allocated_user_container}`
- `container-metadata/*.json` - Per-container metadata (owner, type, creation time, etc.)
- `/var/log/ds01/events.jsonl` - Append-only event log

GPU allocation is **stateless and race-safe**:
- All decisions made at allocation time by reading current state
- File-level locking (fcntl) prevents race conditions
- No persistent allocation records (enables recovery after restart)

## Key Abstractions

**GPU Allocator (gpu_allocator_v2.py):**
- Purpose: Stateless GPU allocation with user quota enforcement
- Examples: `gpu_allocator_v2.py allocate <user> <container>`, `gpu_allocator_v2.py allocate-external <user> <docker>`, `gpu_allocator_v2.py release <user> <container>`, `gpu_allocator_v2.py mark-stopped <user> <container>`
- Pattern: File-locked state mutations, returns specific GPU/MIG instance or error

**Docker Wrapper (docker-wrapper.sh → docker-filter-proxy.py):**
- Purpose: Universal enforcement point for all container creation
- Examples: `docker run --gpus all`, `docker create --gpus all`, VS Code dev containers, docker-compose
- Pattern: Command-line rewriting, cgroup-parent injection, label injection

**Resource Limits Resolution (get_resource_limits.py):**
- Purpose: Read and merge resource configuration with priority (user_overrides > groups > defaults)
- Examples: `get_resource_limits.py alice` returns merged dict
- Pattern: YAML parsing, group lookup from `config/groups/*.members`, priority resolution

**Container Type Detection:**
- Purpose: Classify containers for lifecycle enforcement (devcontainer vs compose vs docker vs unknown)
- Location: Docker wrapper, check-idle-containers.sh, enforce-max-runtime.sh
- Labels checked: `ds01.container_type`, `ds01.interface`, `devcontainer.*`, `com.docker.compose.*`
- Pattern: Priority-ordered label inspection

**Systemd Slice Hierarchy:**
- Purpose: OS-level resource containment (CPU, memory, I/O)
- Pattern: `ds01-{group}-{user}.slice` automatically created and injected via `--cgroup-parent`
- Hierarchy: `ds01.slice` → `ds01-{group}.slice` → `ds01-{group}-{user}.slice`

## Entry Points

**User-Facing Commands:**

**L5 Wizards (Full onboarding):**
- Location: `scripts/user/wizards/`
- Examples: `user-setup`, `project init`, `project launch`, `devcontainer init`
- Triggers: First-time user onboarding or new project creation
- Responsibilities: Interactive step-by-step guidance, calls orchestrators

**L4 Orchestrators (Recommended layer):**
- Location: `scripts/user/orchestrators/`
- Examples: `container deploy`, `container retire`
- Triggers: Direct user command or wizard
- Responsibilities: Multi-step workflows, calls atomic commands, sets `DS01_CONTEXT=orchestration`

**L3 Atomic Commands (Advanced):**
- Location: `scripts/user/atomic/`
- Examples: `container-create`, `container-start`, `container-run`, `container-stop`, `container-remove`
- Triggers: Direct user invocation or orchestrator
- Responsibilities: Single operation, respects `DS01_CONTEXT` for output suppression

**L2 Dispatchers (Command routing):**
- Location: `scripts/user/dispatchers/`
- Examples: `container-dispatcher.sh`, `project-dispatcher.sh`
- Triggers: Space-separated commands like `container deploy my-project`
- Responsibilities: Parse subcommand, route to atomic/orchestrator

**System Entry Points:**

**Docker Wrapper (Universal enforcement):**
- Location: `/usr/local/bin/docker` (replaces system docker)
- Triggers: Any `docker run` or `docker create` command
- Responsibilities: GPU allocation, cgroup injection, label injection

**Cron Jobs (Lifecycle enforcement):**
- Location: `/etc/cron.d/` (deployed from `scripts/system/deploy-cron-jobs.sh`)
- Jobs:
  - `:30/hour` - `check-idle-containers.sh` (idle timeout)
  - `:45/hour` - `enforce-max-runtime.sh` (max runtime)
  - `:15/hour` - `cleanup-stale-gpu-allocations.sh` (GPU hold)
  - `:00/hour` - `cleanup-stale-containers.sh` (container hold)

**Admin Commands:**

**Dashboard & Monitoring:**
- Location: `scripts/admin/`
- Examples: `dashboard`, `ds01-logs`, `ds01-users`, `mig-configure`, `monitoring-manage`
- Triggers: Admin invocation
- Responsibilities: System visibility and management

## Error Handling

**Strategy:** Early validation with clear user-facing errors.

**Patterns:**
- Atomic commands validate inputs before execution (container name exists, user limits not exceeded, GPU available)
- Docker wrapper returns timeout with retry for GPU allocation (3-minute timeout, 10-second retry)
- Cron jobs log errors to `/var/log/ds01/` but continue (don't halt on single container failure)
- User-friendly error messages via `scripts/lib/error-messages.sh`

## Cross-Cutting Concerns

**Logging:**
- Bash: via `scripts/lib/init.sh` (log_info, log_error, log_warning functions with ANSI colors)
- Python: structured JSON logging to `/var/log/ds01/events.jsonl`
- Cron jobs: append to dedicated logs (`idle-cleanup.log`, `runtime-enforcement.log`, etc.)

**Validation:**
- Resource limits: `get_resource_limits.py` validates YAML and resolves user config
- Usernames: `username-utils.sh` sanitizes for systemd slice names (special chars → hyphens)
- GPU state: `gpu_state_reader.py` validates allocation integrity
- Container metadata: each container must have owner label for cleanup

**Authentication:**
- All commands respect Unix user identity ($(whoami))
- GPU ownership enforced via Docker labels (`ds01.user`)
- Admin access required for system/deployment commands

**Context-Aware Output:**
- Orchestrators set `DS01_CONTEXT=orchestration`
- Atomic commands check this to suppress "Next steps" output when called from orchestrators
- Prevents UI spam in multi-step workflows

---

*Architecture analysis: 2026-01-26*
