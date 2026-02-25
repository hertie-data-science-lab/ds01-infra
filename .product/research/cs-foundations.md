# Computer Science Foundations

Core CS concepts and Linux primitives that underpin DS01's implementation. Understanding these explains *why* certain design choices were made.

## Cgroups v2 (Unified Hierarchy)

**What it is:** Linux kernel mechanism for grouping processes and applying resource limits. Cgroups v2 (unified hierarchy) replaced v1's per-controller hierarchy with a single tree.

**Controllers used by DS01:**
- **cpu:** `CPUQuota=9600%` means 96 CPU-seconds per second (32 CPUs × 3 containers). Enforced by kernel scheduler.
- **memory:** `MemoryMax=96G` hard limit (OOM-kill). `MemoryHigh=86G` soft limit (throttle). Two-tier prevents sudden kills.
- **pids:** `TasksMax=12288` prevents fork bombs. Set to `pids_limit × max_containers_per_user`.
- **io:** Available but deferred (requires BFQ scheduler, DS01 currently uses mq-deadline).

**DS01's cgroup hierarchy:**
```
ds01.slice
├── ds01-student.slice
│   └── ds01-student-alice.slice     ← per-user aggregate limits
│       └── docker-abc123.scope      ← per-container limits (Docker-managed)
├── ds01-researcher.slice
│   └── ds01-researcher-carol.slice
└── ds01-admin.slice
```

**Why systemd slices:** Systemd natively manages the cgroup tree. Using systemd slices (via `--cgroup-parent`) gives automatic cleanup, `systemctl` visibility, and drop-in configuration without custom cgroup scripting.

**v1 vs v2 detection:** DS01 checks for `/sys/fs/cgroup/ds01.slice/` (v2) or `/sys/fs/cgroup/memory/` (v1) at runtime. Memory metrics differ: `memory.current` (v2) vs `memory.usage_in_bytes` (v1). Server has been migrated to pure v2 mode.

## File Locking (fcntl)

**Problem:** Multiple processes (Docker wrapper, cron jobs, allocator) may try to allocate GPUs simultaneously.

**Solution:** Exclusive file locks via `fcntl.flock(fd, LOCK_EX)`.

**DS01's locking pattern:**
```python
signal.signal(signal.SIGALRM, timeout_handler)
signal.alarm(5)  # 5-second deadline
try:
    fcntl.flock(fd, LOCK_EX)
    signal.alarm(0)  # Cancel alarm
    # Critical section: allocate GPU
finally:
    fcntl.flock(fd, LOCK_UN)
```

**Why 5-second timeout:** Prevents indefinite hangs if a process crashes while holding the lock. The SIGALRM approach is simpler than threading-based timeouts and works in signal-safe contexts.

**Fail-open on timeout:** If the lock can't be acquired within 5 seconds, the operation proceeds without the lock (with a warning log). Rationale: a stuck lockfile shouldn't block all GPU allocations on the server.

## Atomic Operations

**PIPE_BUF guarantee:** POSIX guarantees that writes ≤ `PIPE_BUF` bytes (4,096 on Linux) to a pipe or file are atomic — they won't interleave with other writes. DS01's event logging exploits this:
- Each JSONL event is capped at 4KB.
- Single `write()` syscall guarantees no partial events in the log.
- Events exceeding 4KB are truncated (with a `.truncated` flag) rather than split.

**Temp-file-then-rename pattern:** For JSON state files (gpu-state.json, container-owners.json):
1. Write to `target.tmp.$$` (process-specific temp file).
2. `mv target.tmp.$$ target` (atomic rename on same filesystem).
3. Readers see either the old file or the new file, never a partial write.

**Why this matters:** Without atomic writes, a crash mid-write could leave `gpu-state.json` as invalid JSON, corrupting GPU allocation state.

## Fail-Open Design

**Principle:** Infrastructure errors should degrade service gracefully, not block user operations entirely.

**Origin:** Distributed systems philosophy — in a system where availability matters more than strict consistency, errors should fail toward "allow" rather than "deny".

**DS01 application:**
- **Lock timeout:** Allow GPU allocation without lock (risk: rare double-allocation, detectable by periodic sync).
- **Config read failure:** Use safe defaults (risk: wrong group limits, corrected on next successful read).
- **Event log failure:** Skip logging (risk: missing audit entry, non-critical).
- **Ownership detection failure:** Mark as "unknown", allow operation (risk: unattributed container, visible in dashboard).

**Contrast with fail-closed:** Banking systems fail-closed (deny transaction on error). DS01 fails-open because a blocked user is worse than a temporarily untracked container.

## Event Sourcing (JSONL)

**Pattern:** Append-only log of events as the system's audit trail. Each event is a self-contained JSON object on a single line.

**DS01's event format:**
```json
{"timestamp":"2026-01-30T14:30:00Z","event_type":"container.create","user":"alice","source":"docker-wrapper","details":{"container":"proj","image":"pytorch:latest"},"schema_version":"1"}
```

**Properties:**
- **Append-only:** Events are never modified or deleted (logrotate handles archival).
- **Queryable:** Standard JSONL format — `jq`, `awk`, `grep` all work. DS01 provides `ds01-events` CLI.
- **Schema-versioned:** `schema_version` field enables format evolution without breaking consumers.
- **Non-blocking:** Event emission never raises exceptions; returns `False` on failure.

**Logrotate integration:** `copytruncate` strategy preserves open file descriptors (scripts keep writing to the same fd after rotation).

## Systemd Integration

**Slices:** Hierarchical resource groups. DS01 uses `ds01.slice` → `ds01-{group}.slice` → `ds01-{group}-{user}.slice` for three-level resource containment.

**Drop-in files:** `/etc/systemd/system/{unit}.d/10-resource-limits.conf` extends unit configuration without modifying the base unit. DS01 generates drop-ins per user with resource limit overrides.

**Services:** `ds01-container-owner-tracker.service` runs the ownership daemon with `Restart=on-failure` and 5-second restart delay. Systemd handles process lifecycle automatically.

**Timers:** Alternative to cron with better dependency management and journald integration. DS01 currently uses cron but plans migration to systemd timers in M3.
