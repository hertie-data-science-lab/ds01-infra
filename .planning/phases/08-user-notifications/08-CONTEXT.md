# Phase 8: User Notifications - Context

**Gathered:** 2026-02-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Timely alerts when containers approach idle timeout, max runtime, or resource quota limits. Notifications delivered to user terminals and as container-visible files. This phase builds on existing notification infrastructure from Phases 5-6 (idle/runtime wall messages already implemented) and Phase 4 (resource-alert-checker.sh writes quota alerts to JSON files but doesn't deliver to terminals).

**Already implemented:**
- `notify_user()` in check-idle-containers.sh and enforce-max-runtime.sh (writes to user PTY)
- Idle warning at 80% of timeout (single warning)
- Max runtime warning at 90% of limit (single warning)
- `resource-alert-checker.sh` detects GPU/container quota at 80%/100% (file-only, no terminal delivery)
- Login greeting (profile.d) shows quota bars

**Gaps to close:**
- Escalating warning sequences (currently single warning)
- Quota alerts delivered to terminals (currently file-only)
- Container-file fallback when user has no active terminals
- Shared notification library (currently duplicated across scripts)
- Login greeting integration with pending alerts

</domain>

<decisions>
## Implementation Decisions

### Message content & tone
- All notification types use the **same detailed style** as existing idle/runtime messages: bordered box with actionable instructions
- **Unified template** across all notification types with a severity/type header
- Severity labels: Claude's discretion (e.g., WARNING/NOTICE/STOPPED or similar)
- Each notification includes **full quota summary** (GPU, memory, containers) alongside the specific alert — gives full picture at a glance

### Delivery mechanism
- Primary delivery: `notify_user()` writing to user's TTY devices
- **Fallback**: Write alerts to `/workspace/.ds01-alerts` inside the container when user has no active terminals
- Belt-and-suspenders: try terminal first, fall back to container file
- **Shared notification library**: Extract `scripts/lib/ds01_notify.sh` with `notify_user()`, `format_message()`, and the unified template — replaces duplicated code in check-idle-containers.sh and enforce-max-runtime.sh
- **Login greeting integration**: Profile.d login greeting (Phase 4) shows pending alerts from `/var/lib/ds01/alerts/` alongside quota bars

### Timing & escalation
- **Two-level escalating sequence** for idle and runtime warnings:
  - First warning (early heads-up) + final warning (imminent action)
  - Replaces current single-warning approach
- GPU quota alerts **repeat with cooldown** while above threshold (cooldown period: Claude's discretion)
- Quota alerts fire once when crossing threshold, then repeat on cooldown; clear when usage drops below

### Quota alert behaviour
- Alert on **three resource types**: GPU, memory, and containers
- **Two tiers per resource**: 80% (approaching limit) and 100% (at limit/blocked)
- Own cron entry at `:10` of each hour — independent of lifecycle enforcement timing
- Quota alerts only fire for users who actually have limits configured — admin group (unlimited) won't trigger
- Lifecycle-exempt users still receive quota alerts if they have resource limits

### Claude's Discretion
- Exact severity label names for the unified template
- Specific warning thresholds for escalation levels (e.g., 80%+95% or 15min+5min)
- Quota alert cooldown period (reasonable balance of awareness vs annoyance)
- Container-file alert format (text vs structured)
- How login greeting displays pending alerts (inline vs summary)

</decisions>

<specifics>
## Specific Ideas

- Existing idle warning message style (bordered box with ━━━ lines) is the reference for all notification types
- Include actionable commands in every notification (e.g., `container-retire`, `check-limits`)
- GPU quota is the most valuable resource — consider giving GPU alerts slightly more prominence

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 08-user-notifications*
*Context gathered: 2026-02-17*
