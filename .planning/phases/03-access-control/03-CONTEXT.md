# Phase 3: Access Control - Context

**Gathered:** 2026-01-31
**Status:** Ready for planning

<domain>
## Phase Boundary

Users cannot bypass DS01 controls or interfere with each other. Bare metal GPU access restricted, user isolation enforced via Docker wrapper authorisation (not OPA). The Docker wrapper is the universal enforcement point — all containers receive identical treatment regardless of launch method.

</domain>

<decisions>
## Implementation Decisions

### Strict Design Principle: Universal Enforcement
- ALL containers are managed — there is no "unmanaged" category from an enforcement perspective
- Docker wrapper normalises everything: `docker run`, `docker-compose up`, VS Code dev containers all get identical labels, limits, and tracking
- "How it was launched" is not a meaningful distinction for enforcement

### Bare metal restriction
- Users removed from `video` group by default (Linux convention: `video` group controls `/dev/nvidia*` device access)
- Helpful contextual error when non-exempt user runs any `nvidia-*` command — explains GPU access is container-only, suggests `container deploy`
- Wrap all `nvidia-*` commands (nvidia-smi, nvidia-settings, etc.), not just nvidia-smi
- Exemptions configured in `resource-limits.yaml` (consistent with existing config pattern)
- Exempt users still tracked via Phase 2 awareness layer (monitored access)
- Time-limited bare metal grants available: 24h default, admin can override duration
- Grant method: both CLI command and config entry
- Soft revocation on expiry: remove from video group but don't kill existing GPU processes; new processes blocked, existing ones finish
- Wall message notification before and when temporary access expires
- User self-check command: shows own bare metal access status and expiry
- Current state: only `ollama` service account in video group (no human users) — ollama to be removed from server (broken, unused)

### Container isolation
- `docker ps` shows own containers only (filtered by wrapper)
- All Docker commands filtered for container isolation (exec, inspect, logs, stats, stop, rm, etc.)
- "Permission denied: this container belongs to <username>" on cross-user attempts (honest, shows owner)
- Docker images remain shared at wrapper level (read-only artefacts; DS01's own `image-list` already handles per-user display)
- Networks and volumes not isolated at wrapper level (host networking shared; data isolation via filesystem bind mounts)
- Container sharing between users deferred to future phase

### Admin model (two tiers)
- **Full admin bypass:** `datasciencelab` account + admin group members — see all containers, manage any container, bare metal GPU access. Configurable admin group.
- **Bare metal exemption only:** `h.baker` — GPU access on host, but container isolation still applies (not an admin)

### Error messages and UX
- Quota errors reference DS01 commands at highest abstraction level: `container list`, `container retire` (not `container stop`, not `ds01 container ...`)
- Contextual GPU quota message: "GPU quota exceeded (2/2 allocated). Check: container list. Free GPUs: container retire <name>"
- Silent label/limit injection on `docker run` — no extra wrapper output, feels like normal Docker
- Deny events rate-limited in logs (cap per user per hour to prevent flooding)

### Docker wrapper enforcement
- Wrapper expands interception beyond current run/create/stop/rm/kill/ps to cover all container-targeting commands
- `docker run`/`docker-compose up` allowed but wrapper auto-injects: DS01 labels, cgroup slice, resource limits, GPU allocation checks

### Claude's Discretion
- Fail-open vs fail-closed default for unknown Docker subcommands (recommendation: fail-open)
- Wrapper crash behaviour (recommendation: fail-open with logging)
- Debug mode implementation (recommendation: DS01_WRAPPER_DEBUG=1 env var)
- Kill switch for maintenance (recommendation: config toggle + logging while disabled)
- Container ownership detection method for containers without DS01 labels
- Network, volume, and build command handling at wrapper level
- Allowlist vs blocklist approach for wrapper command filtering

### Transition & rollout
- Immediate deployment (no gradual rollout — no human users currently affected)
- Dry run: manual testing during implementation, then switch to live enforcement. Silent (log-only, not visible to users)
- MOTD updated with note about access controls + permanent contextual denial message on every blocked command
- New containers only at deployment — existing running containers untouched initially
- Deployment via `deploy.sh` (no formal checklist)

</decisions>

<specifics>
## Specific Ideas

- Video group Linux convention should be documented in admin READMEs — not DS01-specific, it's how all Linux GPU systems work
- Remove ollama from server entirely (broken service, unused) — separate maintenance task before Phase 3 deployment

</specifics>

<deferred>
## Deferred Ideas

- Container sharing between users (voluntary access grants) — future phase
- Network isolation between user containers — future phase if needed
- Ollama containerisation — moot (removing from server)

</deferred>

---

*Phase: 03-access-control*
*Context gathered: 2026-01-31*
