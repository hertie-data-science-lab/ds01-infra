# Phase 4: Comprehensive Resource Enforcement - Context

**Gathered:** 2026-02-05
**Status:** Ready for planning

<domain>
## Phase Boundary

Enforce per-user aggregate resource limits (CPU, memory, GPU) via systemd cgroup v2 user slices. Keep existing per-container limits as a second layer. Show quota usage at login. Unify GPU quota enforcement into the same resource framework. Disk quotas and I/O enforcement are explicitly deferred (infrastructure prerequisites not met).

</domain>

<decisions>
## Implementation Decisions

### Enforcement scope
- **Resources enforced:** CPU, memory, GPU quotas, pids (process limits)
- **Resources deferred:** Disk quotas (requires XFS migration), I/O bandwidth (NVMe contention unlikely, needs BFQ scheduler)
- Phase 4 = CPU + memory + GPU + pids enforcement
- All enforcement via systemd cgroup v2 user slices

### Enforcement model — two-layer stacking
- **Per-user aggregate limits** via systemd user slices (new) — caps total usage across ALL of a user's containers
- **Per-container limits** (existing) — kept as-is, prevents single container hogging user's share
- Industry standard (SLURM GrpTRES + per-job, Kubernetes namespace quotas + pod limits)

### Per-user aggregate values
- Formula: per-container limit × max_containers_per_user
- Student: 32 CPUs × 3 = 96 CPUs, 32GB × 3 = 96GB
- Researcher: 48 CPUs × 5 = 240 CPUs, 64GB × 5 = 320GB
- Faculty: 64 CPUs × 5 = 320 CPUs, 128GB × 5 = 640GB
- Admin: unlimited (no aggregate cap)

### Memory enforcement — soft + hard limits
- MemoryHigh set at 90% of quota (throttles, gives warning time)
- MemoryMax set at 100% of quota (OOM kills runaway processes)
- Two-tier approach reduces surprise container kills

### Group tier model
- Keep existing 4-tier model (student/researcher/faculty/admin) unchanged
- Per-container limits stay as-is in resource-limits.yaml
- New per-user aggregate limits added as separate config section

### GPU quota integration
- Refactor GPU limits into the unified resource enforcement framework
- Current max_mig_instances / max_mig_per_container logic moves into cohesive resource-limits enforcement layer
- GPU quotas enforced at same level as CPU/memory (not a separate system)

### Rollout strategy
- Enforce immediately with generous limits (no monitoring-only period)
- Limits are generous enough (sum of max containers) that legitimate workloads won't hit them
- Clear error messages when limits reached

### User experience on limit hit
- Container creation blocked with clear message showing current usage vs limit
- OOM events: Claude's discretion on notification strategy (event log + next-login message likely)
- Quota check: existing check-limits command already available
- Login greeting: show quota summary at SSH login via profile.d

### Quota management
- Admin-only quota changes (no self-service)
- Users contact admin to request higher limits
- Admin edits resource-limits.yaml, reruns deploy

### Claude's Discretion
- OOM notification mechanism (event log only vs next-login message)
- Exact systemd drop-in file generation approach
- Login quota display format and detail level
- How to handle Docker cgroup driver verification (fail-fast vs auto-configure)
- PSI monitoring collection interval and alert thresholds

</decisions>

<specifics>
## Specific Ideas

- "Let's create a cohesive logic — should be a consistent whole" regarding GPU quota integration with the wider resource enforcement framework
- Existing check-limits command already exists for quota checking; extend rather than replace
- Login greeting should show quota summary (similar to the research mockup showing usage bars)

</specifics>

<deferred>
## Deferred Ideas

### Disk quotas (infrastructure prerequisite)
- Server uses ext4 on single 3.5TB NVMe — XFS project quotas require XFS filesystem
- Migration to XFS requires reformatting the storage partition
- **TODO for roadmap:** Add infrastructure prerequisite phase for XFS migration before disk quota enforcement
- Alternative: ext4 user/group quotas (less capable, no per-container project quotas)
- Alternative: Software-based tracking via periodic du scans (no kernel enforcement)

### I/O bandwidth enforcement
- NVMe uses mq-deadline scheduler; io.weight requires BFQ
- NVMe bandwidth unlikely to be a bottleneck with ~10 users
- **TODO for roadmap:** Revisit if I/O contention emerges as actual problem
- Switching to BFQ may reduce NVMe throughput

### Fair-share scheduling
- Priority-based GPU allocation using historical usage (SLURM-style)
- Deferred to Phase 5+ per research recommendations

### Network bandwidth limits
- Not relevant for single-server setup
- Would matter if distributed training across servers added later

</deferred>

---

*Phase: 04-comprehensive-resource-enforcement*
*Context gathered: 2026-02-05*
