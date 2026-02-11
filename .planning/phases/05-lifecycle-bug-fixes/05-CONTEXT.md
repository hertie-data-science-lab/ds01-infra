# Phase 5: Lifecycle Bug Fixes - Context

**Gathered:** 2026-02-11
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix container retirement, cleanup, and GPU release so they work reliably across all container types (DS01-managed, devcontainers, compose, direct docker run, unmanaged). Idle timeout enforced, max runtime enforced, created-but-never-started containers cleaned up, GPU allocations released without leaks. The system must work for both full GPUs and MIG slices (dynamic partitioning).

</domain>

<decisions>
## Implementation Decisions

### Idle detection criteria
- **GPU utilisation is the primary idle signal** — add DCGM/nvidia-smi GPU util check (<5% threshold) as the main detection signal
- CPU utilisation, network I/O, and process count remain as **secondary signals** — if CPU/network are active, container is NOT idle even if GPU is quiet (protects data loading, preprocessing)
- **30-minute initial grace period** after container start — no idle detection during startup phase (covers data loading, package installation, model download)
- Sampling frequency and rolling window approach: Claude's discretion based on existing monitoring infrastructure (DCGM exporter already running)
- **Core principle unchanged:** "GPU access = ephemeral enforcement, No GPU = permanent OK" — only containers with GPU access are subject to idle detection

### Dev container lifecycle
- **Dev containers exempt from idle timeout** — only subject to max_runtime (currently 168h / 1 week)
- Rationale: dev containers use MIG slices (less scarce than full GPUs), bind-mount project directories (data survives removal), and are interactive workspaces with bursty usage patterns
- Industry standard: GitHub Codespaces 30 min, JupyterHub 60-120 min — but DS01 dev containers have lower resource pressure due to MIG slices
- Dev container data preservation: project files survive via bind mount, container-internal state (packages, tools) lost on removal — this is standard devcontainer workflow

### Keep-alive mechanism
- **Keep existing .keep-alive file mechanism with 24-hour time limit** — user creates `/workspace/.keep-alive` to prevent idle stop, but respected for max 24h before re-evaluation
- Prevents infinite GPU squatting while giving users explicit control

### Cleanup behaviour
- **SIGTERM grace period: 60 seconds** (up from 10s) — allows model checkpoint saves for GPU workloads. Industry recommendation for GPU containers.
- **Immediate removal after idle stop** — no post-stop hold period for idle-stopped containers. GPU freed instantly. User data survives via bind mounts.
- **GPU hold after manual stop: keep 15 min** — user who manually stops a container may want to restart soon
- **Created-but-never-started containers: clean up after 30 minutes**
- **Wall messages only for warnings** — use `wall` to notify user terminal sessions. No file creation inside containers or user home directories (no .idle-warning.txt, no ~/.ds01-idle-warning). Cleaner, less intrusive.
- High-demand mode: keep current approach (halve idle timeouts when GPU allocation >80%)

### GPU leak resolution
- **Post-removal GPU health verification** — after container removal, check nvidia-smi for orphaned processes on the freed GPU. Kill orphaned processes if found (SLURM epilog pattern).
- **Auto-reset GPU if safe** — run `nvidia-smi -r` if orphaned processes detected AND no other containers using that GPU. If GPU is shared (MIG), alert admin instead.
- Reconciliation frequency: Claude's discretion based on overall cleanup timing architecture
- Stateless allocation design (Docker labels as truth) is correct — no changes needed to core allocation model

### Unlabelled container handling
- **Attempt attribution via heuristics**, then apply standard rules — ownership fallback chain: ds01.user label → aime.mlc.USER label → devcontainer.local_folder path → container name pattern → /proc PID owner
- **Unattributable containers: label as `ds01.user=unknown`** — gets strictest lifecycle rules (shortest idle timeout). Easy to query and audit.
- **No retroactive labelling of pre-wrapper containers** — too complex for minimal benefit. Old containers phase out naturally. New containers always get labels via wrapper.
- **Infrastructure containers (ds01.monitoring=true): fully exempt** from all lifecycle enforcement. Never idle-checked, never stopped, never removed.

### Claude's Discretion
- GPU utilisation sampling frequency and rolling window approach
- Stale allocation reconciliation interval (currently 15 min)
- Exact idle detection algorithm combining GPU + CPU + network signals
- Cron schedule adjustments for the cleanup pipeline
- Implementation approach for wall message delivery

</decisions>

<specifics>
## Specific Ideas

- GPU/MIG dynamic partitioning: system must work for both full GPUs and MIG slices — user changes partitioning dynamically. All lifecycle scripts must be sensitive to this. (Note: systemic MIG/GPU accounting redesign is deferred, but lifecycle scripts must handle both.)
- SLURM epilog pattern for GPU health verification — check for orphaned processes, kill if found, reset GPU if safe
- Industry reference: University of Virginia HPC terminates after 5 hours zero GPU util; K8s CNCF plugin uses <5-10% threshold over configurable window
- DCGM exporter already running — leverage existing metrics infrastructure for GPU utilisation checks

</specifics>

<deferred>
## Deferred Ideas

- **MIG vs GPU accounting systemic redesign** — fragile '.' check in gpu_allocator_v2.py, full GPU = 4 MIG-equivalents hardcoded. Affects entire allocation pipeline, not just lifecycle. Already in deferred backlog (MEDIUM-01).
- **Enhanced notification channels** (email, Slack/Teams) — Phase 8: User Notifications covers this
- **Checkpoint/restore (CRIU) for GPU containers** — Kubernetes working group is developing this (Jan 2026). Future capability, not Phase 5.

</deferred>

---

*Phase: 05-lifecycle-bug-fixes*
*Context gathered: 2026-02-11*
