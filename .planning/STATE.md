# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-01-30)

**Core value:** Full control over GPU resources — every GPU process tracked, attributed to a user, and controllable
**Current focus:** Phase 8 complete — User Notifications. Phase 9 next.

## Current Position

Phase: 08 (user-notifications) — COMPLETE
Plan: 3/3 complete
Status: Phase 8 complete. Shared notification library (ds01_notify.sh) created, lifecycle scripts refactored with two-level escalation (idle 80%+95%, runtime 75%+90%), resource-alert-checker extended with memory alerts + terminal delivery + 4h cooldown, cron updated to :10 hourly, login greeting shows pending alerts.
Last activity: 2026-02-17 — Completed 08-03-PLAN.md (quota alert terminal delivery)

Progress: [████████████████████] 97% (39/~41 plans complete)
Resume: .planning/phases/08-user-notifications/08-03-SUMMARY.md

## Performance Metrics

**Velocity:**
- Total plans completed: 39
- Average duration: 3.6 min
- Total execution time: 143 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation-observability | 6 | 19min | 3.2min |
| 02-awareness-layer | 3 | 13min | 4.3min |
| 02.1-gpu-access-control-research | 2 | 8min | 4.0min |
| 03-access-control | 2 | 10min | 5.0min |
| 03.1-hardening-deployment-fixes | 3 | 6min | 2.0min |
| 03.2-architecture-audit-code-quality | 4 | 21min | 5.25min |
| 04-comprehensive-resource-enforcement | 5 | 15min | 3.0min |
| 05-lifecycle-bug-fixes | 4 | 11.5min | 2.9min |
| 06-lifecycle-enhancements | 2 | 5min | 2.5min |
| 07-label-standards-migration | 2 | 8min | 4.0min |
| 08-user-notifications | 3 | 10min | 3.3min |

**Recent Trend:**
- Last 5 plans: 08-03 (6min), 08-02 (8min), 08-01 (2min), 07-03 (3min), 07-02 (3min)
- Trend: Phase 8 slightly longer due to multi-file refactors (3.3min avg)
| Phase 08-user-notifications P02 | 480 | 2 tasks | 2 files |
| Phase 08-user-notifications P03 | 360 | 2 tasks | 3 files |

## Accumulated Context

### Decisions

Decisions are logged in PROJECT.md Key Decisions table.
Recent decisions affecting current work:

- Docker wrapper for universal enforcement (not OPA) — intercepts all container creation
- Awareness-first architecture — detect everything before enforcing
- Milestones ordered: control → observability → hygiene → SLURM → cloud
- Use systemd for DCGM restart management (not docker-compose) — prevents restart conflicts and MIG race conditions (01-02)
- Hybrid docker-compose + systemd pattern for infrastructure containers — compose creates, systemd manages restarts (01-02)
- Replaced commitizen with semantic-release for automated versioning — auto-triggers on push to main (01-04)
- Standardised JSON event schema (v1) — timestamp, event_type, source, schema_version with optional user and details (01-01)
- Never-block event logging pattern — returns False on error, never raises exceptions (01-01)
- Bash-via-CLI bridge for event logging — Python CLI as bridge between Bash and Python event emission (01-01)
- Copytruncate for JSONL logrotate — keeps file descriptors valid for append-only logs (01-01)
- jq-based event filtering over grep — structured JSON queries for reliable event analysis (01-05)
- Four-tier help system for admin tools — --help, --info, --concepts, --guided (01-05)
- Best-effort event logging pattern — log_event || true, never blocks critical operations (01-06)
- Safe import fallback for Python logging — try/except with no-op function ensures allocator always works (01-06)
- Transient filtering uses 2-scan threshold to avoid event noise from short-lived processes (02-01)
- System GPU processes (nvidia-persistenced, DCGM, Xorg) excluded from user inventory (02-01)
- Near-real-time inventory semantics: max 30s lag from polling interval (acceptable for 60s detection window) (02-01)
- Container name pattern 'vsc-' classified as devcontainer (VSCode pattern) (02-01)
- Single docker stats call for efficiency in wide mode — batch query not per-container loops (02-03)
- By-user grouping sorts alphabetically with 'unknown' user always last (02-03)
- Age display format: Xd/Xh/Xm/Xs for human readability (02-03)
- Container isolation enforced in Docker wrapper (not OPA) — wrapper-based authorization replacing failed OPA approach (03-02)
- Filter docker ps via --filter label=ds01.user for performance — leverages daemon filtering instead of post-processing (03-02)
- Fail-open for unowned containers prevents blocking legacy workloads — allows with warning log (03-02)
- Rate limiting at 10/hour per user prevents denial log flooding — first denial always logged at warning level (03-02, 03-01)
- Admin bypass: root, datasciencelab, ds01-admin group — system owner has admin privileges (03-02, 03-01)
- Monitoring mode (DS01_ISOLATION_MODE=monitoring) logs denials but allows operations — safe rollout path (03-02)
- Linux video group for bare metal GPU access exemptions — checked by profile.d script, NOT device permissions (03-01, revised in 02.1-02)
- at command for temporary grant scheduling — purpose-built for one-time tasks, simpler than systemd timers (03-01)
- SSH session re-login required for group changes — Linux limitation documented in user messages (03-01)
- Echo piped to wall avoids nested heredoc complexity — cleaner than heredoc-in-heredoc for at command scripts (03-01)
- Profile.d scripts skip non-interactive shells — [[ $- == *i* ]] check prevents breaking system services and cron jobs (02.1-02)
- Profile.d scripts use 'return' not 'exit' — sourced scripts must not close user shell (02.1-02)
- Video group + profile.d exemption is Layer 3 GPU access control — Layer 1 is CUDA_VISIBLE_DEVICES deterrent, Layer 2 is Docker device mapping security boundary (02.1-02)
- Device permissions remain at defaults (0666) — udev rule manipulation is anti-pattern per HPC research, breaks nvidia-smi and monitoring tools (02.1-02)
- Three-layer GPU access control architecture — Layer 1: CUDA_VISIBLE_DEVICES (host deterrent), Layer 2: Docker --gpus device mapping (container security), Layer 3: video group exemption (opt-in bare-metal) (02.1-01, 02.1-02)
- Self-bootstrap re-exec pattern in deploy.sh — deployed copy always re-execs from source, eliminating "run twice" bug (03.1-01)
- Comprehensive deterministic permissions manifest — explicit chmod/chown on every deploy run ensures correct state regardless of umask or git checkout (03.1-01)
- Unified profile.d deployment from dual sources — single loop deploys from both config/deploy/profile.d/ and config/etc-mirrors/profile.d/ with 644 permissions (03.1-01)
- State directory permissions per-policy — bare-metal-grants 711 (traverse without listing), rate-limits 1777 (world-writable with sticky), /var/lib/ds01 775 root:docker (03.1-01)
- Event log group-writable — events.jsonl 664 root:docker enables non-root users in docker group to log events (03.1-01)
- Fail-open exception handling for GPU allocation chain — infrastructure errors return safe defaults/structured errors per OWASP 2025 A10, never block container creation (03.1-02)
- Replace silent exception swallowing with stderr logging — observability without breaking fail-open pattern (03.1-02)
- Restrictive video group sync — deploy.sh adds exempt users AND removes non-exempt users from video group (03.1-03)
- Three-tier exemption check in GPU awareness — grant file → config exempt_users → video group membership (03.1-03)
- Udev rules removed from deployment — device permissions remain at defaults (0666), no manipulation (03.1-03)
- nvidia-* wrappers deployed as UX tools — provide helpful error messages for blocked users, not a security boundary (03.1-03)
- Architecture validation completed: 7/7 subsystems pass against SLURM/K8s/HPC patterns — event logging, workload detection, container isolation, GPU access control, deployment, GPU allocation, config management all evidence-backed (03.2-01)
- Docker authorization plugin evaluated and REJECTED — CVE-2024-41110 bypass vuln in Docker's authz mechanism, OPA plugin is demo-grade (77 commits), already parked in Phase 3 research. Wrapper approach is correct for DS01 (03.2-01, corrected)
- Config consolidation pattern: deploy/runtime/state hierarchy + template-based generation — reduces duplication, single source of truth, environment-specific values filled at deploy time (03.2-01)
- Lifecycle-based config hierarchy implemented — deploy/ (install-time), runtime/ (per-operation), state/ (persistence documentation), eliminates etc-mirrors duplication (03.2-03)
- Generative config pipeline with fill_config_template() — template support (*.template files), envsubst variable substitution, validation for unsubstituted vars (03.2-03)
- Code severity tiers: CRITICAL (security/data loss) → HIGH (reliability) → MEDIUM (maintainability) → LOW (style) — fix Critical+High in-phase, defer rest to backlog (03.2-01)
- CVE-2025-23266 verification BLOCKING for Phase 4 — NVIDIA Container Toolkit < 1.16.2 allows container escape, must upgrade before resource enforcement (03.2-01)
- Lock timeout with fail-open for GPU allocator — 5-second SIGALRM timeout prevents indefinite hangs on stuck lockfile, fail-open maintains availability (03.2-02)
- Pre-flight validation functions at script entry points — mlc-patched.py validates DS01 environment (GPU allocator, state dirs) before any operations (03.2-02)
- YAML validation in deploy.sh — validates resource-limits.yaml syntax before deployment, prevents broken config from reaching production (03.2-02)
- Event size enforcement at 4KB minus overhead — byte-level checking with truncation and fail-open, preserves PIPE_BUF atomic write guarantee (03.2-02)
- Lifecycle-based config hierarchy — organize by lifecycle (deploy/runtime/state) not source/mirror, clear separation of concerns (03.2-03)
- Generative config pipeline with fill_config_template() — template support (*.template files), envsubst variable substitution, validation for unsubstituted vars (03.2-03)
- Docker authorization plugin rejected — CVE-2024-41110 bypass vulnerability, OPA plugin is demo-grade, wrapper approach is correct for DS01 (03.2-01)
- Aggregate limit formula: per-container × max_containers_per_user — prevents single user from consuming unlimited resources across containers (04-01)
- Admin group has no aggregate limits — unlimited resources for system administration, systemd design: absence of limit = no enforcement (04-01)
- Three-tier generator integration — deploy.sh (all users), setup-resource-slices.sh (all users), create-user-slice.sh (single user with --user flag) (04-01)
- Systemd drop-in files for aggregate enforcement — /etc/systemd/system/ds01-{group}-{user}.slice.d/10-resource-limits.conf, survives daemon-reload (04-01)
- Idempotent generator with stale cleanup — skips unchanged drop-ins, removes configs for deleted users (04-01)
- Aggregate quota check runs BEFORE GPU allocation — fail fast on quota issues, don't waste GPU allocation attempts (04-02)
- Requested memory extracted from --memory flag or per-container default — accurate projection of quota usage (04-02)
- Pids soft warning at 90% threshold — alerts user but doesn't block container creation (04-02)
- CPU quota enforced by systemd kernel-level — no pre-check needed, can't predict usage (04-02)
- Cgroup driver verification warns only — doesn't block deployment, other components may still work (04-02)
- GPU quota unified into aggregate framework — gpu_limit in aggregate section, checked before max_mig_instances (04-03)
- Two-layer GPU quota enforcement — Layer 1: aggregate gpu_limit (per-user total), Layer 2: max_mig_instances (per-container) (04-03)
- GPU quota fail-open pattern — if ResourceLimitParser unavailable or aggregate missing, allow allocation with warning (04-03)
- AGGREGATE_GPU_QUOTA_EXCEEDED error format — matches docker-wrapper.sh QUOTA_EXCEEDED pattern for consistent UX (04-03)
- Login quota greeting via profile.d — shows concise memory/GPU/tasks usage at SSH login with colour-coded progress bars (04-04)
- Cgroup direct reads for speed — profile.d scripts read memory.current/pids.current directly to keep login latency <200ms (04-04)
- 16-char progress bars with colour thresholds — green <70%, yellow 70-84%, red 85%+ for visual quota feedback (04-04)
- PSI metrics collected every minute via cron — cpu.pressure and memory.pressure per user slice for responsiveness monitoring (04-05)
- OOM kill counter tracked with JSON state file — detects increases in memory.events oom_kill counter and logs to event system (04-05)
- Best-effort event logging in monitoring — monitoring scripts never block on logging failures (04-05)
- JSONL format for resource stats — append-only time-series logs suitable for jq queries and analysis (04-05)
- GPU utilization as primary idle signal — nvidia-smi query per GPU UUID (<5% threshold), multi-signal logic with CPU/network as secondary (05-01)
- 30-minute startup grace period for idle detection — uses Docker StartedAt timestamp, prevents false positives during data loading and package installation (05-01)
- Dev containers exempt from idle timeout — only subject to max_runtime (168h), rationale: MIG slice usage, bind-mount survival, bursty interactive patterns (05-01)
- Wall notifications for idle warnings — replaces file-based notifications (.ds01-idle-warning, .idle-warning.txt), plain text broadcast to user terminals (05-01)
- 24-hour keep-alive limit — .keep-alive file respected for max 24h then ignored, prevents infinite GPU squatting (05-01)
- 60-second SIGTERM grace for GPU containers — industry standard for model checkpoint saves, increased from 10s (05-01)
- Wall broadcasts for max runtime notifications — replaces file-based notifications ($HOME/.ds01-runtime-warning), instant terminal delivery (05-02)
- SIGTERM grace configurable via policies.sigterm_grace_seconds — default 60s for GPU workload checkpointing, was hardcoded 10s (05-02)
- Universal container cleanup with ownership fallback chain — ds01.user → aime.mlc.USER → devcontainer.local_folder → name pattern → unknown, handles all containers regardless of creation method (05-03)
- Created-state container cleanup at 30m timeout — detects containers in "created" state (never started) from policies.created_container_timeout (05-03)
- Belt-and-suspenders GPU release in cleanup — duplicates cleanup-stale-gpu-allocations logic to prevent leaks if timing window missed (05-03)
- SLURM epilog pattern for GPU health verification — post-removal check detects orphaned processes via nvidia-smi --query-compute-apps, kills them, resets GPU only if not shared (05-04)
- Never reset shared GPUs — GPU reset affects all containers sharing that physical GPU (MIG multi-tenant safety), alert admin for manual intervention (05-04)
- Cron schedule distribution for lifecycle jobs — spread across hour at :05, :20, :35, :50 to prevent resource contention and maintain logical ordering (05-04)
- Per-group lifecycle policies with inheritance — global policies → group policies → user override, enables different thresholds per research group (06-01)
- CPU idle threshold tuned from <1% to 2-5% — reduces false positives during data loading (students 2%, researcher/faculty 3%) (06-01)
- Time-bounded exemptions with Azure Policy pattern — expires_on field with record preservation after expiry for audit trail (06-01)
- Eventual consistency for exemptions — changes take effect at next cron cycle (~1 hour max), simpler than immediate propagation (06-01)
- Multi-signal AND logic for idle detection — GPU idle AND CPU idle AND network idle = idle, prevents false positives during data loading (LIFE-05, 06-02)
- Detection window with consecutive-check tracking — N idle checks required before action, reduces transient dip false positives (LIFE-06, 06-02)
- Exemption-aware lifecycle enforcement — exempt users receive FYI-only warnings, no enforcement, with audit logging (06-02)
- Variable SIGTERM grace by container type — GPU=60s, devcontainer=30s, compose=45s, ensures checkpoint time per workload pattern (LIFE-07, 06-02)
- [Phase 07]: Lowercase label names (ds01.user not ds01.USER) for Docker ecosystem consistency
- [Phase 07]: Single ds01.user label replaces both aime.mlc and aime.mlc.USER (eliminates duplication)
- [Phase 07]: Authoritative label schema as YAML document (machine-readable, version-controlled)
- [Phase 07]: Bash filter scripts need no fallback — Docker daemon's --filter handles OR logic implicitly
- [Phase 07]: Python ownership scripts retain fallback — explicit ds01.user → aime.mlc.USER chain for attribution
- [Phase 07]: Framework label migrated (aime.mlc.DS01_FRAMEWORK → ds01.framework) in generation and consumption
- [Phase 07]: Monitoring scripts filter on ds01.* labels (ds01.user, ds01.managed, ds01.image)
- [Phase 07]: Admin dashboards use ds01.managed=true filter for DS01 container enumeration
- [Phase 07]: Ownership fallback chain with TODO markers (ds01.user → aime.mlc.USER → devcontainer path → process owner)
- [Phase 08-01]: docker exec -e flag for env var passing avoids shell quoting issues in container alert writes
- [Phase 08-01]: Quota summary caches in shell var per run to avoid repeated Python startup overhead per notification
- [Phase 08-user-notifications]: deliver_alert_to_terminal skips container fallback — quota alerts are user-level, no specific container context
- [Phase 08-02]: Idle two-level escalation: first warning at 80%, final at 95% of idle timeout; WARNED_FINAL state added to container state files
- [Phase 08-02]: Runtime two-level escalation: first warning at 75%, final at 90% of runtime limit; hours_until_stop floored at 1h for clean messaging

### Roadmap Evolution

- Phase 2.1 inserted after Phase 2: GPU Access Control Research (URGENT) — Phase 3's device-permission approach (/dev/nvidia* 0660, video group) broke the GPU allocation pipeline because nvidia-smi requires device access even for queries. Three separate patches failed to fully resolve. Research completed (02.1-01), design document approved, plan 03-03 revised (02.1-02). Phase 3 now unblocked with research-aligned three-layer architecture.
- Phase 3.1 inserted after Phase 3: Hardening & Deployment Fixes (URGENT) — Cross-phase UAT audit revealed systemic file permissions (700/600) blocking all non-admin users. 3 blockers + 4 major issues. Covers: deterministic permissions manifest in deploy.sh, GPU allocator bugs (MIG-only checker, .members loading), deploy.sh symlink fix, complete Phase 3 deployment (03-03), event log permissions.

### Pending Todos

- [ ] Deploy DCGM exporter systemd service to `/etc/systemd/system/` and verify 7-day stability (01-02 artefact at `config/deploy/systemd/ds01-dcgm-exporter.service`)
- [ ] Configure Alertmanager SMTP password for `h.baker@hertie-school.org` and send test email notification
- [x] Fix deploy.sh bootstrap problem — first run deploys old copy of itself, needs two runs after changes (self-deploy ordering) — FIXED in 03.1-01
- [ ] Fix deploy.sh pip install — system Python (`/usr/bin/python3`) has no pip; use `python3 -m ensurepip` or specify full path
- [ ] Update `scripts/user/atomic/container-list` to use wrapper — currently calls `/usr/bin/docker` directly, bypassing container isolation (03-02 follow-up)
- [ ] Consolidate `config/deploy/` and `config/etc-mirrors/` into single SSOT — see `.planning/todos/pending/2026-01-31-consolidate-system-config-ssot.md`
- [ ] Investigate wrapper group detection mismatch — mlc-create-wrapper applies student limits to researcher users — see `.planning/todos/pending/2026-01-31-investigate-wrapper-group-detection-mismatch.md`
- [ ] Verify GPU/MIG allocation end-to-end via container deploy — full chain test after availability checker fix — see `.planning/todos/pending/2026-01-31-verify-gpu-mig-allocation-end-to-end.md`
- [x] **URGENT** Fix GPU allocation (full GPU support + permissions + .members loading) — FIXED in 03.1-02 (hardened with fail-open exceptions)
- [ ] Design group management & file permissions system — deterministic enforcement on deploy — see `.planning/todos/pending/2026-02-01-group-and-permissions-management-system.md`
- [ ] Add login greeting/welcome message via profile.d — see `.planning/todos/pending/2026-02-01-login-greeting-message-profile-d.md`
- [x] Finish GPU notice library deployment — .so has 0700 permissions, non-admin users can't load via LD_PRELOAD — FIXED in 03.1-01 (755 permissions)
- [x] Deterministic file permissions manifest in deploy.sh — all touched files' permissions git-tracked and enforced on deploy — COMPLETED in 03.1-01
- [x] Fix 1 CRITICAL + 3 HIGH code issues (03.2-01 audit findings) — lock timeout, file pre-checks, YAML validation, event size limits — COMPLETED in 03.2-02 (4min, 5 atomic commits)
- [x] Consolidate config/ structure to deploy/runtime/state hierarchy with template generation (Plan 03.2-03) — COMPLETED 2026-02-05 (6.5min, 25 files changed)
- [ ] Install and run ShellCheck on critical bash scripts before code refactoring — estimated 30min (03.2-01 recommendation)
- [ ] [MEDIUM] Refactor MIG slot representation (fragile '.' check in gpu_allocator_v2.py line 123) — deferred from Phase 3.2 audit (suggested: Phase 3.3, 30min)
- [ ] [MEDIUM] Add SSH re-login messaging after group changes — scripts/system/add-user-to-docker.sh lacks clear message — deferred from Phase 3.2 audit (suggested: Phase 3.3, 5min)
- [ ] [MEDIUM] Improve profile.d error visibility — profile.d scripts run during login, errors silent — deferred from Phase 3.2 audit (suggested: Phase 3.3, 15min)
- [ ] [MEDIUM] Consolidate event rate limiting — currently only in denial layer, no general event logging rate limit — deferred from Phase 3.2 audit (suggested: Phase 4.1, 1 hour)
- [ ] [MEDIUM] Grant file JSON corruption detection — add validation on read in profile.d script — deferred from Phase 3.2 audit (suggested: Phase 3.3, 20min)
- [ ] Add Teams notification webhook for ds01-hub GitHub repository
- [ ] Add systematic documentation development phase to roadmap (use /gsd:add-phase)
- [ ] Review and configure CI/CD pipelines (lint, release, sync-docs) — currently disabled — see `.planning/todos/pending/2026-02-11-review-cicd-pipelines.md`
- [ ] [DEFERRED] Disk quota enforcement — requires XFS migration (ext4 → XFS) before kernel-level quotas (Phase 4 ENFORCE-04)
- [ ] [DEFERRED] I/O bandwidth enforcement — requires BFQ scheduler switch from mq-deadline (Phase 4 ENFORCE-03)
- [ ] [DEFERRED] Fair-share GPU scheduling — priority based on historical usage, relevant for SLURM integration (Phase 4)
- [ ] [DEFERRED] Network bandwidth limits — not relevant until multi-node or network contention (Phase 4)

### Blockers/Concerns

**Operational (verify before production deployment):**
- CVE-2025-23266 (NVIDIA Container Toolkit privilege escalation) — verify nvidia-ctk >= 1.17.8 or set `features.disable-cuda-compat-lib-hook = true` in config.toml. Container escape via LD_PRELOAD in Dockerfiles. Check with `nvidia-ctk --version`.

**Monitoring:**
- DCGM exporter systemd service created (01-02) — awaiting deployment to resolve crashes
- jq dependency required for ds01-events query tool — should add to deployment checklist (01-05)

**Dependencies:**
- SMTP credentials from IT needed for Alertmanager email (Phase 1)

**Deferred (Backlog):**
- 6 MEDIUM code quality issues identified (03.2-01) — 3.5 hours total, phased across 3.3 and 4.1

## Session Continuity

Last session: 2026-02-17 11:09 UTC
Stopped at: Completed Phase 8 — all 3 plans (user notifications complete)
Resume file: .planning/phases/08-user-notifications/08-03-SUMMARY.md
