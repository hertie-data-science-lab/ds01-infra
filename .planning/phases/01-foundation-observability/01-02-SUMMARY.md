---
phase: 01-foundation-observability
plan: 02
subsystem: infra
tags: [systemd, docker, dcgm, monitoring, nvidia, gpu-metrics]

# Dependency graph
requires:
  - phase: 01-foundation-observability
    provides: Monitoring stack with DCGM exporter
provides:
  - Robust DCGM exporter systemd service with restart policies
  - Explicit ExecStop prevents restart hangs (GitHub Issue #606)
  - Hybrid docker-compose + systemd lifecycle management pattern
affects: [monitoring, observability, deployment]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - Hybrid docker-compose + systemd pattern for container lifecycle
    - Systemd restart rate limiting with StartLimitBurst
    - Explicit ExecStop prevents systemd restart hangs

key-files:
  created:
    - config/deploy/systemd/ds01-dcgm-exporter.service
  modified:
    - monitoring/docker-compose.yaml

key-decisions:
  - "Use systemd for DCGM restart management (not docker-compose)"
  - "ExecStop with explicit docker stop prevents GitHub Issue #606 hang"
  - "StartLimitBurst=5 prevents infinite restart loops"
  - "TimeoutStopSec=45s gives 30s graceful + 15s buffer before SIGKILL"

patterns-established:
  - "Hybrid pattern: docker-compose creates container, systemd manages restarts"
  - "Infrastructure containers use /usr/bin/docker (not DS01 wrapper)"

# Metrics
duration: 4min
completed: 2026-01-30
---

# Phase 01 Plan 02: DCGM Exporter Stability Summary

**Systemd service with robust restart handling fixes DCGM exporter crashes via ExecStop directive and timeout policies**

## Performance

- **Duration:** ~4 min
- **Started:** 2026-01-30T13:12:15Z
- **Completed:** 2026-01-30T13:16:00Z (approx)
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Created systemd service for DCGM exporter with proper restart and stop handling
- Fixed restart hang issue identified in GitHub Issue #606 via explicit ExecStop
- Delegated restart management from docker-compose to systemd to prevent conflicts
- Established hybrid pattern for infrastructure container lifecycle management

## Task Commits

Each task was committed atomically:

1. **Task 1: Create DCGM exporter systemd service** - `1b25d14` (feat)
2. **Task 2: Update docker-compose to delegate DCGM restart to systemd** - `5a5aadd` (feat)

## Files Created/Modified
- `config/deploy/systemd/ds01-dcgm-exporter.service` - Systemd unit file with Restart=always, ExecStop, timeout policies, and restart rate limiting
- `monitoring/docker-compose.yaml` - Changed dcgm-exporter restart policy to "no" (systemd manages restarts)

## Decisions Made

**1. Use systemd for restart management instead of docker-compose**
- **Rationale:** Research identified that docker-compose restart policies conflict with systemd management and can trigger MIG race conditions. Systemd provides better restart sequencing and timeout control.

**2. Explicit ExecStop directive prevents restart hangs**
- **Rationale:** GitHub Issue #606 documents that missing ExecStop causes systemd to hang on restart. Adding `ExecStop=/usr/bin/docker stop -t 30` with `TimeoutStopSec=45s` prevents this.

**3. Restart rate limiting with StartLimitBurst=5**
- **Rationale:** Prevents infinite restart loops if DCGM exporter is fundamentally broken. After 5 failures in 300s, systemd stops attempting restart.

**4. Use /usr/bin/docker (real binary, not DS01 wrapper)**
- **Rationale:** DCGM container is infrastructure, not user workload. No need for DS01 wrapper's slice injection and enforcement.

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

**Issue:** systemd-analyze initially showed warning about `StartLimitIntervalSec` in `[Service]` section.
- **Resolution:** Moved `StartLimitIntervalSec` and `StartLimitBurst` to `[Unit]` section (correct placement).
- **Impact:** None - detected during verification before commit.

## User Setup Required

**Deployment required** - service file created but not yet deployed to system.

Administrator must:
1. Copy service file: `sudo cp /opt/ds01-infra/config/deploy/systemd/ds01-dcgm-exporter.service /etc/systemd/system/`
2. Reload systemd: `sudo systemctl daemon-reload`
3. Enable service: `sudo systemctl enable ds01-dcgm-exporter`
4. Ensure DCGM container exists (via docker-compose): `cd /opt/ds01-infra/monitoring && docker-compose up -d`
5. Start service: `sudo systemctl start ds01-dcgm-exporter`
6. Verify: `sudo systemctl status ds01-dcgm-exporter`

After deployment, DCGM exporter will auto-restart on failure and prevent the periodic crashes noted in STATE.md blocker.

## Next Phase Readiness

**Ready for next monitoring/observability work:**
- DCGM exporter now has robust restart handling
- Hybrid docker-compose + systemd pattern established and documented
- Service ready for deployment

**Blocker resolution:**
- Addresses "DCGM exporter crashes periodically" blocker noted in STATE.md
- After deployment, crashes will auto-recover via systemd restart

**Pattern established:**
- Hybrid pattern (docker-compose creates, systemd manages restarts) can be applied to other infrastructure containers if needed

---
*Phase: 01-foundation-observability*
*Completed: 2026-01-30*
