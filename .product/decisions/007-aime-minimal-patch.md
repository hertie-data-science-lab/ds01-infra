# ADR-007: Minimal AIME Patch Strategy

**Status:** Accepted
**Date:** 2026-01-30

## Context

DS01 is built on AIME ML Containers, which provides framework-versioned Docker images and container management via `mlc.py` (2,400 lines). DS01 needs custom image support (AIME only allows catalog images) and DS01-specific labels on containers.

## Decision

Patch `mlc.py` minimally (52 lines changed, 2.2% of the file) rather than rewriting or wrapping the entire tool:
- Add `--image` flag to bypass AIME's catalog lookup.
- Add custom image validation (verify image exists locally).
- Add `ds01.*` label injection.
- Preserve 97.8% of AIME's logic (user creation, volume mounting, GPU detection, networking).

Of AIME's 9 MLC commands, DS01 wraps 2 (`mlc-create`, `mlc-stats`), calls 1 directly (`mlc-open`), and replaces the rest with custom implementations.

## Rationale

`mlc.py` handles complex tasks well: user creation, workspace mounting, GPU device mapping, container naming, and framework-specific configuration. Rewriting these would duplicate effort and lose AIME's tested edge-case handling. A minimal patch preserves upgradeability — when AIME releases new versions, the diff is small enough to rebase.

## Alternatives Considered

- **Full wrapper around mlc.py:** Would need to replicate user creation, volume mounting, and GPU detection logic. Higher maintenance burden.
- **Fork AIME entirely:** Maximum flexibility but permanently diverges. Loses ability to pull upstream improvements.
- **Replace AIME completely:** Would require reimplementing 2,400 lines of container management. No justification for the effort when 97.8% works correctly.

## Consequences

- **Positive:** Minimal maintenance burden. Easy to upgrade when AIME releases new versions. Preserves AIME's tested container management logic.
- **Negative:** DS01 depends on AIME's internal structure. If AIME significantly refactors `mlc.py`, the patch may need updating.
- **Accepted risk:** AIME releases are infrequent, and the patch is small enough to port quickly.
