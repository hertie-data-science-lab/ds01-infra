# ADR-002: Awareness-First Architecture

**Status:** Accepted
**Date:** 2026-01-30

## Context

DS01 initially had partial visibility — it could only see containers created through its own commands. Containers from docker-compose, VS Code dev containers, and raw `docker run` were invisible. Host GPU processes (bare Python CUDA scripts) were completely untracked.

This blind spot meant the GPU allocation model was unreliable: DS01 might allocate a GPU that was already in use by an unmanaged container.

## Decision

Build comprehensive detection first, enforce second. The milestone order follows:
1. **See everything** (detection, tracking, inventory)
2. **Control everything** (enforcement, quotas, lifecycle)
3. **Observe everything** (dashboards, analytics, alerts)

## Rationale

You can't enforce what you can't see. If DS01 allocates a GPU without knowing that a docker-compose service is already using it, the allocation is wrong. Detection must come before enforcement to establish an accurate picture of system state.

## Alternatives Considered

- **Enforce-first:** Block all non-DS01 container creation immediately. Rejected — would break existing workflows and alienate users before the system proved its value.
- **Parallel build:** Develop detection and enforcement simultaneously. Rejected — enforcement without accurate detection creates false positives (blocking legitimate work) and false negatives (missing unmanaged containers).

## Consequences

- **Positive:** System builds trust by showing accurate visibility before imposing restrictions. Users see the value (dashboard, quotas) before feeling the constraints (enforcement).
- **Negative:** During the detection-only phase, unmanaged containers could consume resources without limits. Accepted as temporary — enforcement phases follow immediately.
