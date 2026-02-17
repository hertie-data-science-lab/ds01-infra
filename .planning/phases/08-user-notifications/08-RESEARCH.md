# Phase 8: User Notifications - Research

**Researched:** 2026-02-17
**Domain:** Bash notification library, terminal delivery (PTY write), container-file fallback, escalating warning sequences, cron scheduling
**Confidence:** HIGH — all findings based on direct codebase inspection

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

- All notification types use the **same detailed style** as existing idle/runtime messages: bordered box with actionable instructions
- **Unified template** across all notification types with a severity/type header
- Each notification includes **full quota summary** (GPU, memory, containers) alongside the specific alert
- Primary delivery: `notify_user()` writing to user's TTY devices
- **Fallback**: Write alerts to `/workspace/.ds01-alerts` inside the container when user has no active terminals
- Belt-and-suspenders: try terminal first, fall back to container file
- **Shared notification library**: Extract `scripts/lib/ds01_notify.sh` with `notify_user()`, `format_message()`, and the unified template — replaces duplicated code in check-idle-containers.sh and enforce-max-runtime.sh
- **Login greeting integration**: Profile.d login greeting (Phase 4) shows pending alerts from `/var/lib/ds01/alerts/` alongside quota bars
- **Two-level escalating sequence** for idle and runtime warnings (first warning + final warning, replacing single-warning)
- GPU quota alerts **repeat with cooldown** while above threshold; clear when usage drops below
- Alert on **three resource types**: GPU, memory, and containers
- **Two tiers per resource**: 80% (approaching limit) and 100% (at limit/blocked)
- Own cron entry at `:10` of each hour for quota alerts
- Quota alerts only fire for users who actually have limits configured
- Lifecycle-exempt users still receive quota alerts if they have resource limits

### Claude's Discretion

- Exact severity label names for the unified template
- Specific warning thresholds for escalation levels (e.g., 80%+95% or 15min+5min)
- Quota alert cooldown period
- Container-file alert format (text vs structured)
- How login greeting displays pending alerts (inline vs summary)

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope
</user_constraints>

---

## Summary

Phase 8 closes the final user-experience gap in the DS01 lifecycle system. The notification infrastructure is partially in place (PTY delivery via `notify_user()` exists in two scripts, quota alerts are written to `/var/lib/ds01/alerts/` as JSON, and the login greeting shows quota bars) but the pieces are disconnected and incomplete. The work is consolidation + extension, not greenfield.

The core deliverable is `scripts/lib/ds01_notify.sh` — a shared notification library that all lifecycle scripts source. It centralises `notify_user()` (PTY delivery), `notify_container()` (file fallback to `/workspace/.ds01-alerts`), `format_notify_message()` (unified bordered-box template with quota summary), and `get_quota_summary()` (builds the resource snapshot appended to every message). Once the library exists, check-idle-containers.sh and enforce-max-runtime.sh are refactored to source it, resource-alert-checker.sh gains terminal delivery, and the login greeting gains a pending-alerts section.

**Primary recommendation:** Build `scripts/lib/ds01_notify.sh` first — everything else hangs off it. The library's `notify_user()` already exists verbatim in two scripts; extract it, add `notify_container()` and `format_notify_message()`, then wire up the callers.

---

## Standard Stack

### Core (no new dependencies)

| Tool | Version | Purpose | Why Standard |
|------|---------|---------|--------------|
| `bash` | system | Notification library and delivery | All lifecycle scripts are bash |
| `who` | coreutils | Enumerate user TTY devices | Already used in both `notify_user()` implementations |
| PTY write (`echo > /dev/pts/N`) | — | Write to specific terminal | Existing pattern in codebase |
| `docker exec` | system | Write fallback file inside container | Already used in check-idle-containers.sh |
| Python 3 | system | Read quota data from resource-limits.yaml | Already used for all config reads |

### Supporting

| Tool | Purpose | When to Use |
|------|---------|-------------|
| `get_resource_limits.py` | Fetch GPU/memory/container limits for quota summary | Called from `get_quota_summary()` in ds01_notify.sh |
| `gpu_allocator_v2.py status` | Get current GPU usage for quota summary | Called to calculate current vs max GPU |
| `/var/lib/ds01/alerts/${user}.json` | Persistent alert state (quota alerts) | Read by login greeting, written by resource-alert-checker.sh |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| PTY write via `echo > /dev/$tty` | `write` command or `wall` | `write` targets specific user (already what `who` gives us), `wall` broadcasts to ALL users — PTY write is already the established pattern |
| Plain text for container fallback file | JSON structured format | Plain text is simpler, human-readable inside the container, consistent with the terminal message format |

---

## Architecture Patterns

### Recommended File Structure

```
scripts/lib/
└── ds01_notify.sh          # NEW: shared notification library

scripts/monitoring/
└── check-idle-containers.sh  # REFACTOR: source ds01_notify.sh, add 2nd warning

scripts/maintenance/
└── enforce-max-runtime.sh    # REFACTOR: source ds01_notify.sh, add 2nd warning

scripts/monitoring/
└── resource-alert-checker.sh # EXTEND: add terminal delivery via ds01_notify.sh

config/deploy/profile.d/
└── ds01-quota-greeting.sh    # EXTEND: show pending alerts section

config/deploy/cron.d/
└── ds01-maintenance          # UPDATE: add quota-alert cron at :10
```

### Pattern 1: Shared Notification Library (ds01_notify.sh)

**What:** Centralises all notification primitives. Sourced by any script that needs to alert users.

**When to use:** Any cron script or maintenance script sending user alerts.

```bash
# scripts/lib/ds01_notify.sh

INFRA_ROOT="${DS01_ROOT:-/opt/ds01-infra}"
ALERTS_DIR="/var/lib/ds01/alerts"

# Send message to user's active terminal(s). Falls back to container file.
# Usage: ds01_notify <username> <container_name> <message>
#   container_name: used for file fallback only, pass "" if no container context
ds01_notify() {
    local username="$1"
    local container="$2"
    local message="$3"
    local delivered=false

    # Primary: write to each TTY the user has open
    while IFS= read -r tty; do
        [ -z "$tty" ] && continue
        echo "$message" > "/dev/$tty" 2>/dev/null && delivered=true
    done < <(who | awk -v user="$username" '$1 == user {print $2}')

    # Fallback: write to container file if no terminals and container known
    if [ "$delivered" = false ] && [ -n "$container" ]; then
        ds01_notify_container "$container" "$message"
    fi
}

# Write alert to /workspace/.ds01-alerts inside container
ds01_notify_container() {
    local container="$1"
    local message="$2"
    local timestamp
    timestamp=$(date '+%Y-%m-%d %H:%M:%S')

    # Append to alert file (plain text, separator between alerts)
    docker exec "$container" bash -c \
        "echo '--- Alert: $timestamp ---' >> /workspace/.ds01-alerts && \
         echo '$message' >> /workspace/.ds01-alerts && \
         echo '' >> /workspace/.ds01-alerts" 2>/dev/null || true
}

# Build quota summary line for appending to messages
# Returns multi-line string: GPU X/Y, Memory X/Y, Containers X/Y
ds01_quota_summary() {
    local username="$1"
    # ... reads from get_resource_limits.py and docker ps
}

# Format a notification message with bordered box and quota summary
# Usage: ds01_format_message <severity> <title> <body> <username>
# Severity: WARNING | NOTICE | STOPPED | ALERT
ds01_format_message() {
    local severity="$1"
    local title="$2"
    local body="$3"
    local username="$4"
    local quota_line
    quota_line=$(ds01_quota_summary "$username" 2>/dev/null || echo "")

    cat << EOF
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
[$severity] $title

$body

Your resource quotas:
$quota_line
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
EOF
}
```

### Pattern 2: Two-Level Escalating Warnings (idle and runtime)

**What:** Replace current single-warning at 80%/90% with two warnings.

**Recommended thresholds:**
- **Idle**: First warning at 80% of timeout ("heads-up"), final warning at 95% of timeout ("imminent")
- **Runtime**: First warning at 75% of limit ("plan ahead"), final warning at 90% of limit ("save now")

**State file extension:** Add `WARNED_FINAL=false` alongside existing `WARNED=false`.

```bash
# In process_container_universal() — idle warnings
local first_warning_seconds=$((timeout_seconds * 80 / 100))
local final_warning_seconds=$((timeout_seconds * 95 / 100))

if [ "$idle_seconds" -ge "$first_warning_seconds" ] && [ "${WARNED:-false}" != "true" ]; then
    local minutes_until_stop=$(( (timeout_seconds - idle_seconds) / 60 ))
    msg=$(ds01_format_message "WARNING" "IDLE CONTAINER WARNING" \
        "Container $container will auto-stop in ~${minutes_until_stop} minutes..." \
        "$username")
    ds01_notify "$username" "$container" "$msg"
    sed -i "s/^WARNED=.*/WARNED=true/" "$state_file"
fi

if [ "$idle_seconds" -ge "$final_warning_seconds" ] && [ "${WARNED_FINAL:-false}" != "true" ]; then
    local minutes_until_stop=$(( (timeout_seconds - idle_seconds) / 60 ))
    msg=$(ds01_format_message "WARNING" "FINAL IDLE WARNING — STOPPING SOON" \
        "Container $container will auto-stop in ~${minutes_until_stop} minutes..." \
        "$username")
    ds01_notify "$username" "$container" "$msg"
    sed -i "s/^WARNED_FINAL=.*/WARNED_FINAL=true/" "$state_file"
fi
```

### Pattern 3: Quota Alert Terminal Delivery with Cooldown

**What:** resource-alert-checker.sh already writes quota alerts to JSON files. Add terminal delivery with per-user cooldown tracking.

**Cooldown recommendation:** 4 hours. GPU alerts are most critical — fire immediately when threshold crossed, then only repeat every 4 hours while still above threshold. Clears when usage drops below 80%.

**Cooldown state:** Store last-notified timestamp alongside the alert in `/var/lib/ds01/alerts/${user}.json`. The `add_alert()` function already has `updated_at` and `created_at` fields — add `last_notified_at` field.

```bash
# In resource-alert-checker.sh: after add_alert(), deliver to terminal
deliver_alert_to_terminal() {
    local username="$1"
    local alert_type="$2"
    local message_body="$3"

    local COOLDOWN_HOURS=4
    local alerts_file="$ALERTS_DIR/${username}.json"

    # Check cooldown: has this type been notified recently?
    local last_notified
    last_notified=$(python3 -c "
import json, datetime, sys
try:
    alerts = json.load(open('$alerts_file'))
    for a in alerts:
        if a['type'] == '$alert_type':
            print(a.get('last_notified_at', ''))
            sys.exit(0)
    print('')
except: print('')
" 2>/dev/null)

    if [ -n "$last_notified" ]; then
        local now_epoch; now_epoch=$(date +%s)
        local notified_epoch; notified_epoch=$(date -d "$last_notified" +%s 2>/dev/null || echo "0")
        local elapsed=$(( (now_epoch - notified_epoch) / 3600 ))
        if [ "$elapsed" -lt "$COOLDOWN_HOURS" ]; then
            return 0  # Within cooldown — skip terminal delivery
        fi
    fi

    local severity="WARNING"
    [[ "$alert_type" == *"reached"* ]] && severity="ALERT"

    local msg
    msg=$(ds01_format_message "$severity" "RESOURCE QUOTA ALERT" "$message_body" "$username")

    # Try terminal delivery (no container context for quota alerts)
    ds01_notify "$username" "" "$msg"

    # Update last_notified_at in alerts file
    python3 -c "
import json, datetime
ts = datetime.datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
with open('$alerts_file') as f:
    alerts = json.load(f)
for a in alerts:
    if a['type'] == '$alert_type':
        a['last_notified_at'] = ts
with open('$alerts_file', 'w') as f:
    json.dump(alerts, f, indent=2)
" 2>/dev/null || true
}
```

### Pattern 4: Login Greeting — Pending Alerts Section

**What:** The existing `ds01-quota-greeting.sh` shows the banner and quota bars. Add a section after the quota bars that reads `/var/lib/ds01/alerts/${USER}.json` and prints any pending alerts.

**Display style:** Compact inline — show alert count and types if any, full detail if 1-2 alerts, summary if more. Keeps login fast.

```bash
# In ds01-quota-greeting.sh, after existing quota display:

_alerts_file="/var/lib/ds01/alerts/${_username}.json"
if [ -f "$_alerts_file" ]; then
    _alert_count=$(python3 -c "import json; print(len(json.load(open('$_alerts_file'))))" 2>/dev/null || echo "0")
    if [ "$_alert_count" -gt 0 ]; then
        echo -e " ${_B}${_RED}Pending alerts ($_alert_count):${_NC}"
        python3 -c "
import json
alerts = json.load(open('$_alerts_file'))
for a in alerts:
    print(f'  ! {a[\"message\"]}')
" 2>/dev/null
        echo ""
    fi
fi
```

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Quota data for summary | Custom YAML parser | `get_resource_limits.py` (already exists) |
| Current GPU usage | Docker label parsing | `gpu_allocator_v2.py status` (already exists) |
| Duration parsing | Custom regex in bash | `ds01_parse_duration` from `init.sh` / `ds01_core.py` |
| Alert persistence | Custom file format | Existing JSON alert files in `/var/lib/ds01/alerts/` |
| Colour codes | Hardcoded escape strings | `init.sh` exports `$RED`, `$YELLOW`, `$NC` etc. |

**Key insight:** Nearly all infrastructure already exists. The work is wiring, not building.

---

## Common Pitfalls

### Pitfall 1: PTY Write Failure Causes Silent Non-Delivery

**What goes wrong:** `echo "$message" > "/dev/$tty"` silently fails if the TTY is owned by a different user or has been deallocated between the `who` query and the write.

**Why it happens:** `who` output can be stale (microseconds). The TTY ownership check happens at open(), not at the `who` call.

**How to avoid:** Use `2>/dev/null` on the write (already done in both existing `notify_user()` implementations). Mark `sent=true` only after a successful write. The existing pattern is correct — preserve it in the library.

**Warning signs:** `notify_user()` logs "User has no active terminals" even when the user is logged in. Check for permission issues on `/dev/pts/N`.

### Pitfall 2: Container File Fallback Race — Container Not Running

**What goes wrong:** `docker exec` fails if the container stops between the check and the exec.

**Why it happens:** Race condition between lifecycle enforcement and notification.

**How to avoid:** Always use `2>/dev/null || true` on the `docker exec` call. The fallback is best-effort — if the container is gone, the user is likely seeing the stop message on their terminal anyway.

### Pitfall 3: Quota Summary Adds Latency to Every Notification

**What goes wrong:** Each `ds01_format_message()` call invokes `get_resource_limits.py` + potentially `gpu_allocator_v2.py` — Python startup overhead adds ~0.5s per notification. For rapid-fire notifications (multiple containers), this stacks.

**Why it happens:** Python interpreter startup cost on each subprocess call.

**How to avoid:** Cache quota summary in a variable at the start of each cron script run:
```bash
# Top of monitor_containers()
CACHED_QUOTA_SUMMARIES=()  # associative array keyed by username
```
Or: make `ds01_quota_summary()` accept an optional pre-fetched data argument so callers can pass cached data.

### Pitfall 4: Login Greeting Performance — Slow at Login

**What goes wrong:** Reading the alerts file + running Python at login adds latency. If Python takes 1-2 seconds, the login experience is noticeably worse.

**Why it happens:** profile.d scripts run synchronously at login. Every Python call has interpreter startup overhead.

**How to avoid:** Keep the alerts check to a single Python call that reads the JSON file and prints results in one pass. Do NOT call `get_resource_limits.py` at login time solely for the alerts section — the JSON file already has the human-readable message. The current quota greeting already calls Python 3-4 times; don't add more.

### Pitfall 5: State File Not Initialised with WARNED_FINAL

**What goes wrong:** Adding `WARNED_FINAL` to the two-level escalation but not initialising it in the state file creation path leads to sourcing a state file without that variable — the comparison `[ "${WARNED_FINAL:-false}" != "true" ]` then always triggers the final warning on the first run.

**Why it happens:** The default value `:-false` correctly handles the missing variable case — so actually this is fine. But the `sed -i` update pattern only works if the variable is in the file.

**How to avoid:** When creating a new state file, always include all tracked variables:
```bash
echo "LAST_ACTIVITY=$start_epoch" > "$state_file"
echo "LAST_CPU=0.0" >> "$state_file"
echo "WARNED=false" >> "$state_file"
echo "WARNED_FINAL=false" >> "$state_file"    # NEW
echo "IDLE_STREAK=0" >> "$state_file"
```
And for existing state files (the `:- ` default catches them at runtime, but `sed -i` won't find the line to update). Guard with:
```bash
grep -q "^WARNED_FINAL=" "$state_file" || echo "WARNED_FINAL=false" >> "$state_file"
```

### Pitfall 6: resource-alert-checker.sh User Discovery Misses Users Without Running Containers

**What goes wrong:** The current `get_ds01_users()` function only finds users with *running* containers (`docker ps -a --filter "label=ds01.managed=true"`). Users who have hit a quota but all containers are stopped won't be checked.

**Why it happens:** Quota alerts for container count can be hit even with stopped containers, and GPU quota can be at limit with held allocations.

**How to avoid:** For Phase 8, this is acceptable scope — quota alerts fire while containers are running (the primary scenario). Document this limitation. A comprehensive fix would iterate `/var/lib/ds01/alerts/` for existing alert files too, but that's scope creep.

---

## Code Examples

### Existing notify_user() pattern (from both scripts — identical)

```bash
# Source: check-idle-containers.sh lines 348-359 and enforce-max-runtime.sh lines 41-52
notify_user() {
    local username="$1"
    local message="$2"
    local sent=false
    while IFS= read -r tty; do
        [ -z "$tty" ] && continue
        echo "$message" > "/dev/$tty" 2>/dev/null && sent=true
    done < <(who | awk -v user="$username" '$1 == user {print $2}')
    if [ "$sent" = false ]; then
        log "User $username has no active terminals — notification not delivered"
    fi
}
```

**This is the canonical implementation.** Extract verbatim to `ds01_notify.sh` with minor additions.

### Existing message format (bordered box — reference style)

```bash
# Source: check-idle-containers.sh send_warning() lines 395-418
local message="━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
IDLE CONTAINER WARNING

Container: $container
Status: IDLE (no activity detected)
Action: Will auto-stop in ~${minutes_until_stop} minutes

This container will be automatically stopped...
Your work in /workspace is safe and will persist.

To keep your container running:
  1. Run any command in the container
  2. Or restart your training/script

To stop and retire now (frees GPU immediately):
  container-retire $(echo $container | cut -d'.' -f1)

Questions? Run 'check-limits' or contact admin.
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
```

**Template** `ds01_format_message()` must match this style. The severity/title header replaces "IDLE CONTAINER WARNING". The quota summary block is appended before the final `━━━` line.

### Existing quota alert JSON format (resource-alert-checker.sh)

```json
[
  {
    "type": "gpu_usage_high",
    "message": "GPU usage high: 2/3 GPUs (80%)",
    "created_at": "2026-02-17T10:00:00Z",
    "updated_at": "2026-02-17T10:00:00Z"
  }
]
```

Alert types: `gpu_usage_high`, `gpu_limit_reached`, `container_usage_high`, `container_limit_reached`.

**Memory alerts are not yet implemented** in resource-alert-checker.sh — Phase 8 needs to add `check_memory_alerts()` following the same pattern as `check_gpu_alerts()`. Memory data comes from `get_resource_limits.py <user> --aggregate` (returns JSON with `memory_max`), and current usage from `systemctl show ds01-{group}-{user}.slice --property=MemoryCurrent`.

### Cron schedule context (from ds01-maintenance)

```
Current lifecycle flow:
  :05 - cleanup-stale-gpu-allocations.sh
  :10 - [NEW] resource-alert-checker.sh (quota alerts — Phase 8)
  :20 - check-idle-containers.sh (idle detection)
  :35 - enforce-max-runtime.sh (runtime enforcement)
  :50 - cleanup-stale-containers.sh
```

The decision was `:10` for quota alerts. This is the right slot — runs after GPU cleanup has freed any released allocations, before idle detection fires.

### get_resource_limits.py flags for quota summary

```bash
# Current GPU limit
python3 "$RESOURCE_PARSER" "$username" --max-gpus        # e.g., "3" or "unlimited"
# Max containers
python3 "$RESOURCE_PARSER" "$username" --max-containers  # e.g., "3"
# Aggregate JSON (has memory_max, cpu_quota)
python3 "$RESOURCE_PARSER" "$username" --aggregate       # JSON or "null"
# Group
python3 "$RESOURCE_PARSER" "$username" --group           # e.g., "student"
```

---

## State of the Art

| Old Approach | Current Approach | Impact |
|--------------|-----------------|--------|
| Single warning at 80%/90% | Two-level escalation (80%+95% idle / 75%+90% runtime) | Users get an early heads-up, then a final urgent warning |
| Quota alerts file-only | File + terminal delivery with cooldown | Users see quota alerts in their terminal, not just at login |
| `notify_user()` duplicated in 2 scripts | Extracted to `ds01_notify.sh` | Single source of truth for all notification delivery |
| No container file fallback | `/workspace/.ds01-alerts` fallback | Users with no open terminal still receive alerts |
| Login greeting: quota bars only | Quota bars + pending alerts summary | Login immediately shows any active quota issues |

---

## Open Questions

1. **Memory quota: current usage via systemd slice**
   - What we know: `memory_max` is in the aggregate JSON from `get_resource_limits.py`. Systemd tracks `MemoryCurrent` per slice.
   - What's unclear: The slice name format for a user is `ds01-{group}-{sanitized_username}.slice`. The sanitisation is in `username_utils.py`. Need to confirm this works for all username formats (e.g., email-based usernames like `204214@hertie-school.lan`).
   - Recommendation: Use `python3 scripts/lib/username_utils.py <username>` to get the sanitised name, or call `get_resource_limits.py <username> --aggregate` which already knows the slice name.

2. **Container file fallback: which container to use?**
   - What we know: Quota alerts iterate all users, not specific containers. There may be multiple containers per user.
   - What's unclear: Which container should receive the fallback file write? Write to all? Write to most recently started?
   - Recommendation: For quota alerts, skip the container fallback entirely — quota alerts are user-level, not container-level. The `/workspace` fallback makes sense for idle/runtime warnings (where the container is known). Document this distinction.

3. **Severity label names**
   - Recommendation: Use `WARNING` (approaching limit, recoverable), `ALERT` (at limit/blocked), `STOPPED` (container just stopped), `NOTICE` (informational/exempt).
   - This aligns with syslog severity conventions and is self-explanatory without documentation.

---

## Sources

### Primary (HIGH confidence — direct codebase inspection)

- `/opt/ds01-infra/scripts/monitoring/check-idle-containers.sh` — `notify_user()`, `send_warning()`, state file pattern, WARNED flag
- `/opt/ds01-infra/scripts/maintenance/enforce-max-runtime.sh` — `notify_user()` duplicate, warning at 90%, state file pattern
- `/opt/ds01-infra/scripts/monitoring/resource-alert-checker.sh` — `add_alert()`, `clear_alert()`, alert JSON format, `check_gpu_alerts()`, `check_container_alerts()`, `get_ds01_users()`
- `/opt/ds01-infra/config/deploy/profile.d/ds01-quota-greeting.sh` — login greeting structure, quota display, Python calls at login
- `/opt/ds01-infra/config/deploy/cron.d/ds01-maintenance` — cron schedule, existing slots (:05, :20, :35, :50)
- `/opt/ds01-infra/scripts/lib/init.sh` — library source pattern, `ds01_draw_header()`, colour exports
- `/opt/ds01-infra/scripts/lib/ds01_core.py` — `parse_duration()`, `format_duration()`, `Colors`
- `/opt/ds01-infra/config/runtime/resource-limits.yaml` — group definitions, `policies`, `container_types`, resource limits

---

## Metadata

**Confidence breakdown:**
- Existing code (notify_user, alert format): HIGH — read directly from source
- Architecture (lib extraction): HIGH — pattern established by init.sh, ds01_events.sh
- Escalation thresholds: MEDIUM — reasonable defaults recommended, no strong technical constraint
- Memory quota implementation: MEDIUM — systemd slice mechanism confirmed, username sanitisation for slice names needs verification during planning
- Quota alert cooldown (4h): MEDIUM — judgement call, no technical constraint

**Research date:** 2026-02-17
**Valid until:** Stable (no external dependencies — internal codebase only)
