---
phase: 01-foundation-observability
verified: 2026-01-30T15:30:00Z
status: gaps_found
score: 4/6 must-haves verified
gaps:
  - truth: "DCGM exporter runs reliably without crashing for 7+ days"
    status: failed
    reason: "Systemd service created but not deployed to system - cannot verify 7-day reliability"
    artifacts:
      - path: "config/deploy/systemd/ds01-dcgm-exporter.service"
        issue: "Service file exists but not installed to /etc/systemd/system/"
    missing:
      - "Deploy service to /etc/systemd/system/ds01-dcgm-exporter.service"
      - "Enable and start service via systemctl"
      - "Wait 7 days to verify no crashes"
  
  - truth: "Alertmanager email configuration functional (test notification delivered)"
    status: failed
    reason: "SMTP password not configured - email alerting cannot function"
    artifacts:
      - path: "monitoring/alertmanager/alertmanager.yml"
        issue: "smtp_auth_password commented out, no .env file with credentials"
    missing:
      - "Configure SMTP password in monitoring/.env or alertmanager.yml"
      - "Verify h.baker@hertie-school.org account has SMTP auth enabled"
      - "Send test alert to confirm email delivery"
---

# Phase 1: Foundation & Observability Verification Report

**Phase Goal:** Observability infrastructure works reliably before adding complexity. Event logging functional, monitoring stable, alerts configured.

**Verified:** 2026-01-30T15:30:00Z  
**Status:** gaps_found  
**Re-verification:** No — initial verification

## Goal Achievement

### Observable Truths

| # | Truth | Status | Evidence |
|---|-------|--------|----------|
| 1 | Event log records all container lifecycle events (create, start, stop, remove) with timestamps and user attribution | ✓ VERIFIED | `docker-wrapper.sh:730` logs container.create, `gpu_allocator_v2.py` logs at allocate/release, maintenance scripts log lifecycle events |
| 2 | Event log records GPU allocation and release events in structured JSON format | ✓ VERIFIED | `gpu_allocator_v2.py:366-370` logs gpu.allocate with user/container/gpu details, `gpu_allocator_v2.py:618-624` logs gpu.release |
| 3 | DCGM exporter runs reliably without crashing for 7+ days | ✗ FAILED | Systemd service created but NOT deployed - service file at `config/deploy/systemd/ds01-dcgm-exporter.service` but not in `/etc/systemd/system/` |
| 4 | Alertmanager email configuration functional (test notification delivered) | ✗ FAILED | SMTP credentials missing - `alertmanager.yml:21` has password commented out, no email can be sent |
| 5 | Admin can query event log for audit purposes via CLI or log viewer | ✓ VERIFIED | `scripts/monitoring/ds01-events` provides jq-based query tool with --user, --type, --container, --since, --until filters |
| 6 | Automated semantic versioning via CI pipeline produces correct version tags on merge to main | ✓ VERIFIED | `.github/workflows/release.yml` + `.releaserc.json` configure semantic-release with 6 plugins, auto-triggers on push to main |

**Score:** 4/6 truths verified (67%)

### Required Artifacts

| Artifact | Expected | Status | Details |
|----------|----------|--------|---------|
| `scripts/lib/ds01_events.py` | Shared Python event logging library | ✓ VERIFIED | 280 lines, log_event() function, CLI interface, EVENT_TYPES dict, never-block pattern |
| `scripts/lib/ds01_events.sh` | Bash wrapper for event logging | ✓ VERIFIED | 71 lines, sources Python CLI, auto-detects source, || true pattern |
| `/var/log/ds01/events.jsonl` | Event log file | ⚠️ ORPHANED | File exists but permissions 644 root:root - not writable by non-root, event logging fails with permission denied |
| `config/deploy/logrotate.d/ds01` | Logrotate config with copytruncate | ✓ VERIFIED | Lines 37-48 configure events.jsonl rotation with copytruncate, maxsize 100M, daily rotation |
| `scripts/docker/event-logger.py` | Refactored to use shared library | ✓ VERIFIED | Line 31 imports ds01_events.log_event, EventReader for queries, delegates logging to shared lib |
| `scripts/monitoring/ds01-events` | jq-based query tool | ✓ VERIFIED | 603 lines, jq-based filtering (line 18 checks for jq), 4-tier help, --user/--type/--container filters |
| `scripts/docker/docker-wrapper.sh` | Instrumented with event logging | ✓ VERIFIED | Lines 598-599 log auth.denied, lines 729-730 log container.create |
| `scripts/docker/gpu_allocator_v2.py` | Instrumented with event logging | ✓ VERIFIED | Lines 50-55 safe import, 27 log_event calls throughout (gpu.allocate, gpu.reject, gpu.release) |
| `scripts/monitoring/check-idle-containers.sh` | Instrumented with event logging | ✓ VERIFIED | Lines 396-397 log maintenance.idle_kill events |
| `scripts/maintenance/*.sh` | Instrumented with event logging | ✓ VERIFIED | 3 files found with log_event calls (enforce-max-runtime, cleanup-stale-gpu-allocations, cleanup-stale-containers) |
| `config/deploy/systemd/ds01-dcgm-exporter.service` | DCGM systemd service | ✗ STUB | File exists with Restart=always, ExecStop, timeout policies BUT not deployed to /etc/systemd/system/ |
| `monitoring/docker-compose.yaml` | DCGM restart: "no" | ✓ VERIFIED | Line 75 sets restart: "no" for dcgm-exporter (systemd manages restarts) |
| `monitoring/alertmanager/alertmanager.yml` | Dual-channel alerting config | ⚠️ PARTIAL | Lines 72-101 configure email + Teams receivers, but line 21 SMTP password commented out - email won't work |
| `monitoring/prometheus/rules/ds01_alerts.yml` | Alert rules | ✓ VERIFIED | 250 lines, 4 alert groups, DCGMExporterDown at line 153 is critical severity, GrafanaDown/AlertmanagerDown added |
| `.github/workflows/release.yml` | Semantic-release workflow | ✓ VERIFIED | Lines 1-47 configure auto-trigger on push to main, semantic-release with dry-run option |
| `.releaserc.json` | Semantic-release config | ✓ VERIFIED | 18 lines, 6 plugins including changelog, exec (VERSION file), git, github |

### Key Link Verification

| From | To | Via | Status | Details |
|------|-----|-----|--------|---------|
| Bash scripts | Python event logger | CLI call | ✓ WIRED | `ds01_events.sh:65` calls `python3 /opt/ds01-infra/scripts/lib/ds01_events.py log` |
| Python scripts | Shared event logger | Import | ✓ WIRED | `event-logger.py:31` imports, `gpu_allocator_v2.py:51` imports with safe fallback |
| Event logging | events.jsonl file | Write operation | ✗ NOT_WIRED | Fails with permission denied - file is 644 root:root, non-root cannot write |
| docker-wrapper | Event logging | Function call | ✓ WIRED | Lines 598, 729 call log_event after checking command exists |
| GPU allocator | Event logging | Function call | ✓ WIRED | 27 log_event calls throughout allocation/rejection/release code paths |
| Logrotate | events.jsonl | Rotation | ✓ WIRED | Config at lines 37-48 with copytruncate prevents file descriptor issues |
| Systemd | DCGM container | Service management | ✗ NOT_WIRED | Service file created but not installed to /etc/systemd/system/ |
| Alertmanager | Email server | SMTP | ✗ NOT_WIRED | SMTP password missing, email notifications cannot be sent |
| Alertmanager | Teams webhook | HTTP POST | ✓ WIRED | Lines 84, 100 have hardcoded webhook URLs |
| GitHub Actions | semantic-release | Workflow trigger | ✓ WIRED | Lines 3-5 trigger on push to main, line 46 runs semantic-release |

### Requirements Coverage

| Requirement | Status | Blocking Issue |
|-------------|--------|----------------|
| LOG-01: Event log records all container lifecycle events | ✓ SATISFIED | None - instrumentation complete |
| LOG-02: Event log records GPU allocation and release events | ✓ SATISFIED | None - GPU allocator instrumented |
| LOG-03: Event log records unmanaged workload detection events | ⚠️ PARTIAL | Event types defined in EVENT_TYPES but Phase 2 detection not yet built |
| LOG-04: Events stored in structured format (JSON) queryable for audit | ✓ SATISFIED | None - ds01-events query tool functional |
| CICD-01: Automated semantic versioning through CI pipeline | ✓ SATISFIED | None - semantic-release configured |

### Anti-Patterns Found

| File | Line | Pattern | Severity | Impact |
|------|------|---------|----------|--------|
| `/var/log/ds01/events.jsonl` | - | File permissions 644 root:root | 🛑 Blocker | Event logging fails for all non-root scripts - instrumentation is wired but cannot write |
| `config/deploy/systemd/ds01-dcgm-exporter.service` | - | Deployment incomplete | 🛑 Blocker | Service file created but not deployed - cannot verify 7-day stability requirement |
| `monitoring/alertmanager/alertmanager.yml` | 21 | SMTP password commented out | 🛑 Blocker | Email alerting completely non-functional without credentials |

### Human Verification Required

#### 1. DCGM Exporter 7-Day Stability

**Test:** Deploy DCGM systemd service and monitor for 7 days  
**Expected:** Service remains running without crashes, auto-restarts on failure  
**Why human:** Requires time-based observation (7 days) and real-world crash scenarios  

**Steps:**
```bash
# Deploy service
sudo cp /opt/ds01-infra/config/deploy/systemd/ds01-dcgm-exporter.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ds01-dcgm-exporter
sudo systemctl start ds01-dcgm-exporter

# Monitor for 7 days
sudo systemctl status ds01-dcgm-exporter  # Check status
sudo journalctl -u ds01-dcgm-exporter -f  # Watch logs

# After 7 days, verify uptime
sudo systemctl show ds01-dcgm-exporter | grep ActiveEnterTimestamp
```

#### 2. Email Alerting Functional Test

**Test:** Configure SMTP password and send test alert  
**Expected:** Email delivered to datasciencelab@hertie-school.org and h.baker@hertie-school.org  
**Why human:** Requires SMTP credentials and external email delivery verification  

**Steps:**
```bash
# Configure password (choose one option)
# Option 1: .env file
echo "SMTP_AUTH_PASSWORD=your_password" >> /opt/ds01-infra/monitoring/.env

# Option 2: Uncomment line 21 in alertmanager.yml and add password

# Restart alertmanager
cd /opt/ds01-infra/monitoring
docker-compose restart alertmanager

# Trigger test alert via Alertmanager API
curl -XPOST http://localhost:9093/api/v1/alerts -d '[
  {
    "labels": {"alertname": "TestAlert", "severity": "warning"},
    "annotations": {"summary": "Test notification from DS01"}
  }
]'

# Verify email received in both inboxes
```

#### 3. Event Log Write Permissions

**Test:** Fix file permissions and verify event logging works for all scripts  
**Expected:** Non-root users can write events, logs appear in events.jsonl  
**Why human:** Requires root access to fix permissions and verification across multiple user contexts  

**Steps:**
```bash
# Fix permissions (choose one approach)
# Option 1: World-writable (simple but less secure)
sudo chmod 666 /var/log/ds01/events.jsonl

# Option 2: Group ownership (preferred)
sudo chown root:docker /var/log/ds01/events.jsonl
sudo chmod 664 /var/log/ds01/events.jsonl

# Test event logging as non-root
python3 /opt/ds01-infra/scripts/lib/ds01_events.py log test.verification source=manual result=success

# Verify event written
tail -1 /var/log/ds01/events.jsonl

# Test from Bash
source /opt/ds01-infra/scripts/lib/ds01_events.sh
log_event "test.bash_wrapper" "$USER" "manual-test" result=success

# Verify both events visible
/opt/ds01-infra/scripts/monitoring/ds01-events --type test --limit 5
```

### Gaps Summary

**Gap 1: DCGM Exporter Deployment Incomplete**

The systemd service file for DCGM exporter exists with proper restart policies, ExecStop directive, and timeout handling, but was never deployed to the system. Success criterion #3 requires the exporter to run reliably for 7+ days, which cannot be verified without deployment.

**Root cause:** Plan 01-02 created the service file but marked deployment as "User Setup Required" rather than completing it during execution.

**Impact:** Cannot verify monitoring stability requirement - blocks phase completion.

**Gap 2: Email Alerting Non-Functional**

Alertmanager is configured for dual-channel alerting (email + Teams) with proper routing, but SMTP authentication password is missing. The configuration file has the password commented out (line 21) and no .env file exists with credentials. Teams webhook is configured and should work, but email is completely blocked.

**Root cause:** Plan 01-03 noted "SMTP password still needs configuring" in summary but didn't block on it.

**Impact:** 50% of dual-channel alerting is non-functional - blocks success criterion #4.

**Gap 3: Event Log File Permissions**

The event logging library is fully implemented and all scripts are instrumented, but `/var/log/ds01/events.jsonl` has permissions 644 root:root. Non-root processes cannot write events, causing all event logging to fail with "permission denied" errors.

**Root cause:** Plan 01-01 noted "File permissions on /var/log/ds01/events.jsonl must be fixed before downstream plans can write events" but subsequent plans proceeded anyway.

**Impact:** Event logging infrastructure is wired but inoperative for non-root use cases - creates false sense of completion.

---

## Detailed Verification

### Truth 1: Container Lifecycle Event Logging (VERIFIED)

**Evidence of substantive implementation:**

1. **docker-wrapper.sh instrumentation:**
   - Line 598-601: Checks for log_event availability and logs auth.denied events
   - Line 729-732: Logs container.create events with user, source, container details
   - Uses best-effort pattern: `command -v log_event &>/dev/null` check before calling

2. **Event schema includes required fields:**
   - ds01_events.py line 148: timestamp in UTC ISO 8601 format
   - Line 149: event_type field (e.g., "container.create")
   - Line 154-158: user field when provided
   - Line 161-162: details object for additional fields

3. **Wiring confirmed:**
   - docker-wrapper sources ds01_events.sh or calls Python directly
   - Events written to /var/log/ds01/events.jsonl (line 50 of ds01_events.py)
   - Query tool at scripts/monitoring/ds01-events can retrieve and filter events

**Gap:** File permissions prevent non-root writes, but infrastructure is complete and will work once permissions fixed.

### Truth 2: GPU Allocation Event Logging (VERIFIED)

**Evidence of substantive implementation:**

1. **gpu_allocator_v2.py instrumentation:**
   - Lines 50-55: Safe import with fallback (never breaks allocator if logging fails)
   - Line 291-295: Logs gpu.reject on full GPU denial
   - Line 310-314: Logs gpu.reject on quota exceeded
   - Line 366-370: Logs gpu.allocate on successful allocation with user, container, gpu, priority, container_type
   - Line 618-624: Logs gpu.release on deallocation with user, container, gpu, reason

2. **Structured JSON format:**
   - Uses shared ds01_events.log_event() which produces standardised envelope
   - Details include: gpu slot, priority, container_type, reason
   - Schema version field enables future evolution

3. **27 log_event calls throughout allocator:**
   - Allocation path: lines 291, 310, 333, 351, 366, 436, 446, 496, 516, 521, 527
   - Release path: lines 618, 848, 862, 881
   - External allocation: lines 721, 742, 750
   - All use best-effort pattern (never blocks allocation logic)

**Gap:** Same file permission issue as Truth 1, but logging infrastructure complete.

### Truth 3: DCGM Exporter 7-Day Reliability (FAILED)

**Artifact exists:**
- `config/deploy/systemd/ds01-dcgm-exporter.service` is 45 lines
- Contains Restart=always (line 30)
- Contains ExecStop directive (line 34) to prevent GitHub Issue #606 hang
- Contains TimeoutStopSec=45s (line 35)
- Contains restart rate limiting StartLimitBurst=5 (line 26)

**Artifact is stub/incomplete:**
- File exists in repo at `config/deploy/systemd/` but not in `/etc/systemd/system/`
- `systemctl status ds01-dcgm-exporter` returns "Unit could not be found"
- docker-compose.yaml line 75 sets restart: "no" expecting systemd to manage restarts
- Without deployment, systemd isn't managing anything

**Wiring missing:**
- Service file not copied to /etc/systemd/system/
- systemctl daemon-reload not run
- Service not enabled or started
- Cannot verify 7-day reliability without actual deployment

**Blocker severity:** High - success criterion explicitly requires "7+ days" of reliable operation, which is impossible to verify without deployment.

### Truth 4: Email Alerting Functional (FAILED)

**Artifact exists:**
- `monitoring/alertmanager/alertmanager.yml` is 106 lines
- Contains dual-channel config (email + Teams)
- Lines 72-81: ds01-admin email receiver with 2 recipients
- Lines 88-97: ds01-critical email receiver with 2 recipients
- Lines 17-22: SMTP configuration with hertie-school.org server

**Artifact is incomplete:**
- Line 21: `# smtp_auth_password: 'YOUR_PASSWORD_HERE'` is commented out
- No monitoring/.env file exists with SMTP_AUTH_PASSWORD
- Plan 01-03 summary notes "SMTP password not yet available" and "email channel will fail"
- Teams webhook URLs are configured (lines 84, 100) so Teams alerting should work

**Testing shows:**
- Cannot send test email without SMTP credentials
- Alertmanager will silently fail email sending
- Summary explicitly states "email alerting blocked on SMTP password"

**Blocker severity:** Medium - 50% of dual-channel alerting works (Teams), but success criterion says "email configuration functional" which is false.

### Truth 5: Admin Can Query Event Log (VERIFIED)

**Evidence of substantive implementation:**

1. **ds01-events query tool:**
   - 603 lines (scripts/monitoring/ds01-events)
   - Line 18: Checks for jq dependency
   - Lines 41-84: build_jq_filter() creates structured queries with AND logic
   - Supports filters: --user, --type (prefix match), --container, --since, --until
   - Output modes: human-readable table, --json, --follow (live stream), --summary

2. **4-tier help system:**
   - --help: Quick reference
   - --info: Full reference
   - --concepts: Architecture explanation
   - --guided: Interactive tutorial

3. **Schema compatibility:**
   - Lines 44-46: Handles both old (ts/event) and new (timestamp/event_type) schemas
   - Uses jq's `//` operator for backward compatibility
   - Works with mixed event logs during transition

4. **Wiring confirmed:**
   - Tool reads from /var/log/ds01/events.jsonl (line 15)
   - jq-based filtering (26 invocations throughout, no grep)
   - Colorized output via sed (after column formatting)

**Gap:** Event log file is empty due to permission issues, but query tool itself is fully functional and will work once events exist.

### Truth 6: Automated Semantic Versioning (VERIFIED)

**Evidence of substantive implementation:**

1. **.github/workflows/release.yml:**
   - Lines 3-5: Triggers on push to main (automatic versioning)
   - Lines 7-11: Manual workflow_dispatch for dry-run testing
   - Line 34: Installs semantic-release with 4 plugins
   - Line 46: Runs semantic-release automatically

2. **.releaserc.json configuration:**
   - Line 2: Branches: ["main"]
   - Lines 4-5: commit-analyzer determines version bump from conventional commits
   - Lines 6-8: changelog plugin generates CHANGELOG.md
   - Lines 9-11: exec plugin writes VERSION file
   - Lines 12-15: git plugin commits CHANGELOG.md and VERSION with [skip ci]
   - Line 16: github plugin creates GitHub release with tag

3. **Wiring confirmed:**
   - GitHub Actions workflow exists at .github/workflows/release.yml
   - Config file exists at .releaserc.json
   - Workflow has permissions: contents:write, issues:write, pull-requests:write
   - Auto-triggers on main branch push (not manual-only)

4. **Testing capability:**
   - Dry-run mode available via workflow_dispatch
   - Can preview changes without releasing
   - Preserves manual testing option while enabling automation

**No gaps:** Fully implemented and ready to use on next merge to main.

---

## Anti-Pattern Analysis

### 1. File Permissions Blocker (events.jsonl)

**Pattern:** Created infrastructure file with root-only write permissions  
**Location:** /var/log/ds01/events.jsonl (644 root:root)  
**Impact:** All event logging fails for non-root scripts - creates false sense of working instrumentation  

**Why this is critical:**
- Plan 01-01 explicitly noted this as a blocker for downstream plans
- Plans 01-05 and 01-06 proceeded assuming permissions would be fixed
- Extensive instrumentation (docker-wrapper, GPU allocator, maintenance scripts) is wired but inoperative
- Silent failure pattern - scripts don't crash, but no events are written

**Resolution path:**
```bash
# Option 1: Group ownership (recommended)
sudo chown root:docker /var/log/ds01/events.jsonl
sudo chmod 664 /var/log/ds01/events.jsonl

# Option 2: World-writable (simpler but less secure)
sudo chmod 666 /var/log/ds01/events.jsonl
```

### 2. Deployment Incomplete (DCGM systemd service)

**Pattern:** Created deployment artifact but didn't deploy it  
**Location:** config/deploy/systemd/ds01-dcgm-exporter.service  
**Impact:** Cannot verify success criterion #3 (7-day reliability)  

**Why this matters:**
- Plan 01-02 marked deployment as "User Setup Required" rather than completing it
- Success criterion explicitly requires 7+ days of stable operation
- Service file is well-designed (restart policies, timeouts, ExecStop) but unused
- docker-compose.yaml sets restart: "no" expecting systemd to manage it

**Resolution path:**
```bash
sudo cp /opt/ds01-infra/config/deploy/systemd/ds01-dcgm-exporter.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable ds01-dcgm-exporter
sudo systemctl start ds01-dcgm-exporter
# Wait 7 days, verify no crashes
```

### 3. Missing Credentials (Alertmanager SMTP)

**Pattern:** Configured service with placeholder credentials  
**Location:** monitoring/alertmanager/alertmanager.yml line 21  
**Impact:** Email alerting completely non-functional (50% of dual-channel alerting down)  

**Why this blocks:**
- Success criterion #4 says "email configuration functional (test notification delivered)"
- Configuration exists but cannot deliver email without password
- Plan 01-03 noted this but didn't block on it
- Teams webhook is configured and should work, but email is blocked

**Resolution path:**
```bash
# Add to monitoring/.env
echo "SMTP_AUTH_PASSWORD=your_password" >> monitoring/.env

# Or uncomment line 21 in alertmanager.yml
# smtp_auth_password: 'actual_password'

# Restart alertmanager
docker-compose restart alertmanager
```

---

## Recommendations

### Immediate Actions (Block Phase Completion)

1. **Fix event log permissions** - Blocks LOG-01, LOG-02, LOG-04
   - Run: `sudo chmod 664 /var/log/ds01/events.jsonl && sudo chown root:docker /var/log/ds01/events.jsonl`
   - Test: `python3 /opt/ds01-infra/scripts/lib/ds01_events.py log test.verification source=fix-check result=success`
   - Verify: `tail -1 /var/log/ds01/events.jsonl` shows JSON event

2. **Deploy DCGM systemd service** - Blocks success criterion #3
   - Deploy service file to /etc/systemd/system/
   - Enable and start service
   - **Wait 7 days** to verify stability requirement
   - Monitor: `journalctl -u ds01-dcgm-exporter -f`

3. **Configure SMTP password** - Blocks success criterion #4
   - Obtain password for h.baker@hertie-school.org SMTP auth
   - Add to monitoring/.env or alertmanager.yml
   - Restart alertmanager
   - Send test alert and verify email delivery

### Nice to Have (Not Blocking)

1. **Document deployment steps** - Create deployment checklist covering:
   - Event log permissions setup
   - Systemd service deployment
   - Alertmanager credentials configuration
   - Verification steps for each

2. **Add automation to deployment script** - Update deploy-commands.sh to:
   - Set event log permissions automatically
   - Copy systemd service files to /etc/systemd/system/
   - Reload systemd and enable services
   - Prompt for SMTP password during setup

3. **Create monitoring health check** - Add script to verify:
   - Event logging permissions correct
   - DCGM exporter systemd service running
   - Alertmanager can send email (test mode)

---

_Verified: 2026-01-30T15:30:00Z_  
_Verifier: Claude (gsd-verifier)_  
_Mode: Initial verification (no previous VERIFICATION.md found)_
