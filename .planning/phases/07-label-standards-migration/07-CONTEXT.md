# Phase 7: Label Standards & Migration - Context

**Gathered:** 2026-02-16
**Status:** Ready for planning

<domain>
## Phase Boundary

Standardise all container labels from mixed `aime.mlc.*` and `ds01.*` namespaces to a consistent `ds01.*` namespace. Patch mlc-patched.py to write ds01.* labels. Migrate all script references. Maintain a lightweight fallback for existing containers until they naturally cycle out.

</domain>

<decisions>
## Implementation Decisions

### AIME upstream boundary
- Patch mlc-patched.py to write `ds01.*` labels instead of `aime.mlc.*`
- Remove `aime.mlc.*` label writing from mlc-patched.py entirely (clean break, not dual-write)
- Accept the upstream divergence — label changes are small, easy to maintain across upstream syncs
- Upstream AIME tracking continues (occasional sync), but this is an accepted divergence point

### Label naming convention
- Keep current mixed convention: dots for hierarchy (`ds01.gpu.uuid`), underscores in leaf names (`created_at`, `container_type`)
- All lowercase values — `ds01.user`, not `ds01.USER`
- Formal schema document listing all valid `ds01.*` labels with types and descriptions (single source of truth for the namespace)

### Type label consolidation
- Claude's discretion: assess what `aime.mlc.TYPE` provides vs existing `ds01.container_type` and `ds01.interface`, consolidate as appropriate

### Migration strategy
- Natural turnover for existing containers — don't restart or relabel running containers
- All ~20+ scripts with `aime.mlc.*` references migrated to `ds01.*` in one sweep (complete migration, not partial)
- mlc-patched.py updated as the root fix — new containers get `ds01.*` labels from creation
- Lightweight ownership fallback: shared library function checks `ds01.user` first, falls back to `aime.mlc.USER`
- Fallback lives in shared library (docker-utils.sh / ds01_core.py) — single place to remove later

### Backward compatibility
- Fallback function is the only backward compatibility mechanism (no dual-write, no state files)
- Remove fallback when no `aime.mlc.*` containers remain (`docker ps --filter label=aime.mlc.USER` returns nothing)
- TODO comment in code marks the fallback for future removal — manual check, no automation needed
- No sunset date — removal triggered by container lifecycle, not calendar

</decisions>

<specifics>
## Specific Ideas

- Schema document should be a reference for the ds01.* label namespace — what each label means, who sets it, valid values
- The shared library fallback pattern already exists in some scripts (check-idle-containers.sh does ds01.user then aime.mlc.USER) — consolidate into one function

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 07-label-standards-migration*
*Context gathered: 2026-02-16*
