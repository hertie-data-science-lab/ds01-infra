# Phase 2: Awareness Layer - Context

**Gathered:** 2026-01-30
**Status:** Ready for planning

<domain>
## Phase Boundary

Detect all GPU workloads regardless of how they were created — managed containers, unmanaged containers, and host processes. Build a unified inventory queryable from a single command. Zero blind spots.

Enforcement (blocking, stopping, access restriction, cgroup slice application) belongs to Phase 3/4. Soft enforcement (cgroup slice application to unmanaged containers) was originally scoped for Phase 2 but has been deferred — see research constraint below.

**Deferred from Phase 2:** Cgroup slice application to unmanaged containers. Research (02-RESEARCH.md, Pitfall 2) confirmed that `--cgroup-parent` cannot be changed on running containers via Docker API. Options (systemd transient scopes, container recreation) are fragile and invasive. Slices will be applied via the docker wrapper on next container creation/restart, which is an enforcement concern (Phase 3/4), not an awareness concern.

</domain>

<decisions>
## Implementation Decisions

### Detection behaviour
- Systemd timer running every 30 seconds (not a persistent daemon)
- Scans Docker API for all containers + nvidia-smi + /proc for host GPU processes
- Detects ALL containers (not just GPU ones), flags which have GPU access
- Classifies containers by origin: ds01-managed, docker-compose, devcontainer, raw-docker, unknown
- Persists inventory state to file in /var/lib/ds01/ (survives reboots)
- Emits events to Phase 1 event log for all transitions: new workload detected, workload exited, classification changed
- Non-GPU containers noted in inventory without deep tracking (flags "shadow" workloads)
- Inventory is near-real-time: current state at last scan, max 30s lag from polling interval (acceptable for 60s detection window)

### Inventory & reporting
- New dedicated command: `ds01-workloads` (separate from ds01-events)
- Default output: summary table (Type, User, GPU(s), Status, Age)
- `--wide` flag adds: Container/Process ID, Name/Image, CPU%, Memory usage
- `--by-user` flag groups workloads under user headings
- `--json` flag for scripting and piping to jq
- Filter flags: `--user`, `--type`, `--gpu-only` to narrow results
- Does NOT integrate into dashboard (stays a separate tool)
- Full 4-tier help system: --help, --info, --concepts, --guided

### Unmanaged workload handling
- On discovery: log event AND inject `ds01.detected.*` labels onto the container
- Label namespace: `ds01.detected.*` (e.g., ds01.detected=true, ds01.detected.user=jane, ds01.detected.time=...)
- Clearly separated from ds01-managed labels (no confusion with ds01.* managed labels)
- Best-effort user attribution using available signals (process owner, env vars, docker inspect)
- If user cannot be determined: label as `ds01.detected.user=unknown`
- ~~Soft enforcement: apply DS01 cgroup slices to ALL unmanaged containers (not just GPU ones)~~ **DEFERRED to Phase 3/4** — cgroup-parent cannot be changed on running containers (see 02-RESEARCH.md Pitfall 2). Docker wrapper already applies slices to new containers; enforcement of existing containers requires restart and belongs in enforcement phase.
- Skip already-labelled containers on subsequent scans (no re-processing)

### Host process attribution
- Detection via nvidia-smi (GPU PIDs) + /proc/{pid}/status (owning user)
- Show command line from /proc/{pid}/cmdline (e.g., "python train.py")
- Three separate categories in inventory: DS01-managed, unmanaged containers, host processes
- Host processes persisted to same inventory file as containers (unified state)
- Observe only — no action taken on host GPU processes (Phase 3 handles restriction)
- When a host process exits, remove from inventory (event log has historical record)

### Claude's Discretion
- Transient process handling (processes that appear in one scan and are gone by the next)
- System/infrastructure GPU process handling (DCGM, Xorg, nvidia-persistenced — exclude or tag as system)
- Exact inventory file format and location within /var/lib/ds01/
- Attribution signal priority ordering

</decisions>

<specifics>
## Specific Ideas

- Default table output should feel like `docker ps` — compact, familiar to admins
- `--wide` mirrors `kubectl get pods -o wide` pattern — same data, more columns
- ds01.detected.* namespace keeps detection labels cleanly separate from managed labels
- "Gone is gone" philosophy for host processes — inventory shows current state, event log has history

</specifics>

<deferred>
## Deferred Ideas

- **Cgroup slice application to unmanaged containers** — cannot change cgroup-parent on running containers (research finding). Deferred to Phase 3/4 enforcement phase where container restart/recreation is acceptable.

</deferred>

---

*Phase: 02-awareness-layer*
*Context gathered: 2026-01-30*
*Revised: 2026-01-30 (deferred soft enforcement, clarified near-real-time semantics)*
