# Phase 6: Lifecycle Enhancements - Context

**Gathered:** 2026-02-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Tune lifecycle enforcement for real-world usage patterns and add admin override controls. Phase 5 built the enforcement engine (idle detection, max runtime, cleanup, GPU health verification). Phase 6 makes it practical: adjust thresholds to reduce false positives, add per-user exemption toggles for research workflows, and ensure graceful shutdown works reliably for large GPU containers.

</domain>

<decisions>
## Implementation Decisions

### Threshold tuning
- Idle detection thresholds configurable **per-group** in resource config (not global-only)
- Multi-signal idle detection uses **AND logic** — container only idle when ALL signals (GPU, CPU, network) are below their respective thresholds
- **Both thresholds AND detection window** (consecutive checks before action) should be tunable per-group
- GPU threshold adjustment: Claude's discretion — evaluate whether <5% GPU threshold also needs raising based on real workload patterns during research

### Override granularity
- **Per-user** exemptions for both idle timeout and max runtime (same granularity for both)
- Consistent model: same mechanism controls idle exemption and runtime exemption
- **Time-bounded exemptions** supported — optional expiry date (e.g., `exempt_until: 2026-03-01`) for temporary research grants; permanent if no expiry specified

### Config format & UX
- Config file location (resource-limits.yaml vs separate file): Claude's discretion — research best practices for lifecycle policy configuration in HPC/container orchestration
- User exemption storage (inline YAML list vs external file): Claude's discretion — research best practices, but must be consistent with existing DS01 patterns (e.g., bare-metal-grants uses external files)
- Admin CLI for managing exemptions: Claude's discretion — if implemented, config file must remain SSOT (CLI reads/writes the file, doesn't bypass it)
- Change propagation timing (immediate vs next cron cycle): Claude's discretion — research best practices

### Graceful shutdown
- Pre-stop notification: **wall message only** — consistent with Phase 5 notification pattern
- Docker stop timeout vs SIGTERM grace alignment: Claude's discretion — audit what Phase 5 implemented and fill gaps
- Variable timeout by container type (GPU vs non-GPU): Claude's discretion — research best practices for container orchestration
- Escalation after grace period: Claude's discretion — research best practices (log + SIGKILL vs immediate SIGKILL)

### Claude's Discretion
- GPU idle threshold adjustment (raise from <5% or keep)
- Config file organisation for lifecycle policies
- Exemption storage format (inline vs external)
- Whether to build admin CLI for exemptions
- Change propagation timing
- Variable stop timeouts by container type
- Force-kill escalation behaviour
- Whether exempt users still receive informational warnings

</decisions>

<specifics>
## Specific Ideas

- User expressed strong preference for research-based decisions — multiple "you decide based on web search of best industry practice" answers indicate desire for well-researched, industry-standard approaches rather than ad-hoc choices
- Config file must be SSOT regardless of whether CLI tooling is added
- Time-bounded exemptions are important for the use case (temporary research grants, not permanent policy exceptions)

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 06-lifecycle-enhancements*
*Context gathered: 2026-02-14*
