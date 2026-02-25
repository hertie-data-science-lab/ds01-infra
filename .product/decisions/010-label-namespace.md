# ADR-010: ds01.* Label Namespace Migration

**Status:** Accepted
**Date:** 2026-02-16

## Context

DS01 inherited AIME's label convention (`aime.mlc.*` labels like `aime.mlc.USER`, `aime.mlc.DS01_FRAMEWORK`). As DS01 grew beyond AIME's scope, the label namespace became confusing — DS01-specific metadata was stored under AIME's namespace, and the mix of uppercase/lowercase was inconsistent with Docker conventions.

## Decision

Migrate to a `ds01.*` label namespace with lowercase names:
- `ds01.user` (replaces `aime.mlc.USER`)
- `ds01.managed` (replaces `aime.mlc.DS01_MANAGED`)
- `ds01.framework` (replaces `aime.mlc.DS01_FRAMEWORK`)
- `ds01.gpu.uuids`, `ds01.gpu.slots`, `ds01.interface`, `ds01.slice`, etc.

All consumer scripts (monitoring, maintenance, admin, Docker wrapper) updated to read `ds01.*` labels first, with fallback to `aime.mlc.*` for backward compatibility.

An authoritative label schema is maintained in `config/label-schema.yaml` (machine-readable, version-controlled).

## Rationale

DS01 needs its own identity separate from AIME. Lowercase label names follow Docker ecosystem conventions. A machine-readable schema document serves as the single source of truth for label definitions.

## Alternatives Considered

- **Keep aime.mlc.* labels:** No migration effort, but increasingly confusing as DS01 diverges from AIME. New labels (gpu.slots, interface) don't fit the aime.mlc.* namespace.
- **Hard cutover (no backward compatibility):** Simpler code but would break all existing containers. Unacceptable with live users.
- **Dual-write (write both namespaces):** Considered but rejected as unnecessary complexity. Write new labels only; read both with fallback.

## Consequences

- **Positive:** Clean namespace. Schema document enables tooling and validation. Consistent with Docker conventions.
- **Negative:** Fallback chain in Python ownership scripts adds complexity. Will need eventual cleanup pass to remove `aime.mlc.*` fallbacks.
- **Migration path:** Existing containers continue working via fallback reads. New containers get `ds01.*` labels only. No manual relabelling required.
