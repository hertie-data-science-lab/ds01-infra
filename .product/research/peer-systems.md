# Peer Systems Analysis

How existing GPU management and container orchestration systems handle the same problems DS01 solves. Each system's relevant patterns and what DS01 borrows or rejects.

## SLURM (HPC Standard)

**What it is:** The dominant job scheduler for HPC clusters. Manages compute resources (CPU, GPU, memory) across multi-node environments.

**Relevant patterns:**
- **GPU GRES (Generic Resources):** GPUs declared as `gres/gpu:4` per node. Users request via `--gres=gpu:1`. DS01 equivalent: `max_mig_instances` in resource-limits.yaml.
- **Cgroup enforcement:** SLURM creates cgroups per job, constraining CPU/memory/devices. DS01 equivalent: systemd slices per user (`ds01-{group}-{user}.slice`).
- **Fair-share scheduling:** Historical usage affects priority. DS01 defers this to M4 (SLURM integration).
- **Epilog scripts:** Post-job cleanup verifies GPU health, kills orphans. DS01 equivalent: `cleanup-stale-gpu-allocations.sh` with GPU health verification.
- **Prolog/epilog pattern:** Pre-job validation (quota check) and post-job cleanup. DS01 equivalent: Docker wrapper pre-checks + cron-based cleanup.

**What DS01 borrows:** Cgroup-per-user enforcement, epilog cleanup pattern, GPU-as-resource abstraction.
**What DS01 rejects:** Job queue model (DS01 is interactive-first, not batch-first). SLURM integration planned for M4.

## Kubernetes GPU Operator

**What it is:** NVIDIA's Kubernetes integration for GPU scheduling. Device plugins expose GPUs as schedulable resources.

**Relevant patterns:**
- **Device plugin model:** GPUs exposed as `nvidia.com/gpu: 1` resource requests. Scheduler handles placement. DS01 equivalent: `gpu_allocator_v2.py` allocates specific devices.
- **Resource quotas per namespace:** `ResourceQuota` limits total GPU/CPU/memory per team. DS01 equivalent: aggregate limits per user via systemd slices.
- **MIG support:** `nvidia.com/mig-1g.5gb` as schedulable resource type. DS01 equivalent: MIG tracking as `physical_gpu:instance` notation.
- **Node-level isolation:** Namespace boundaries prevent cross-tenant access. DS01 equivalent: Docker wrapper ownership filtering.
- **Time-sharing (experimental):** Multiple workloads share a GPU with time-slicing. DS01 uses MIG for spatial sharing instead.

**What DS01 borrows:** Per-user resource quotas, MIG-as-resource model, namespace-like isolation.
**What DS01 rejects:** Kubernetes complexity (single-server, no orchestrator needed), device plugin model (wrapper is simpler).

## Run:ai / Rafay / Anyscale

**What they are:** Commercial GPU platforms providing managed GPU orchestration, typically built on Kubernetes.

**Relevant patterns:**
- **GPU fractioning:** Virtualise GPU memory for fine-grained sharing. DS01 uses NVIDIA MIG instead (hardware-level isolation).
- **Quota management:** Per-team GPU budgets with borrowing. DS01 equivalent: per-group limits in resource-limits.yaml.
- **Idle GPU reclamation:** Detect idle workloads and reclaim GPUs. DS01 equivalent: `check-idle-containers.sh` with multi-signal detection.
- **Priority-based preemption:** Higher-priority jobs evict lower-priority ones. DS01 defers this (priority field exists but not enforced).
- **Dashboard and analytics:** Usage visualisation, cost attribution. DS01 equivalent: Grafana dashboards + `ds01-events` query tool.

**What DS01 borrows:** Idle reclamation pattern, quota-per-group model, multi-signal idle detection.
**What DS01 rejects:** GPU virtualisation (MIG provides hardware isolation), preemption (too aggressive for academic setting).

## AIME ML Containers

**What it is:** The base platform DS01 extends. Provides framework-versioned Docker images and container lifecycle tools (`mlc-create`, `mlc-open`, `mlc-stats`).

**Relevant patterns:**
- **Framework image management:** Pre-built images for PyTorch, TensorFlow, MXNet with version tracking.
- **User isolation via naming:** Container naming convention `name._.uid` for ownership.
- **Workspace mounting:** `/home/{user}/workspace` mounted into containers for persistence.
- **Label system:** `aime.mlc.*` labels for container metadata. DS01 migrated to `ds01.*` namespace.

**DS01's relationship:** Minimal patch strategy — 2.2% modification of `mlc.py` (52 lines out of 2,400) to add `--image` flag for custom images. Preserves upgradeability. Three of nine MLC commands wrapped; others used directly or replaced.

## JupyterHub

**What it is:** Multi-user Jupyter notebook server with spawner model for container-based isolation.

**Relevant patterns:**
- **Spawner model:** Per-user containers spawned on demand. DS01 equivalent: container-deploy creates per-user containers.
- **Resource limits per user:** Configurable CPU/memory per spawned container. DS01 equivalent: resource-limits.yaml.
- **Idle culling:** Shut down inactive notebooks after timeout. DS01 equivalent: idle detection + cleanup pipeline.

**Relevance to DS01:** Potential M6 integration target. DS01 could serve as a JupyterHub spawner backend.

## Academic HPC Clusters (Harvard FASRC, Edinburgh CIRRUS)

**What they are:** University-operated GPU clusters sharing similar constraints to DS01 (academic users, shared resources, single admin team).

**Relevant patterns:**
- **Fair-share with decay:** Usage history weighted by recency (recent heavy use lowers priority). DS01 defers to M4.
- **Walltime limits:** Maximum job runtime enforced at submission. DS01 equivalent: `max_runtime` per group.
- **Group-based quotas:** Research groups allocated GPU-hours or GPU-count. DS01 equivalent: four-tier group model (student/researcher/faculty/admin).
- **Scratch directories:** Ephemeral storage for job data, periodically purged. DS01 equivalent: workspace persistence model (containers ephemeral, workspace permanent).
- **MOTD and login banners:** System status communicated at SSH login. DS01 equivalent: `ds01-quota-greeting.sh` profile.d script.

**What DS01 borrows:** Group-based quotas, walltime enforcement, login-time status display.
