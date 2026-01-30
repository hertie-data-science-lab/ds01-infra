# Pitfalls Research: GPU Container Management Platform

**Domain:** Multi-tenant GPU cluster management with Docker
**Researched:** 2026-01-30
**Confidence:** HIGH

This research focuses on critical mistakes when adding resource enforcement, user isolation, process detection, and operational automation to a production GPU container management system.

---

## Critical Pitfalls

### Pitfall 1: Enforcement Bypass via Cgroup Manipulation

**What goes wrong:**
Users can escape resource limits by specifying `--cgroup-parent` when launching containers, placing them outside the intended systemd slice hierarchy. This completely bypasses CPU, memory, and GPU limits.

**Why it happens:**
Docker daemon settings can define a default `--cgroup-parent`, but users can override it at container runtime. The Docker daemon doesn't reject these overrides by default. This is compounded by the "single-writer rule" violation - when both systemd and user-specified cgroups try to manage the same container, systemd loses enforcement capability.

**Consequences:**
- Resource limits unenforced (user with 8GB limit can consume 64GB)
- GPU allocation tracking breaks (container not in ds01.slice hierarchy)
- Monitoring blind spots (Prometheus cgroup metrics miss these containers)
- Cross-user interference (unlimited container steals resources from compliant users)
- Accountability loss (process attribution fails without cgroup labelling)

**Prevention:**
1. **Docker authorization plugin** to reject `--cgroup-parent` overrides (OPA alternative needed since yours failed)
2. **Wrapper script validation** - Docker wrapper must reject or override cgroup-parent flags before exec
3. **Detection monitoring** - Alert when containers appear outside ds01.slice hierarchy
4. **User education** - Document that cgroup-parent overrides are blocked and why

**Warning signs:**
- Containers running but not appearing in `systemctl status ds01.slice` output
- GPU processes attributed to users but no matching container in ds01 hierarchy
- Resource consumption exceeding configured slice limits
- Prometheus cgroup metrics showing gaps vs actual container count

**Phase to address:**
Milestone 1, Phase 1 (Foundation) - Must fix before building user isolation or detection on top

**Sources:**
- [Force containers to use cgroup-parent defined by Docker Daemon](https://github.com/moby/moby/issues/23262)
- [systemd Control Group APIs and Delegation](https://systemd.io/CGROUP_DELEGATION/)
- [Default cgroup usage confirmation](https://docs.datadoghq.com/security/default_rules/cis-docker-1.2.0-2.9/)

---

### Pitfall 2: The OPA Fail-Open Trap

**What goes wrong:**
Docker authorization plugins (like OPA) fail open by default. If the plugin crashes, becomes unreachable, or has no policy loaded, Docker authorises ALL requests. Users gain unrestricted access during outages.

**Why it happens:**
Docker daemon cannot distinguish between "plugin explicitly allows this" and "plugin is broken, fail open for availability". The OPA Docker authorization plugin specifically fails open when installed without a Rego policy file reference. Plugin restarts after daemon restarts can also cause the plugin to be "not found" even if previously working.

**Consequences:**
- Silent security degradation (no alerts when enforcement stops)
- Time-window attacks (users discover plugin is down, launch privileged containers)
- False confidence (thinking OPA is protecting when it's actually offline)
- Difficult debugging (no clear signal that plugin failed vs legitimately allowed)

**Prevention:**
1. **Monitor plugin health** - Systemd service monitoring for OPA plugin process
2. **Test fail modes** - Kill plugin during testing, verify Docker rejects rather than allows
3. **Default-deny policy** - Even minimal policy must deny by default, allow explicitly
4. **Daemon validation** - Docker daemon should refuse to start if required authorization plugin is missing
5. **Alternative approach** - Your Docker wrapper approach is actually safer than OPA for this reason

**Warning signs:**
- Plugin process not running (`ps aux | grep opa-docker-authz` returns nothing)
- Docker logs show "plugin not found" or "authorization plugin failed"
- Sudden increase in container launches without corresponding policy evaluation logs
- Containers launched with flags that should be blocked (--privileged, --cgroup-parent)

**Phase to address:**
Milestone 1, Phase 2 (User Isolation) - If reconsidering OPA alternative, test fail modes first

**Sources:**
- [OPA Docker Authorization - Fail-Open Behaviour](https://www.openpolicyagent.org/docs/docker-authorization)
- [Unable to locate plugin after restarting daemon](https://github.com/open-policy-agent/opa-docker-authz/issues/46)
- [OPA Docker Tutorial not working](https://github.com/open-policy-agent/opa/issues/880)

---

### Pitfall 3: NVIDIA Container Toolkit Privilege Escalation (CVE-2025-23266)

**What goes wrong:**
A three-line Dockerfile can escape container isolation and gain root access to the host by exploiting the NVIDIA Container Toolkit's mishandling of LD_PRELOAD. Attackers set LD_PRELOAD in their Dockerfile to load a malicious library when nvidia-ctk hook executes, achieving container escape.

**Why it happens:**
The toolkit's OCI hook "createContainer" trusts the container's LD_PRELOAD environment variable. The hook runs with elevated privileges on the host, and loading attacker-controlled libraries from the container image creates a direct privilege escalation path.

**Consequences:**
- **CRITICAL for multi-tenant GPU systems** - One malicious user compromises entire server
- Cross-tenant data theft (access other users' containers, volumes, data)
- Model stealing (proprietary ML models from other researchers)
- Persistent backdoors (attacker gains root, installs persistence mechanisms)
- Regulatory compliance violations (data breach in academic environment)

**Prevention:**
1. **Immediate patching** - Upgrade to NVIDIA Container Toolkit >= 1.17.8 (you're likely vulnerable)
2. **Workaround if can't patch** - Disable cuda-compat hook: edit `/etc/nvidia-container-toolkit/config.toml`, set `features.disable-cuda-compat-lib-hook = true`
3. **Container image scanning** - Scan user Dockerfiles for LD_PRELOAD before allowing builds
4. **User Dockerfile review** - For teaching lab, consider requiring instructor approval for custom Dockerfiles
5. **AppArmor/SELinux** - These do NOT protect against this CVE (it bypasses them)

**Warning signs:**
- User Dockerfiles containing `ENV LD_PRELOAD=/path/to/lib.so`
- Unexplained processes running as root outside containers
- Files appearing in /root or /home directories the container shouldn't access
- Sudden privilege escalation events in audit logs

**Phase to address:**
**IMMEDIATE** - Check version now: `nvidia-ctk --version`. If < 1.17.8, patch before Milestone 1 starts.

**Sources:**
- [NVIDIAScape - NVIDIA AI Vulnerability (CVE-2025-23266)](https://www.wiz.io/blog/nvidia-ai-vulnerability-cve-2025-23266-nvidiascape)
- [Critical NVIDIA Container Toolkit Flaw](https://thehackernews.com/2025/07/critical-nvidia-container-toolkit-flaw.html)
- [NVIDIA Security Bulletin - July 2025](https://nvidia.custhelp.com/app/answers/detail/a_id/5659)

---

### Pitfall 4: Container Lifecycle Cleanup Race Conditions

**What goes wrong:**
Containers escape retirement due to race conditions between lifecycle scripts and user actions. Specifically: idle timeout triggers container-stop, but container restarts before cleanup script runs; container in "Created" state stuck indefinitely; cleanup script fails with "no such container" despite container still existing in Docker's view.

**Why it happens:**
Docker's container lifecycle has subtle state transitions. Containers can be in "Created" state without being "Running" - they exist but aren't executing. Cleanup scripts that check only "running" status miss these. Signal propagation delays (SIGTERM → wait → SIGKILL) create windows where containers restart. Multiple cleanup actors (cron job, systemd timer, manual script) can conflict.

**Consequences:**
- **GPU allocation leaks** - Retired containers still hold GPU assignments
- **Disk space exhaustion** - Stopped containers accumulate, filling /var/lib/docker
- **Stale monitoring data** - Prometheus scrapes dead containers, pollutes dashboards
- **User confusion** - "I stopped that container, why is it still using GPU?"
- **Label pollution** - Zombie containers with ds01.* labels break allocation logic

**Prevention:**
1. **Atomic state transitions** - Use Docker labels to track retirement state before stopping
2. **Comprehensive state filtering** - Cleanup must check ALL states: created, running, paused, exited, dead
3. **Idempotent cleanup** - Script must handle "container already gone" gracefully
4. **Transaction log** - Record intended action before executing (aids debugging)
5. **Post-cleanup validation** - After cleanup, verify GPU allocation state matches Docker ps
6. **Single cleanup coordinator** - One systemd timer, not multiple overlapping cron jobs

**Warning signs:**
- `docker ps -a | wc -l` growing unbounded over weeks
- GPU allocator showing assigned GPUs but no running containers
- Containers in "Created" state for > 5 minutes (`docker ps -a --filter status=created`)
- Cleanup logs showing "Error: No such container" repeatedly

**Phase to address:**
Milestone 1, Phase 1 (Foundation) - Fix before adding more lifecycle automation

**Sources:**
- [Docker Container Lifecycle Management Best Practices](https://daily.dev/blog/docker-container-lifecycle-management-best-practices)
- [Cleanup: failed to delete container from containerd](https://github.com/docker/for-linux/issues/1148)
- [Docker Container Won't Delete? Fix It Fast](https://atmosly.com/knowledge/fixing-the-docker-container-wont-delete-problem-all-solutions-explained)

---

### Pitfall 5: Process Detection Without Context Creates False Positives

**What goes wrong:**
Detecting unmanaged GPU processes is straightforward (`nvidia-smi`), but attributing them correctly and deciding what to do is hard. False positives flood alerts: Jupyter kernel using GPU but no container detected (actually running inside container, nvidia-smi shows host view); short-lived processes from container init scripts; DCGM exporter itself using GPU for metrics collection; driver processes (nvidia-persistenced, nvidia-fabricmanager).

**Why it happens:**
nvidia-smi shows processes from host perspective - doesn't know about container namespaces. Process attribution requires /proc parsing to map PID → container → user. Container runtime changes pid namespace, making simple PID matching unreliable. Ephemeral workloads (containers < 30 seconds) appear/disappear between detection runs.

**Consequences:**
- **Alert fatigue** - Admin ignores legitimate alerts due to false positive flood
- **User frustration** - Legitimate workflows flagged as "unmanaged", breaking research
- **Enforcement paralysis** - Can't auto-kill processes if unsure they're actually violations
- **Incomplete attribution** - Some processes genuinely unattributable (which user ran this?)

**Prevention:**
1. **Multi-step correlation** - nvidia-smi PID → /proc/PID/cgroup → systemd slice → container ID → ds01 labels → user
2. **Whitelist infrastructure** - Exclude DCGM exporter, nvidia-persistenced, DS01 exporter PIDs
3. **Grace period** - Don't alert on processes existing < 60 seconds (handles init scripts)
4. **Context enrichment** - Log full process context: cmdline, parent PID, cgroup, user, container (if any)
5. **Manual verification before automation** - Run detection in logging-only mode for 2 weeks, review patterns
6. **Clear alert messages** - "GPU process PID 12345 by user alice not in DS01 container" not "Unmanaged process detected"

**Warning signs:**
- Alert volume > 10/day (suggests false positives)
- Same processes appearing repeatedly in alerts (needs whitelisting)
- Alerts for processes that exist < 5 seconds (detection too aggressive)
- Unable to reproduce alert manually (timing/race condition)

**Phase to address:**
Milestone 1, Phase 3 (Process Detection) - Build conservative, refine over time

**Sources:**
- [Process monitoring: How you can detect malicious behavior in containers](https://www.tigera.io/blog/process-monitoring-how-you-can-detect-malicious-behavior-in-your-containers/)
- [Container Runtime Security](https://www.paloaltonetworks.com/cyberpedia/runtime-security)
- [Detect Container Escape Vulnerabilities with Osquery](https://www.uptycs.com/blog/container-escape-vulnerability-detection)

---

### Pitfall 6: Backward Compatibility Breaks During Gradual Rollout

**What goes wrong:**
Adding enforcement to a production system requires gradual rollout - but changes to the Docker wrapper, GPU allocator, or resource limits can break existing containers mid-rollout. Example: New wrapper adds mandatory label, old containers lack it, allocation logic crashes; GPU allocator changes assignment algorithm, existing containers lose GPU access on restart; Resource limit enforcement activates, kills containers exceeding limits that were previously allowed.

**Why it happens:**
Production systems have existing state (running containers, cached images, user workflows). Gradual rollout means old and new behaviour coexist. Database schema equivalent: new code assumes schema V2, but old containers created with schema V1. Insufficient testing with real production data (test with fresh containers, miss edge cases).

**Consequences:**
- **Active research disrupted** - Student's training job killed mid-run due to new enforcement
- **User trust erosion** - "DS01 used to work, now it's broken"
- **Emergency rollbacks** - Admin scrambling to revert changes at 2am
- **Data loss** - Containers killed before users save results

**Prevention:**
1. **Feature flags** - Environment variable controls new behaviour: `DS01_ENFORCE_GPU_LIMITS=false` during rollout
2. **Graceful degradation** - New code handles missing labels/old format containers
3. **Canary users** - Test with 1-2 volunteer power users for 1 week before general rollout
4. **Migration window** - Announce "containers created before DATE will be retired on FUTURE-DATE"
5. **Backward-compatible labels** - New wrapper adds new labels, keeps old labels during transition
6. **Dry-run mode** - Log what WOULD happen without enforcing (see alert patterns before going live)
7. **Instant rollback plan** - Git tag before deployment, documented revert procedure

**Warning signs:**
- User reports increase after deployment ("containers not starting")
- Containers created before deployment date failing on restart
- Error logs mentioning missing labels, unexpected formats
- Spike in GPU allocation errors coinciding with deployment

**Phase to address:**
ALL PHASES - Every enforcement change needs backward compatibility strategy

**Sources:**
- [Managing API Changes: 8 Strategies That Reduce Disruption](https://www.theneo.io/blog/managing-api-changes-strategies)
- [Challenges in a Rolling Update with Database Changes](https://medium.com/@anshulsharma1011/%EF%B8%8Fchallenges-in-a-rolling-update-with-database-changes-98200148fac6)
- [Rolling Deployments: Pros, Cons, And 4 Critical Best Practices](https://octopus.com/devops/software-deployments/rolling-deployment/)

---

### Pitfall 7: Alert Fatigue from Poorly Tuned Monitoring

**What goes wrong:**
New monitoring generates hundreds of alerts per day. Most are false positives or low-priority noise. Admin learns to ignore alerts. When real problem occurs (GPU hardware failure, container escape, user quota exceeded), alert drowns in noise and goes unnoticed for hours.

**Why it happens:**
Default Prometheus alert thresholds too sensitive (trigger on 1-second spike vs sustained problem). Short evaluation windows (5-second check triggers on transient blips). Lack of alert prioritisation (container idle = same severity as GPU hardware failure). No recovery thresholds (alert fires when over limit, fires again when under, creates flapping). Missing context in alert messages ("High GPU usage" - which user? which container? for how long?).

**Consequences:**
- **Critical alerts missed** - Real problems lost in noise
- **Admin burnout** - Checking alerts becomes dread, not vigilance
- **Erosion of monitoring value** - "Just turn off alerts, they're useless"
- **Delayed incident response** - 6 hours to notice GPU failure that alerted immediately

**Prevention:**
1. **Longer evaluation windows** - Alert if condition true for 5 minutes, not 5 seconds
2. **Recovery thresholds** - Require return to normal for 2 minutes before clearing alert
3. **Severity levels** - Critical (page admin), Warning (email), Info (dashboard only)
4. **Context-rich alerts** - "User alice container xenial-gpu-3 idle >6 hours (limit: 4h), auto-retire in 30min"
5. **Baseline first** - Run monitoring for 2 weeks in observation mode, identify normal patterns
6. **Alert tuning sprints** - Weekly review: which alerts fired? Were they actionable? Adjust thresholds
7. **Start conservative** - Better to miss edge cases initially than flood with false positives

**Warning signs:**
- Alert volume > 20/day initially (suggests over-tuning)
- Same alert firing repeatedly (recovery threshold needed)
- Alerts for "problems" that resolve in < 60 seconds (evaluation window too short)
- Admin stops checking alert channel (fatigue has set in)

**Phase to address:**
Milestone 2, Phase 1 (Monitoring Foundation) - Get this right before adding more alerts

**Sources:**
- [Alert Fatigue: What It Is and How to Prevent It](https://www.datadoghq.com/blog/best-practices-to-prevent-alert-fatigue/)
- [Preventing Alert Fatigue in Cybersecurity](https://www.splunk.com/en_us/blog/learn/alert-fatigue.html)
- [5 Ways to Avoid Alert Fatigue in Network Monitoring](https://www.logicmonitor.com/blog/network-monitoring-avoid-alert-fatigue)

---

### Pitfall 8: Automation Scripts Without Safeguards Cause Data Loss

**What goes wrong:**
Cleanup automation intended to remove idle containers accidentally deletes active containers with unsaved work. Example: User's training job checkpointing to /tmp in container, cleanup script removes container before checkpoint saved to volume; Script uses `docker rm -f` without checking if user is actively SSH'd into container; Departed user cleanup deletes home directory of similarly-named current user (alice-2025 vs alice-2026); Disk cleanup removes Docker images still in use, breaking container restarts.

**Why it happens:**
Scripts operate at machine speed - errors affect many resources before human can intervene. Insufficient validation (script checks "idle" but not "has unsaved data"). Lack of dry-run testing with production data. No "undo" mechanism (rm is permanent). Edge cases not considered (what if username contains special chars? what if two containers have same name?).

**Consequences:**
- **Unrecoverable data loss** - Student loses 3 days of training results
- **Broken trust** - Users stop trusting platform, move to cloud
- **Emergency recovery** - Admin frantically trying to restore from backups
- **Scope creep** - One wrong filter deletes 30 containers instead of 3

**Prevention:**
1. **Mandatory dry-run** - Script must run with `--dry-run` first, show what WOULD be deleted, require confirmation
2. **Incremental scope** - Delete 1 item, verify, delete next (not all at once)
3. **User notification** - Email user 24h before deletion: "Container X will be deleted DATE unless you respond"
4. **Active session detection** - Never delete containers with active shell sessions (check `docker exec` sessions)
5. **Checkpoint validation** - For training jobs, verify checkpoint saved to persistent volume before deleting
6. **Backup before bulk operations** - `docker export` containers before cleanup, keep for 7 days
7. **Audit logging** - Record WHO ran script, WHAT was deleted, WHEN, WHY (idle timeout vs manual)
8. **Escape hatches** - User can mark container `ds01.protect=true` to exempt from auto-cleanup

**Warning signs:**
- User reports data loss after cleanup runs
- Script output shows "Deleted 47 containers" when expecting 3-5
- Errors about missing images after cleanup
- Users preemptively moving data out of platform before cleanup runs

**Phase to address:**
Milestone 3, Phase 2 (Cleanup Automation) - Build conservative, expand cautiously

**Sources:**
- [AI data loss: Automation errors and how to prevent them](https://rewind.com/blog/ai-data-loss/)
- [Docker Cleanup: How to Remove Images, Containers & Volumes](https://middleware.io/blog/docker-cleanup/)
- [Keeping the whale happy: How to clean up after Docker](https://tutorials.releaseworksacademy.com/learn/keeping-the-whale-happy-how-to-clean-up-after-docker)

---

## Technical Debt Patterns

Shortcuts that seem reasonable but create long-term problems.

| Shortcut | Immediate Benefit | Long-term Cost | When Acceptable |
|----------|-------------------|----------------|-----------------|
| Skip label migration, just add new labels alongside old | No breaking changes, fast deployment | Two label systems forever, all code checks both, confusion | Never - Creates permanent complexity |
| Disable enforcement for "trusted" users to avoid breaking workflows | Power users happy, faster rollout | Security boundary erodes, creates precedent, impossible to re-enable | Only during 2-week transition period with expiry date |
| Poll nvidia-smi every 5 seconds for process detection | Simple to implement, immediate visibility | 17,280 executions/day, scales poorly, stresses nvml library | MVP only - Replace with eBPF/event-driven in 6 months |
| Store GPU allocation state only in Docker labels | No additional state store needed, simpler | Container deletion loses allocation history, race conditions | Acceptable with reconciliation loop every 60s |
| Hard-code user whitelist in scripts instead of YAML config | Quick fix for testing | Must edit code to add users, no audit trail, version control noise | Only in testing/dev, never in production |
| Use `sleep 60` loops instead of systemd timers | Works immediately, no service config needed | Fragile (dies on script error), no logging, hard to monitor | Never - Invest 30min in proper timer |
| Skip dry-run mode to save development time | Ships feature faster | First mistake causes data loss, no user confidence | Never - Dry-run is non-negotiable for destructive ops |

---

## Integration Gotchas

Common mistakes when connecting to external services.

| Integration | Common Mistake | Correct Approach |
|-------------|----------------|------------------|
| Prometheus/Grafana | Scrape every container individually (30-200 endpoints) | Single exporter aggregates all container metrics, Prometheus scrapes exporter |
| DCGM Exporter | Assume it's reliable, don't monitor the monitor | DCGM crashes frequently - monitor exporter health, auto-restart via systemd |
| Systemd Cgroups | Create ad-hoc cgroups outside systemd's control | Always use systemd-run or .slice files, never raw cgcreate |
| NVIDIA Container Toolkit | Trust default hook configuration | Review /etc/nvidia-container-toolkit/config.toml, disable unused hooks |
| Docker API | Call Docker API directly from parallel scripts | Use locking or serial execution - Docker API has race conditions |
| User home directories | Assume /home/$USER exists and is owned by $USER | Check with `getent passwd $USER`, handle missing home, wrong ownership |
| LDAP/AD queries | Query on every operation | Cache results for 5 minutes, handle LDAP unavailability gracefully |

---

## Performance Traps

Patterns that work at small scale but fail as usage grows.

| Trap | Symptoms | Prevention | When It Breaks |
|------|----------|------------|----------------|
| Linear scan of all containers for status checks | `container-stats` takes 5 seconds | Cache container list, update on Docker events | > 50 containers |
| Individual `docker inspect` calls in loop | Dashboard load takes 30 seconds | Single `docker ps --format json` parses all at once | > 30 containers |
| Polling nvidia-smi every second | High CPU usage, nvml library errors | Use 30-second interval, or event-driven via DCGM | Continuous polling |
| Storing metrics in text files, grep to query | Slow queries, file locking issues | Use Prometheus TSDB for time-series data | > 7 days of metrics |
| No pagination in user-facing commands | `container-list` outputs 500 lines | Add `--limit` and `--offset` flags, default to 20 | > 100 containers |
| Synchronous cleanup in user commands | `container-deploy` hangs waiting for cleanup | Background cleanup task, command returns immediately | Cleanup > 5 seconds |
| Full filesystem scan on every query | Finding user containers takes 10 seconds | Maintain index of user→containers in memory | > 50 users |

---

## Security Mistakes

Domain-specific security issues beyond general web security.

| Mistake | Risk | Prevention |
|---------|------|------------|
| Allowing `--privileged` flag | Complete host compromise, kernel module loading | Docker wrapper rejects --privileged unconditionally |
| Not validating user-provided image names | Pull malicious images: `malicious.com/bitcoin-miner:latest` | Whitelist allowed registries (Docker Hub, internal), reject others |
| Shared /tmp between host and containers | Cross-user data leakage via temp files | Each container gets isolated /tmp, never bind mount host /tmp |
| Running containers as root by default | Container escape = root on host | Force `--user $(id -u):$(id -g)` in wrapper, reject root |
| Unrestricted network access from containers | Containers attack internal university network | Default to bridge network, explicit allow for internet access |
| GPU memory not cleared between users | User B sees user A's training data in GPU RAM | Trust NVIDIA driver to clear, but consider MIG reset between users |
| No rate limiting on container creation | User launches 1000 containers, exhausts resources | Limit to 5 active containers per user, 10 total per user |
| Trusting container labels for security decisions | User sets `ds01.owner=admin`, gains privileges | Labels informational only, get ground truth from getent/LDAP |

---

## UX Pitfalls

Common user experience mistakes in this domain.

| Pitfall | User Impact | Better Approach |
|---------|-------------|-----------------|
| Silently killing containers that exceed limits | "My container disappeared, I lost 8 hours of work" | Notify 30min before: "Container exceeds memory limit, will retire at HH:MM" |
| Cryptic error messages: "GPU allocation failed" | User doesn't know what to do next | "No GPUs available. 4/4 GPUs in use. Try: container-list --all or wait 30min" |
| Requiring manual cleanup of stopped containers | Disk fills with zombie containers, user blamed | Auto-cleanup stopped containers after 7 days, notify user on day 6 |
| No visibility into queue position | "How long until I get a GPU?" - no answer | Show queue: "Position 3/7, estimated wait 45min based on avg job time" |
| Retiring containers during active SSH session | User typing command, container vanishes mid-keystroke | Extend timeout while active shell session exists |
| No self-service quota visibility | User guesses at remaining quota, exceeds, blocked | Dashboard shows: GPU-hours used: 45/100 this month, 55 remaining |
| Alerting admin but not user about their container issues | User doesn't know container is idle, admin becomes messenger | Alert user directly via email/Teams, CC admin for visibility |

---

## "Looks Done But Isn't" Checklist

Things that appear complete but are missing critical pieces.

- [ ] **Process detection:** Often missing attribution to actual user (PID → container → user chain incomplete)
- [ ] **Cleanup automation:** Often missing dry-run mode and user notification before deletion
- [ ] **GPU allocation tracking:** Often missing reconciliation loop (state drift between allocator and reality)
- [ ] **User isolation:** Often missing enforcement (detection works, blocking doesn't)
- [ ] **Resource limits:** Often missing grace period (limits enforced immediately vs warning first)
- [ ] **Monitoring dashboards:** Often missing alert definitions (pretty graphs, no actionable alerts)
- [ ] **Lifecycle management:** Often missing handling of edge states (created, paused, dead, not just running)
- [ ] **Label migration:** Often missing transition plan (adds new labels, forgets to remove old)
- [ ] **Backward compatibility:** Often missing feature flags (change is all-or-nothing, no gradual rollout)
- [ ] **Error messages:** Often missing next steps (tells user what failed, not what to do)

---

## Recovery Strategies

When pitfalls occur despite prevention, how to recover.

| Pitfall | Recovery Cost | Recovery Steps |
|---------|---------------|----------------|
| Enforcement bypass via cgroup-parent | LOW | 1. Identify containers outside ds01.slice 2. Docker stop them 3. User re-launches properly |
| OPA plugin fail-open | MEDIUM | 1. Audit all containers created during outage 2. Validate compliance 3. Retire violations 4. User re-launches |
| CVE-2025-23266 exploitation | HIGH | 1. Isolate server from network 2. Audit all containers for LD_PRELOAD 3. Full security audit 4. Re-image server if compromised |
| Lifecycle cleanup race condition | LOW | 1. Manual `docker ps -a --filter status=created` 2. Remove stuck containers 3. Re-run allocation reconciliation |
| False positive process detection | LOW | 1. Add PID to whitelist 2. Update detection logic 3. Clear alert |
| Backward compatibility break | MEDIUM | 1. Revert deployment 2. Add feature flag 3. Test with canary users 4. Re-deploy with flag=false initially |
| Alert fatigue | MEDIUM | 1. Disable noisy alerts temporarily 2. Tune thresholds based on 2-week baseline 3. Re-enable conservatively |
| Automation data loss | HIGH | 1. Restore from backup 2. Audit script logic 3. Add dry-run requirement 4. Notify affected users |

---

## Pitfall-to-Phase Mapping

How roadmap phases should address these pitfalls.

| Pitfall | Prevention Phase | Verification |
|---------|------------------|--------------|
| Enforcement bypass via cgroup-parent | M1 Foundation | No containers exist outside ds01.slice hierarchy |
| OPA fail-open trap | M1 User Isolation | Plugin crash test: Docker rejects container creation |
| CVE-2025-23266 | **IMMEDIATE** | `nvidia-ctk --version` >= 1.17.8 |
| Lifecycle cleanup race conditions | M1 Foundation | Zero containers in "created" state > 5min |
| Process detection false positives | M1 Process Detection | Alert volume < 5/day, 90% true positive rate |
| Backward compatibility breaks | ALL PHASES | Canary user testing before general rollout, feature flags present |
| Alert fatigue | M2 Monitoring Foundation | Alert volume < 10/day, admin responds to all within 4h |
| Automation data loss | M3 Cleanup Automation | Dry-run mandatory, user notification 24h before deletion |

---

## Context-Specific Warnings for DS01

Pitfalls particularly relevant to your constraints.

### Single Admin + Learning Linux

**Risk:** Complex solutions become unmaintainable when admin is sick/on holiday.

**Mitigation:**
- Favour systemd timers over custom daemons (systemd is documented, your daemon isn't)
- Use established Linux patterns (logrotate, tmpfiles.d) over inventing new mechanisms
- Document "break glass" procedures: how to disable enforcement if something goes wrong
- Prefer simple scripts that log everything over clever code that's opaque

### Production System with Active Users

**Risk:** Testing in production because there's no staging environment.

**Mitigation:**
- Feature flags for all enforcement changes
- Canary users (2-3 volunteers) before general rollout
- Rollout schedule announced 1 week in advance
- Office hours during rollout (don't deploy Friday 5pm)
- Instant rollback documented and tested

### Failed OPA Attempt

**Risk:** Trying another authorization plugin hits same issues.

**Mitigation:**
- Your Docker wrapper approach is actually good - leaning into it is smart
- If need finer-grained control, extend wrapper rather than add plugin
- Test fail modes: what if wrapper script is missing? (Docker daemon won't start)
- Version wrapper script, deploy with same care as code changes

### Three Bypass Paths (dev containers, raw docker, host processes)

**Risk:** Fixing one bypass, others remain, allocation model still broken.

**Mitigation:**
- Milestone 1 must address ALL THREE, not piecemeal (incomplete fix = no fix)
- Detection before enforcement (see the problem before auto-killing)
- User education concurrent with enforcement (users need to understand why)
- Migration path for existing workflows (how does dev container user comply?)

### Container Escape Bug

**Risk:** Rushing to add more lifecycle automation before fixing existing bug.

**Mitigation:**
- Fix existing bug FIRST (Phase 1 Foundation), new automation builds on fixed base
- Root cause the race condition (what exact sequence triggers it?)
- Add regression test (script that tries to trigger race, verify it's fixed)
- Don't paper over bug with more frequent cleanup (fixes symptom, not cause)

---

## Sources

**Critical Vulnerabilities:**
- [NVIDIAScape - NVIDIA AI Vulnerability (CVE-2025-23266)](https://www.wiz.io/blog/nvidia-ai-vulnerability-cve-2025-23266-nvidiascape)
- [Critical NVIDIA Container Toolkit Flaw Allows Privilege Escalation](https://thehackernews.com/2025/07/critical-nvidia-container-toolkit-flaw.html)
- [NVIDIA Security Bulletin - July 2025](https://nvidia.custhelp.com/app/answers/detail/a_id/5659)
- [CVE-2022-0492 - Linux Kernel Cgroups Privilege Escalation](https://unit42.paloaltonetworks.com/cve-2022-0492-cgroups/)

**Docker & Container Security:**
- [Force containers to use cgroup-parent defined by Docker Daemon](https://github.com/moby/moby/issues/23262)
- [Docker release_agent cgroups escape](https://book.hacktricks.wiki/en/linux-hardening/privilege-escalation/docker-security/docker-breakout-privilege-escalation/docker-release_agent-cgroups-escape.html)
- [Default cgroup usage confirmation](https://docs.datadoghq.com/security/default_rules/cis-docker-1.2.0-2.9/)

**Systemd & Cgroups:**
- [systemd Control Group APIs and Delegation](https://systemd.io/CGROUP_DELEGATION/)
- [Configuring resource management using cgroups-v2 and systemd](https://docs.redhat.com/en/documentation/red_hat_enterprise_linux/8/html/managing_monitoring_and_updating_the_kernel/assembly_configuring-resource-management-using-systemd_managing-monitoring-and-updating-the-kernel)
- [Managing resources with cgroups in systemd](https://opensource.com/article/20/10/cgroups)

**OPA & Authorization:**
- [OPA Docker Authorization Plugin](https://www.openpolicyagent.org/docs/docker-authorization)
- [Unable to locate plugin after restarting daemon](https://github.com/open-policy-agent/opa-docker-authz/issues/46)
- [OPA Docker Tutorial not working](https://github.com/open-policy-agent/opa/issues/880)

**Container Lifecycle:**
- [Docker Container Lifecycle Management Best Practices](https://daily.dev/blog/docker-container-lifecycle-management-best-practices)
- [Cleanup: failed to delete container from containerd](https://github.com/docker/for-linux/issues/1148)
- [Docker Container Won't Delete? Fix It Fast](https://atmosly.com/knowledge/fixing-the-docker-container-wont-delete-problem-all-solutions-explained)

**Process Detection & Runtime Security:**
- [What is Container Escape: Detection & Prevention](https://www.wiz.io/academy/container-security/container-escape)
- [Process monitoring: How you can detect malicious behavior in containers](https://www.tigera.io/blog/process-monitoring-how-you-can-detect-malicious-behavior-in-your-containers/)
- [Detect Container Escape Vulnerabilities with Osquery](https://www.uptycs.com/blog/container-escape-vulnerability-detection)
- [eBPF-Guard: container escape detection via multi-level monitoring](https://link.springer.com/article/10.1007/s10664-025-10784-1)

**Monitoring & Alerts:**
- [Alert Fatigue: What It Is and How to Prevent It](https://www.datadoghq.com/blog/best-practices-to-prevent-alert-fatigue/)
- [Preventing Alert Fatigue in Cybersecurity](https://www.splunk.com/en_us/blog/learn/alert-fatigue.html)
- [5 Ways to Avoid Alert Fatigue in Network Monitoring](https://www.logicmonitor.com/blog/network-monitoring-avoid-alert-fatigue)

**Deployment & Backward Compatibility:**
- [Managing API Changes: 8 Strategies That Reduce Disruption](https://www.theneo.io/blog/managing-api-changes-strategies)
- [Challenges in a Rolling Update with Database Changes](https://medium.com/@anshulsharma1011/%EF%B8%8Fchallenges-in-a-rolling-update-with-database-changes-98200148fac6)
- [Rolling Deployments: Pros, Cons, And 4 Critical Best Practices](https://octopus.com/devops/software-deployments/rolling-deployment/)

**Data Loss Prevention:**
- [AI data loss: Automation errors and how to prevent them](https://rewind.com/blog/ai-data-loss/)
- [Docker Cleanup: How to Remove Images, Containers & Volumes](https://middleware.io/blog/docker-cleanup/)

**GPU Cluster Management:**
- [Making GPU Clusters More Efficient with NVIDIA Monitoring Tools](https://developer.nvidia.com/blog/making-gpu-clusters-more-efficient-with-nvidia-data-center-monitoring)
- [Cloud GPU Mistakes to Avoid](https://www.runpod.io/articles/guides/cloud-gpu-mistakes-to-avoid)
- [Revisiting Reliability in Large-Scale ML Research Clusters](https://arxiv.org/html/2410.21680v2)

---

*Pitfalls research for: DS01 GPU Container Management Platform*
*Researched: 2026-01-30*
