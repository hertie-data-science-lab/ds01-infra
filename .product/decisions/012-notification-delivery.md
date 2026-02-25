# ADR-012: TTY + Container File Notification Delivery

**Status:** Accepted
**Date:** 2026-02-17

## Context

DS01 needs to warn users when their containers approach idle timeout, runtime limits, or quota exhaustion. Notifications must reach users who may be:
- Actively working in a terminal (SSH session).
- Away from their terminal (container running unattended).
- Logged in across multiple sessions.

## Decision

Two-tier delivery mechanism:

1. **Primary — TTY delivery:** Discover user's active terminals via `who` command. Write notification directly to each `/dev/pts/*` terminal. Immediate, visible, and non-intrusive (appears in terminal output).

2. **Fallback — Container file:** If user has no active terminals, append the notification to `/workspace/.ds01-alerts` inside the affected container (via `docker exec`). User sees alerts when they next connect.

Notifications use boxed formatting for visibility. Quota summary (GPUs, memory, containers) is cached per notification run to avoid repeated Python overhead.

Two-level escalation pattern:
- Idle timeout: first warning at 80%, final warning at 95%.
- Max runtime: first warning at 75%, final warning at 90%.

## Rationale

TTY delivery is the fastest way to reach an active user — no application dependencies, no email setup, works over any SSH connection. The container file fallback ensures notifications aren't lost when users are disconnected.

## Alternatives Considered

- **Email:** Requires SMTP credentials (blocked on IT). Adds latency. Users may not check email during compute sessions.
- **Slack/Teams webhook:** Requires external service setup. Not all users monitor chat during research.
- **File in home directory:** Would persist across containers but clutters home. Container-scoped files are cleaner.
- **Docker events:** Only admin-visible. Users can't subscribe to Docker events for their containers.

## Consequences

- **Positive:** Immediate delivery to active sessions. Persistent fallback for disconnected users. No external dependencies.
- **Negative:** TTY messages can interrupt terminal output (brief visual disruption). Container file requires user to check `.ds01-alerts` manually.
- **Best-effort:** Notification delivery never blocks enforcement actions. If delivery fails, the enforcement (stop/cleanup) proceeds regardless.
