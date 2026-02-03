---
phase: 01-foundation-observability
plan: 03
subsystem: monitoring
tags: [alertmanager, prometheus, teams-webhook, smtp, alerting]

requires:
  - phase: none
    provides: "Independent plan"
provides:
  - "Dual-channel alerting (email + Teams webhook)"
  - "Comprehensive monitoring health alert rules"
  - "Alertmanager v0.28.1 with native Teams support"
affects: [monitoring, observability]

tech-stack:
  added: [alertmanager-v0.28.1, teams-webhook]
  patterns: [dual-channel-alerting, severity-based-routing]

key-files:
  created: []
  modified:
    - monitoring/alertmanager/alertmanager.yml
    - monitoring/docker-compose.yaml
    - monitoring/prometheus/rules/ds01_alerts.yml

key-decisions:
  - "SMTP sender changed from non-existent ds01-alerts@hertie-school.org to datasciencelab@hertie-school.org"
  - "DCGM exporter down upgraded from warning to critical severity"
  - "Teams webhook configured directly (not via env var placeholder)"
  - "h.baker@hertie-school.org added as additional email recipient on both receivers"

duration: 8min
completed: 2026-01-30
---

# Phase 1 Plan 03: Alertmanager Dual-Channel Alerting Summary

**Alertmanager v0.28.1 with dual-channel email+Teams routing, severity-based fast-path, and comprehensive monitoring health alerts**

## Performance

- **Duration:** ~8 min
- **Tasks:** 3 (2 auto + 1 checkpoint)
- **Files modified:** 3

## Accomplishments
- Upgraded Alertmanager from v0.26.0 to v0.28.1 (native Teams webhook support)
- Configured dual-channel receivers: email (datasciencelab + h.baker) and Teams webhook
- Aggressive grouping (5min batch) with critical fast-path (30s group_wait, 1h repeat)
- Enhanced alert rules: DCGMExporterDown upgraded to critical, added GrafanaDown, AlertmanagerDown, GPUXIDError
- Teams webhook URL configured live during checkpoint

## Task Commits

1. **Task 1: Upgrade Alertmanager and configure dual-channel alerting** - `4b9249a` (feat)
2. **Task 2: Enhance monitoring health alert rules** - `237cc15` (feat)
3. **Task 3: Configure credentials (checkpoint)** - `821a34f` (feat)

## Files Created/Modified
- `monitoring/alertmanager/alertmanager.yml` - Dual-channel config with Teams webhook and 2 email recipients
- `monitoring/docker-compose.yaml` - Alertmanager image upgraded to v0.28.1
- `monitoring/prometheus/rules/ds01_alerts.yml` - 3 new alerts, 1 severity upgrade

## Decisions Made
- SMTP sender changed to datasciencelab@hertie-school.org (ds01-alerts@ didn't exist)
- DCGM exporter down → critical severity (GPU metrics are critical infrastructure)
- Teams webhook URL hardcoded rather than env var (simpler for single-instance deployment)
- SMTP password still needs configuring — email alerting won't work until credentials provided

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] SMTP sender account doesn't exist**
- **Found during:** Checkpoint (user reported ds01-alerts@ doesn't exist)
- **Fix:** Changed smtp_from and smtp_auth_username to datasciencelab@hertie-school.org
- **Committed in:** 821a34f

## Issues Encountered
- SMTP password not yet available — email channel will fail until password is configured
- Email alerting requires IT to confirm SMTP auth works with datasciencelab@ account

## User Setup Required
**SMTP password still needed.** Add to `monitoring/.env` as `SMTP_AUTH_PASSWORD=your_password` or uncomment line 21 in alertmanager.yml when available.

## Next Phase Readiness
- Teams alerting ready for testing once monitoring stack is restarted
- Email alerting blocked on SMTP password
- Alert rules ready — will fire once Prometheus reloads config

---
*Phase: 01-foundation-observability*
*Completed: 2026-01-30*
