# Project State

## Project Reference

See: .planning/PROJECT.md (updated 2026-01-30)

**Core value:** Full control over GPU resources — every GPU process tracked, attributed to a user, and controllable
**Current focus:** Phase 3.1 (Access Control Completion & Hardening) — merged scope from Phase 3 03-03 + UAT fixes

## Current Position

Phase: 4 (comprehensive-resource-enforcement) — READY TO START
Plan: 0/5 complete
Status: Phase 3.2 complete. Architecture validated (7/7 subsystems pass SLURM/K8s/HPC standards), Critical+High code issues fixed, config consolidated into lifecycle hierarchy. Ready for Phase 4 resource enforcement.
Last activity: 2026-02-05 — Phase 3.2 complete: architecture audit, code refactoring, config consolidation, documentation sync (4 plans, 21 min total)

Progress: [█████████████████░░░] 95% (23/~24 plans complete)
Resume: .planning/phases/03.2-architecture-audit-code-quality/03.2-04-SUMMARY.md

## Performance Metrics

**Velocity:**
- Total plans completed: 23
- Average duration: 3.9 min
- Total execution time: 91.5 min

**By Phase:**

| Phase | Plans | Total | Avg/Plan |
|-------|-------|-------|----------|
| 01-foundation-observability | 6 | 19min | 3.2min |
| 02-awareness-layer | 3 | 13min | 4.3min |
| 02.1-gpu-access-control-research | 2 | 8min | 4.0min |
| 03-access-control | 2 | 10min | 5.0min |
| 03.1-hardening-deployment-fixes | 3 | 6min | 2.0min |
| 03.2-architecture-audit-code-quality | 4 | 21min | 5.25min |
| **Phase 3.2 COMPLETE** | **4/4** | **21min** | **5.25min** |

**Recent Trend:**
- Last 5 plans: 03.2-04 (2min), 03.2-03 (6.5min), 03.2-02 (4min), 03.2-01 (4min), 03.1-03 (2min)
- Trend: Audit/refactor phase complete; documentation updates very fast (2min); consolidation moderate (6.5min)

*Updated after each plan completion*

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

### Blockers/Concerns

**Critical (BLOCKING Phase 4):**
- CVE-2025-23266 (NVIDIA Container Toolkit privilege escalation) — verify nvidia-ctk >= 1.16.2 or apply config.toml workaround (03.2-01 audit finding: MUST verify before Phase 4 deployment, container escape defeats all isolation)

**Monitoring:**
- DCGM exporter systemd service created (01-02) — awaiting deployment to resolve crashes
- jq dependency required for ds01-events query tool — should add to deployment checklist (01-05)

**Dependencies:**
- SMTP credentials from IT needed for Alertmanager email (Phase 1)

**Deferred (Backlog):**
- 6 MEDIUM code quality issues identified (03.2-01) — 3.5 hours total, phased across 3.3 and 4.1

## Session Continuity

Last session: 2026-02-05 15:28 UTC
Stopped at: Phase 3.2 complete (all 4 plans). Architecture validated (7/7 subsystems pass HPC standards), Critical+High code issues fixed, config consolidated, documentation synced. 5 MEDIUM issues deferred to Phase 3.3/4.1 backlog. Ready for Phase 4: Comprehensive Resource Enforcement.
Resume file: .planning/phases/03.2-architecture-audit-code-quality/03.2-04-SUMMARY.md
