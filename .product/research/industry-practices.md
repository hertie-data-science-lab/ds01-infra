# Industry Practices

Established patterns in GPU resource management, container orchestration, and multi-tenant compute that inform DS01's design.

## GPU Resource Management in Multi-Tenant Environments

**Spatial vs temporal sharing:**
- **Spatial (MIG):** Hardware-level GPU partitioning. Each tenant gets a dedicated slice with isolated memory and compute. DS01 uses this as its primary GPU sharing mechanism.
- **Temporal (time-sharing):** Workloads take turns on the full GPU. Higher utilisation but no isolation. DS01 rejects this for production use (MIG provides stronger guarantees).
- **MPS (Multi-Process Service):** CUDA-level multiplexing. Better utilisation than MIG but weaker isolation and fault propagation risk. DS01 rejects MPS in favour of MIG.

**Quota models:**
- **GPU-count quotas:** Simple, coarse (user gets N GPUs). DS01 uses this: `max_mig_instances` per user.
- **GPU-hours budgets:** Finer-grained, enables fair-share. DS01 defers to M2/M4.
- **Priority tiers:** Different user classes get different quotas and preemption rights. DS01 implements this via four-tier group model.

**Idle detection patterns:**
- **Single-signal (GPU utilisation only):** Simple but false positives during data loading.
- **Multi-signal (GPU + CPU + network):** Reduces false positives. DS01 uses this with AND logic and consecutive-check windows.
- **User heartbeat:** Application-level keepalive. DS01 supports `.keep-alive` file with 24-hour expiry.

## Container Orchestration for Shared Compute

**Enforcement points:**
- **Admission control (pre-creation):** Validate resource requests before container starts. DS01: Docker wrapper checks quotas before `docker create`.
- **Runtime enforcement (cgroup):** Kernel enforces limits continuously. DS01: systemd slices with CPU/memory/pids limits.
- **Lifecycle enforcement (cron):** Periodic checks for idle/overtime containers. DS01: four cron jobs at :00/:15/:30/:45.

**Container creation interception patterns:**
- **API proxy:** Intercept Docker/K8s API calls. Complex, version-dependent.
- **Admission webhook (K8s):** Server-side validation. K8s-specific.
- **CLI wrapper:** Intercept CLI commands via PATH precedence. DS01 uses this — simple, universal, fail-open capable.
- **Auth plugin:** Docker authorization plugin. DS01 rejected this due to CVE-2024-41110.

**State management approaches:**
- **Database-backed:** PostgreSQL/etcd for allocation state. Reliable but adds dependency.
- **File-backed:** JSON/YAML files with file locking. DS01 uses this for simplicity.
- **Label-backed:** Container labels as source of truth. DS01 uses Docker labels as primary state, file as cache.
- **Stateless (query-on-demand):** Read state from Docker daemon each time. DS01's `gpu-state-reader.py` follows this pattern.

## Multi-Tenancy Isolation Patterns

**Isolation mechanisms (weakest to strongest):**
1. **Namespace filtering:** Show only user's resources. DS01: Docker wrapper filters `docker ps` by `ds01.user` label.
2. **Linux namespaces:** PID, network, mount isolation. Docker provides this by default.
3. **Cgroup enforcement:** Resource limits per user/group. DS01: systemd slices.
4. **Device access control:** GPU device visibility. DS01: three-layer GPU access (CUDA_VISIBLE_DEVICES → Docker device mapping → video group).
5. **VM isolation:** Full hypervisor separation. Not needed for DS01's threat model.

**Ownership detection in shared environments:**
- **Explicit labels:** Creator tags resources. DS01: `ds01.user` label.
- **Name conventions:** Ownership encoded in resource names. DS01: `name._.uid` pattern.
- **Mount path analysis:** Infer owner from bind-mounted paths. DS01: `/home/{user}/` path matching.
- **Process genealogy:** Track parent-child process relationships. DS01: fallback for host process detection.

## Lifecycle Management

**Idle detection → warning → enforcement pipeline:**
1. **Detection:** Periodic polling of resource utilisation metrics.
2. **Grace period:** Warning notification before enforcement action.
3. **Enforcement:** Stop/evict the workload.
4. **Cleanup:** Release resources (GPU, memory), remove container.
5. **Audit:** Log the lifecycle event for compliance.

DS01 implements all five stages with configurable thresholds per group.

**Two-level escalation (industry standard):**
- First warning at 75-80% of threshold.
- Final warning at 90-95% of threshold.
- Enforcement at 100%.
- DS01: idle warnings at 80% and 95%; runtime warnings at 75% and 90%.

## Configuration Management

**Single source of truth (SSOT):**
- One authoritative configuration file per domain. DS01: `resource-limits.yaml` for all resource limits.
- Override hierarchy: defaults → group → user. DS01 implements this exactly.
- Immediate effect: changes apply without restart. DS01: runtime config read per operation.

**Lifecycle-based configuration:**
- **Install-time (deploy):** System files deployed to /etc/. DS01: `config/deploy/`.
- **Runtime (operational):** Read per operation, hot-reloadable. DS01: `config/runtime/`.
- **State (persistent):** Runtime data in /var/lib/. DS01: `config/state/` documents `/var/lib/ds01/`.

**Template-based deployment:**
- Configuration templates with variable substitution. DS01: `*.template` files processed by `fill_config_template()` in `deploy.sh`.
- Validation before deployment (syntax check). DS01: YAML validation in deploy pipeline.
- Deterministic permissions. DS01: `permissions-manifest.sh` enforced on every deploy.
