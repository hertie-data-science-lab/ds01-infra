# Phase 9: Command Bug Fixes - Context

**Gathered:** 2026-02-17
**Status:** Ready for planning

<domain>
## Phase Boundary

Fix 4 known bugs in user-facing CLI tools: container-stats, image-create, image-update, and user-setup. Scope includes bug fixes, local refactoring where needed, and one UX enhancement (user-setup image awareness). No new commands or capabilities.

</domain>

<decisions>
## Implementation Decisions

### Fix scope
- Claude decides per-bug: surgical fix where code is clean, broader cleanup where it's needed
- Refactoring is permitted if the bug fix reveals tangled code (especially image-create at ~1800 lines)
- Error handling improvements allowed in affected functions at Claude's discretion
- All fixes must be validated with live verification (actually run the commands against Docker)

### container-stats --filter (FIX-01)
- Bug: `-*)` catch-all at line 330 rejects `--filter` and any unknown flag
- Fix: stop crashing on unknown flags — let docker handle errors for flags the script doesn't recognise
- Accept container names as positional arguments (e.g., `container-stats my-container`)
- Default behaviour should be one-shot (show stats once and exit), use `--watch` for streaming
- Note: script already accepts one positional arg as CONTAINER_NAME (line 336) — verify this works

### image-create code quality (FIX-02)
- Original bug: "creation: command not found" at line 1244 (line numbers shifted since report)
- Confirmed issues: operator precedence bug at line 1364 (`&&`/`||` without grouping), unquoted variable in heredoc at line 1376
- File passes `bash -n` — original error may be input-dependent or stale
- Fix the confirmed code quality issues; runtime test to check if original error is reproducible

### image-update rebuild flow (FIX-03)
- Bug: double rebuild prompt — user answers "Rebuild now?" inside interactive_mode, then asked again at line 1829
- Affects 4 of 7 code paths (options 2, 3, 4, 5 all trigger double prompt)
- Fix: show diff of changes, then ask for rebuild confirmation ONCE
- On build failure: offer to revert Dockerfile changes (keep backup before rebuild)
- Show full docker build output (not quiet/spinner)
- Add $EDITOR option to interactive mode menu (open Dockerfile directly)

### user-setup image awareness (FIX-04)
- Not a bug — image detection works correctly (tested live, grep pattern matches)
- Enhancement: when existing images detected, list them by name (not just count)
- Offer to skip image creation if user already has images they need
- Continue rest of onboarding regardless (SSH, workspace, project init still run)
- Only detect ds01-{UID}/ images — ignore manually built images

### Claude's Discretion
- Exact refactoring scope per script (how far beyond the bug to clean up)
- Whether to restructure image-create's indentation issues (lines 1242-1333)
- Error message wording and formatting
- How to implement the Dockerfile backup/revert mechanism in image-update

</decisions>

<specifics>
## Specific Ideas

- container-stats should feel like a quick glance at resource usage — one-shot by default, not a streaming dashboard
- image-update rebuild should flow naturally: modify -> see diff -> confirm once -> build with visible output -> revert on failure
- user-setup should acknowledge returning users who already have images, not treat everyone as brand new

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 09-command-bug-fixes*
*Context gathered: 2026-02-17*
