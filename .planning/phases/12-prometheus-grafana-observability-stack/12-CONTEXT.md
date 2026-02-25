# Phase 12: Prometheus & Grafana Observability Stack - Context

**Gathered:** 2026-02-25
**Status:** Ready for planning

<domain>
## Phase Boundary

Audit, fix, and mature the existing Prometheus/Grafana observability stack. The stack already exists (Prometheus, Grafana, Alertmanager, DCGM Exporter, DS01 Exporter, Node Exporter) but has bugs, untested alerts, and gaps. This phase makes it production-grade following industry best practices — fixing what's broken, adding missing metrics, creating proper dashboards, and validating alerting end-to-end. Research other GPU monitoring codebases and HPC observability setups to ground decisions in proven patterns.

</domain>

<decisions>
## Implementation Decisions

### Dashboard design
- Fix existing buggy dashboards — some panels don't work, need methodical audit
- Two audiences: admin dashboards for operations + simplified user-facing dashboards
- **Clean separation of concerns**: real-time/current-state dashboards separate from historical/trend dashboards
- User-facing access: both Grafana (visual exploration) and CLI commands (quick terminal checks)
- Existing user-facing CLI commands already exist in the codebase — research should identify these and integrate
- Research industry best practice for GPU cluster dashboard design (SLURM, HPC, Kubernetes GPU dashboards)

### Alert tuning & delivery
- Current 47 alert rules are untested in production — need methodical validation
- **Teams-only notification** — drop email channel, Teams webhook needs to be created from scratch
- Claude decides alert management approach (start minimal vs keep-and-tune) based on industry practice for single-server GPU environments
- Each alert rule must be validated: fires correctly, delivers to Teams, thresholds are sensible

### Stack maturity
- **90-day metric retention** — increase from current 7-day/20GB (disk budget to be determined during planning)
- **Fully automatic recovery** on server reboot — zero manual intervention to restore monitoring
- **Lean resource footprint** — monitoring should not consume significant CPU/RAM; this is a GPU workstation first
- Claude decides Grafana auth model (likely anonymous read-only for internal server)
- Claude decides version pinning strategy (likely pin major versions, allow patch updates)

### Metric coverage
- **Add cAdvisor** for per-container resource metrics (CPU, memory, network, disk I/O) — industry standard, ~30MB RAM
- **Lifecycle events in Prometheus** — export enforcement actions (idle kills, runtime kills, GPU allocations, warnings) as metrics for dashboard panels showing enforcement activity over time
- **User login tracking** — SSH session data as Prometheus metrics; Claude decides detail level (active sessions gauge vs full session history) based on what's practical from auth.log/utmp
- **GPU cost attribution** — GPU-hours per user for awareness/fair-sharing visibility (not billing); recording rules exist but are untested, need validation
- Research should identify additional metric gaps based on industry practice
- Claude decides exporter architecture (enhance existing DS01 exporter vs separate exporters) based on maintainability

### Claude's Discretion
- Admin dashboard panel selection and layout (Claude picks based on what DS01 collects and industry norms)
- Grafana authentication model (anonymous read-only vs LDAP)
- Version management strategy (pin vs latest)
- Alert approach (minimal-first vs audit-all)
- Exporter architecture (single enhanced DS01 exporter vs multiple)
- Login tracking granularity
- Resource limits for monitoring containers
- Recording rule optimization

</decisions>

<specifics>
## Specific Ideas

- "The current dashboards are buggy — some panels don't work. We need to go through methodically to set this up"
- "I want this based on research of other codebases etc to follow industry best practice"
- "We already have some user-facing CLI commands — find these in research"
- Clean separation: real-time operational dashboards vs historical trend/reporting dashboards
- GPU cost attribution is for awareness and encouraging fair sharing, not actual billing/chargeback
- Teams webhook needs to be created from scratch (no existing working webhook)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 12-prometheus-grafana-observability-stack*
*Context gathered: 2026-02-25*
