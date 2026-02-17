# Phase 9: Command Bug Fixes - Research

**Researched:** 2026-02-17
**Domain:** Bash scripting — user-facing CLI tools (container-stats, image-create, image-update, user-setup)
**Confidence:** HIGH — all findings from direct code inspection of the live source files

---

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

#### Fix scope
- Claude decides per-bug: surgical fix where code is clean, broader cleanup where needed
- Refactoring permitted if bug fix reveals tangled code (especially image-create at ~1800 lines)
- Error handling improvements allowed in affected functions at Claude's discretion
- All fixes must be validated with live verification (actually run the commands against Docker)

#### container-stats --filter (FIX-01)
- Bug: `-*)` catch-all at line 330 rejects `--filter` and any unknown flag
- Fix: stop crashing on unknown flags — let docker handle errors for flags the script doesn't recognise
- Accept container names as positional arguments (e.g., `container-stats my-container`)
- Default behaviour should be one-shot (show stats once and exit), use `--watch` for streaming
- Note: script already accepts one positional arg as CONTAINER_NAME (line 336) — verify this works

#### image-create code quality (FIX-02)
- Original bug: "creation: command not found" at line 1244 (line numbers shifted since report)
- Confirmed issues: operator precedence bug at line 1364, unquoted variable in heredoc at line 1376
- File passes `bash -n` — original error may be input-dependent or stale
- Fix the confirmed code quality issues; runtime test to check if original error is reproducible

#### image-update rebuild flow (FIX-03)
- Bug: double rebuild prompt — user answers "Rebuild now?" inside interactive_mode, then asked again at line 1829
- Affects 4 of 7 code paths (options 2, 3, 4, 5 all trigger double prompt)
- Fix: show diff of changes, then ask for rebuild confirmation ONCE
- On build failure: offer to revert Dockerfile changes (keep backup before rebuild)
- Show full docker build output (not quiet/spinner)
- Add $EDITOR option to interactive mode menu (open Dockerfile directly)

#### user-setup image awareness (FIX-04)
- Not a bug — image detection works correctly
- Enhancement: when existing images detected, list them by name (not just count)
- Offer to skip image creation if user already has images they need
- Continue rest of onboarding regardless (SSH, workspace, project init still run)
- Only detect ds01-{UID}/ images — ignore manually built images

### Claude's Discretion
- Exact refactoring scope per script (how far beyond the bug to clean up)
- Whether to restructure image-create's indentation issues (lines 1242-1333)
- Error message wording and formatting
- How to implement the Dockerfile backup/revert mechanism in image-update

### Deferred Ideas (OUT OF SCOPE)
None — discussion stayed within phase scope
</user_constraints>

---

## Summary

This phase fixes 4 independent bugs/enhancements across 4 user-facing shell scripts. All scripts are pure Bash with no external framework dependencies. The fixes are self-contained within each file; no shared library changes are needed.

All four scripts pass `bash -n` syntax check. The bugs are logic-level (wrong flag handling, operator precedence, UX flow) rather than parse-level errors. Each fix is bounded and well-understood from code inspection.

**Primary recommendation:** Fix each bug in isolation with a dedicated plan. Test against live Docker on the server. The only script warranting broader cleanup discussion is image-create (1869 lines), but the specific bugs are small and surgical.

---

## Standard Stack

### Core
| Tool | Version | Purpose | Notes |
|------|---------|---------|-------|
| Bash | 5.x (Ubuntu) | Script language | All scripts are `#!/bin/bash` |
| Docker CLI | Current | Container/image operations | `docker stats`, `docker images`, `docker build` |
| `diff` | GNU | Show Dockerfile changes | Built-in, available for FIX-03 |
| `sed`, `awk` | GNU | Dockerfile text manipulation | Already used heavily in image-update |

### Supporting
| Tool | Purpose | When to Use |
|------|---------|-------------|
| `nvidia-smi` | GPU stats | container-stats `--gpu` flag |
| `bc` | Arithmetic comparisons | Already used in container-stats |
| `$EDITOR` / `find_editor()` | Dockerfile editing | image-update already has `find_editor()` |

No new dependencies needed. All tools already in use.

---

## Architecture Patterns

### Script Locations

```
/opt/ds01-infra/scripts/user/
├── atomic/
│   ├── container-stats      (356 lines)  — FIX-01
│   ├── image-create         (1869 lines) — FIX-02
│   └── image-update         (2040 lines) — FIX-03
└── wizards/
    └── user-setup           (478 lines)  — FIX-04
```

Installed symlinks at `/usr/local/bin/{container-stats,image-create,image-update,user-setup}`.

### Pattern: Flag Handling in These Scripts

All scripts use a `while [[ $# -gt 0 ]]; do case $1 in` loop. The catch-all `-*)` clause is the source of the FIX-01 bug. The correct pattern for "pass unknown flags through" is to collect them or silently ignore them, rather than erroring.

### Pattern: Heredoc Variable Expansion

image-create uses two heredoc styles:
- `<< DOCKERFILEEOF` — variables ARE expanded (shell substitutes `$project_name`, etc.)
- `<< 'DOCKERFILEEOF'` — variables are NOT expanded (literal `$` in Dockerfile)

Line 1364–1379 uses the unquoted form (`<< DOCKERFILEEOF`), so `$project_name` and `$framework` expand at heredoc-write time. This is correct for the `--display-name` line. The risk is if those variables are empty or contain spaces.

### Pattern: image-update's Dual-Return Architecture

`interactive_mode()` returns via two paths:
1. **User chooses "7) Continue to rebuild"** → `return 0` (line 1457)
2. **User says "Rebuild now? [Y/n]" Yes** → `return 0` (lines 1306, 1344, 1375, 1421)
3. **User cancels** → `exit 0` (line 1463)

The main script then unconditionally runs Phase 2: rebuild prompt (line 1817–1844). This means path 2 returns, then the main script asks again — the double prompt.

---

## FIX-01: container-stats --filter

### Root Cause (Confirmed)

**File:** `/opt/ds01-infra/scripts/user/atomic/container-stats`
**Lines:** 330–334

```bash
-*)
    echo -e "${RED}✗ Unknown option: $1${NC}\n"
    usage
    exit 1
    ;;
```

Any unrecognised flag (including `--filter`, `--format`, etc.) hits this catch-all, prints an error, and exits.

### What Already Works

- Line 336 already handles positional args: `if [ -z "$CONTAINER_NAME" ]; then CONTAINER_NAME="$1"; fi`
- The `show_gpu` variable is also already handled via `-g|--gpu`
- Default (no `--watch`) is already one-shot (lines 349–356)

### Fix Pattern

Replace the crash-and-exit with a pass-through. Two approaches:

**Option A: Silent pass-through (collect unknown flags for future use)**
```bash
-*)
    # Unknown flag — ignore and let docker handle it if applicable
    shift
    ;;
```

**Option B: Warn but continue (more user-friendly for typos)**
```bash
-*)
    echo -e "${YELLOW}⚠ Ignoring unknown option: $1${NC}" >&2
    shift
    ;;
```

The context decision says "let docker handle errors for flags the script doesn't recognise" — Option A (silent pass-through) is the right approach. Docker itself will error if the flag is invalid.

### Verification
```bash
container-stats --filter name=foo   # should not crash
container-stats my-container         # should filter to that container
container-stats                       # one-shot, exits after display
container-stats --watch               # streaming (2s refresh)
```

---

## FIX-02: image-create Code Quality

### Root Cause Analysis

**File:** `/opt/ds01-infra/scripts/user/atomic/image-create`

All three confirmed issues (original "command not found" + two code quality bugs):

#### Issue A: Operator Precedence Bug at Line 1364

```bash
if [ "$skip_base" != true ] && [ "$jupyter_choice" = "default" ] || [ "$jupyter_choice" = "custom" ]; then
```

**Problem:** Without grouping, `&&` binds tighter than `||`. This evaluates as:
```
([ "$skip_base" != true ] && [ "$jupyter_choice" = "default" ]) || [ "$jupyter_choice" = "custom" ]
```

**Intended:** The `|| custom` branch should also be gated by `skip_base != true`. As written, if `skip_base = true` but `jupyter_choice = custom`, the block executes (wrong). Fix:

```bash
if [ "$skip_base" != true ] && { [ "$jupyter_choice" = "default" ] || [ "$jupyter_choice" = "custom" ]; }; then
```

#### Issue B: Unquoted Variable in Heredoc at Line 1376

**File context:** Lines 1375–1377 (inside `<< DOCKERFILEEOF` heredoc, not `<< 'DOCKERFILEEOF'`):

```bash
RUN python -m ipykernel install --user \\
    --name=$project_name \\
    --display-name="$project_name ($framework)"
```

If `$project_name` contains spaces (e.g., `"my project"`), the Dockerfile gets:
```
RUN python -m ipykernel install --user \
    --name=my project \
    --display-name="my project (pytorch)"
```

The `--name=my project` line becomes invalid Dockerfile syntax (Docker parses it as two tokens). Fix: quote the value in the heredoc:

```bash
    --name="${project_name}" \\
    --display-name="${project_name} ($framework)"
```

Note: `$project_name` is derived from user input that's already sanitised (alphanumeric + dash) — but the fix is still correct practice and makes it safe for future changes.

#### Issue C: Original "creation: command not found" Error

This was reported at "line 1244" but the current file passes `bash -n` cleanly. The error message `creation: command not found` would occur if a line like `creation ...` appeared without being in a string — but no such pattern exists now. Most likely:
- Line numbers shifted after previous edits
- The error was triggered by a specific input path that is now fixed
- Or the error was in a heredoc that got evaluated by `set -e`

**Runtime test needed:** Run `image-create test-image` and step through the Jupyter phases to confirm no runtime error.

### Indentation in Lines 1242–1333

The context says Claude has discretion here. Lines 1242–1333 have a missing close brace for the `if [ -z "$requirements_file" ]; then` block (opened at 1242, the body is unindented). This is a readability issue, not a functional bug. **Recommendation: fix the indentation** while in the file since it's in the same logical block as the operator precedence bug.

---

## FIX-03: image-update Rebuild Flow

### Root Cause (Confirmed)

**Double prompt mechanism:**

1. User runs `image-update my-project` → enters `interactive_mode()`
2. User selects option 2/3/4/5 (modify Dockerfile)
3. After modification: prompt "Rebuild now? [Y/n]:" (e.g., line 1302)
4. User says Y → `return 0` from `interactive_mode()`
5. Main script continues to line 1803: "Phase 2/3: Rebuild Docker Image?"
6. Main script asks "Rebuild image now? [Y/n]:" again (line 1829) ← SECOND PROMPT

**4 of 7 menu options are affected:** options 2 (add pip), 3 (requirements.txt import), 4 (add system packages), 5 (remove packages).

Options 1 (list), 6 (edit in `$EDITOR`), 7 (continue to rebuild) are not affected.

### Fix Strategy

**Remove the "Rebuild now?" prompts from inside `interactive_mode()`**. Let the main flow handle all rebuild decisions. Instead, inside `interactive_mode()`:
- After modification: inform user changes were made, return from the `case` branch, continue the menu loop
- When user selects "7) Continue to rebuild": `return 0`

This way the rebuild question is asked exactly once, in the main script at Phase 2.

**Diff display before rebuild:** The main script already has `${DOCKERFILE}.bak` created in `add_python_packages()` and similar functions. Use `diff "${DOCKERFILE}.bak" "$DOCKERFILE"` before the rebuild prompt to show what changed.

**Backup/revert on build failure:** The `.bak` file already exists. On build failure (the `else` branch at line 2027), offer:
```bash
read -p "Restore Dockerfile backup? [Y/n]: " REVERT
if [[ "$REVERT" =~ ^[Yy]$ ]]; then
    mv "${DOCKERFILE}.bak" "$DOCKERFILE"
    echo "Dockerfile restored."
fi
```

Currently the failure branch only shows troubleshooting tips.

**$EDITOR in menu:** `find_editor()` already exists (lines 258–269 in image-update). Menu option 6 already opens `$EDITOR`. The context says "Add $EDITOR option to interactive mode menu" — this already exists as option 6. **Verify this is functioning correctly** rather than adding a new option. If it means surfacing it more prominently or making it the first resort path, that's a minor UX tweak.

**Show full docker build output:** The build command `eval "$BUILD_CMD"` (line 1864) already streams full output — no spinner or redirect. This is already correct.

### Implementation Note on Menu Labels

After removing in-menu rebuild prompts, update menu item 7 label to be clearer:
```
7) Save changes and rebuild image
```
(Currently says "Continue to rebuild (necessary to apply changes!)")

---

## FIX-04: user-setup Image Awareness

### Current Implementation (Lines 219–256)

```bash
USER_IMAGES=$(docker images --format "{{.Repository}}" 2>/dev/null | grep -c "^ds01-${USER_ID}/" 2>/dev/null || true)
```

This counts images. Already works correctly (tested live per CONTEXT.md).

### Enhancement: Show Image Names

Collect image names, not just count:

```bash
USER_IMAGE_NAMES=$(docker images --format "{{.Repository}}" 2>/dev/null | grep "^ds01-${USER_ID}/" | sort -u)
USER_IMAGES=$(echo "$USER_IMAGE_NAMES" | grep -c . || echo 0)
```

Then in the display section (currently lines 229–233):

```bash
if [ "$USER_IMAGES" -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Docker access configured"
    echo -e "${YELLOW}○${NC} No custom images yet (will create one)"
else
    echo -e "${GREEN}✓${NC} Docker access configured ($USER_IMAGES custom image(s)):"
    while IFS= read -r img; do
        [ -n "$img" ] && echo -e "    ${DIM}• $img${NC}"
    done <<< "$USER_IMAGE_NAMES"
fi
```

### Enhancement: Offer to Skip Image Creation

Currently user-setup's "Next Steps" section (line 463–477) directs all users to `project-init --guided` or `project-init my-project`. The enhancement: if `USER_IMAGES > 0`, show a note like:

```
You already have images. You can:
  • Skip image-create and deploy directly: container-deploy <name>
  • Create additional images: project-init my-new-project

Proceed to project-init for a new project? [y/N]:
```

**Important:** The rest of onboarding (SSH, workspace, VS Code) still runs regardless. Only the final "create your first image" recommendation is conditional.

### Exact Detection Pattern

Per CONTEXT.md: `grep "^ds01-${USER_ID}/"` — this matches `ds01-{UID}/project-name` format. Correct and matches what image-create uses.

---

## Don't Hand-Roll

| Problem | Don't Build | Use Instead |
|---------|-------------|-------------|
| Diff display | Custom diff logic | `diff "${DOCKERFILE}.bak" "$DOCKERFILE"` |
| Unknown flag handling | Complex flag parser | Drop unknown flags silently |
| Image name listing | Custom formatting | `docker images --format "{{.Repository}}"` |

---

## Common Pitfalls

### Pitfall 1: container-stats `show_gpu` Variable Scope
**What goes wrong:** `show_gpu` is referenced in `show_container_stats()` but set in the main arg-parsing loop as a global. Script uses `show_gpu="true"` (string), not a proper boolean. This already works, but any new option additions must follow the same pattern.
**How to avoid:** Keep using the string `"true"` pattern, consistent with existing code.

### Pitfall 2: image-update `.bak` File Lifecycle
**What goes wrong:** Currently, `.bak` is created inside `add_python_packages()` and similar functions — one per call. If user adds packages AND removes packages in one session, there may be multiple `.bak` files or `.bak` may represent an intermediate state, not the original.
**How to avoid:** For FIX-03, take the backup ONCE at the start of interactive_mode, before any modifications. Store as `${DOCKERFILE}.pre-session.bak` or similar. Use this for the diff and for revert.

### Pitfall 3: Heredoc Variable Expansion in image-create
**What goes wrong:** Swapping a heredoc delimiter from unquoted `DOCKERFILEEOF` to quoted `'DOCKERFILEEOF'` (or vice versa) changes whether shell variables expand. The fix to quote `$project_name` inside the heredoc is the right approach — do NOT change the delimiter quoting style.
**How to avoid:** Leave the heredoc delimiter unquoted. Just add quotes around the variable references inside.

### Pitfall 4: user-setup `set -e` with Grep
**What goes wrong:** `grep -c` returns exit code 1 when there are zero matches, and `set -e` would abort the script. The current code uses `|| true` to handle this — any new grep-based image counting must also use `|| true` or `|| echo 0`.

### Pitfall 5: image-update's `interactive_mode` Return Path
**What goes wrong:** When removing the in-menu "Rebuild now?" prompts, if you accidentally also remove the `return 0` from menu option 7, the function never exits and loops forever.
**How to avoid:** Keep the `return 0` on menu option 7. Only remove the early-return `return 0` from options 2, 3, 4, 5.

---

## Code Examples

### FIX-01: Silent flag pass-through
```bash
# Before (crashes):
-*)
    echo -e "${RED}✗ Unknown option: $1${NC}\n"
    usage
    exit 1
    ;;

# After (pass-through):
-*)
    # Unknown option — ignore; docker will error if flag is invalid
    shift
    ;;
```

### FIX-02: Operator precedence fix
```bash
# Before (wrong precedence):
if [ "$skip_base" != true ] && [ "$jupyter_choice" = "default" ] || [ "$jupyter_choice" = "custom" ]; then

# After (grouped correctly):
if [ "$skip_base" != true ] && { [ "$jupyter_choice" = "default" ] || [ "$jupyter_choice" = "custom" ]; }; then
```

### FIX-02: Quoted variables in heredoc
```bash
# Before (unquoted, breaks if project name has spaces):
RUN python -m ipykernel install --user \\
    --name=$project_name \\
    --display-name="$project_name ($framework)"

# After (quoted):
RUN python -m ipykernel install --user \\
    --name="${project_name}" \\
    --display-name="${project_name} (${framework})"
```

### FIX-03: Diff before rebuild
```bash
# In main script, after interactive_mode returns, before rebuild prompt:
if [ -f "${DOCKERFILE}.bak" ] && ! diff -q "${DOCKERFILE}.bak" "$DOCKERFILE" > /dev/null 2>&1; then
    echo -e "${CYAN}Changes made to Dockerfile:${NC}"
    echo ""
    diff "${DOCKERFILE}.bak" "$DOCKERFILE" || true
    echo ""
fi
```

### FIX-03: Revert on build failure
```bash
# In the else branch of the build result (currently line ~2027):
else
    echo -e "${RED}✗ Build failed${NC}"
    echo ""
    if [ -f "${DOCKERFILE}.bak" ]; then
        read -r -t 0.1 -n 10000 discard </dev/tty 2>/dev/null || true
        read -p "Revert Dockerfile to pre-update state? [Y/n]: " REVERT_CONFIRM </dev/tty
        REVERT_CONFIRM=${REVERT_CONFIRM:-Y}
        if [[ "$REVERT_CONFIRM" =~ ^[Yy]$ ]]; then
            mv "${DOCKERFILE}.bak" "$DOCKERFILE"
            echo -e "${GREEN}✓${NC} Dockerfile restored"
        fi
    fi
    echo ""
    echo "Troubleshooting: ..."
    exit 1
fi
```

### FIX-04: Image name listing in user-setup
```bash
# Replace the existing USER_IMAGES count-only block:
USER_IMAGE_NAMES=$(docker images --format "{{.Repository}}" 2>/dev/null | grep "^ds01-${USER_ID}/" | sort -u || true)
USER_IMAGES=$(echo "$USER_IMAGE_NAMES" | grep -c . 2>/dev/null || echo 0)
if ! [[ "$USER_IMAGES" =~ ^[0-9]+$ ]]; then USER_IMAGES=0; fi

if [ "$USER_IMAGES" -eq 0 ]; then
    echo -e "${GREEN}✓${NC} Docker access configured"
    echo -e "${YELLOW}○${NC} No custom images yet (will create one)"
else
    echo -e "${GREEN}✓${NC} Docker access configured ($USER_IMAGES custom image(s)):"
    while IFS= read -r img; do
        [ -n "$img" ] && echo -e "    ${DIM}• $img${NC}"
    done <<< "$USER_IMAGE_NAMES"
fi
```

---

## State of the Art

These are mature, stable bash scripts. No framework changes are needed.

| Area | Current Approach | Status |
|------|-----------------|--------|
| Flag parsing | Manual `case` loop | Appropriate for simplicity |
| Dockerfile manipulation | `sed`/`awk` | Correct approach |
| Docker API | CLI calls | Correct (no daemon socket needed) |

---

## Open Questions

1. **FIX-02: Is the original "creation: command not found" error still reproducible?**
   - What we know: The file passes `bash -n`; confirmed code quality bugs exist at lines 1364, 1376
   - What's unclear: Whether the original error was from a specific input combination
   - Recommendation: Run the wizard interactively with `--no-build` to reach the Jupyter phase and verify

2. **FIX-03: `.bak` file timing — where to take the session backup?**
   - What we know: Multiple functions each take their own `.bak`; this can miss the true starting state if multiple operations happen
   - What's unclear: Whether users typically do multiple Dockerfile operations in one session
   - Recommendation: Take a session-start backup at the top of `interactive_mode()` before the while loop; use it for diff and revert

3. **FIX-04: Where exactly in user-setup to add the skip-image-creation prompt?**
   - What we know: user-setup does NOT call `image-create` directly — it only points users to `project-init` in the Next Steps section (line 463–477)
   - What's unclear: The onboarding flow doesn't actually run `image-create`; the "skip" offer is purely informational
   - Recommendation: In the Next Steps section, conditionally show "You already have N images" message and suggest `container-deploy` as an alternative to `project-init`

---

## Sources

### Primary (HIGH confidence)
- Direct code inspection of `/opt/ds01-infra/scripts/user/atomic/container-stats` (356 lines)
- Direct code inspection of `/opt/ds01-infra/scripts/user/atomic/image-create` (1869 lines)
- Direct code inspection of `/opt/ds01-infra/scripts/user/atomic/image-update` (2040 lines)
- Direct code inspection of `/opt/ds01-infra/scripts/user/wizards/user-setup` (478 lines)
- `bash -n` syntax validation — all 4 scripts pass clean

### Secondary (MEDIUM confidence)
- Bash operator precedence rules (`&&` before `||`) — well-established, standard POSIX/GNU bash behaviour
- `grep -c` exit code behaviour with zero matches — standard, verified in bash documentation

---

## Metadata

**Confidence breakdown:**
- FIX-01 root cause: HIGH — code directly inspected, catch-all at line 330 confirmed
- FIX-02 operator precedence: HIGH — standard bash precedence rules, verifiable
- FIX-02 heredoc variable: HIGH — code directly inspected at lines 1375–1377
- FIX-02 original error: MEDIUM — file passes syntax check; runtime test needed
- FIX-03 double prompt: HIGH — both prompt locations confirmed in code
- FIX-04 enhancement: HIGH — current implementation inspected; image name collection is straightforward

**Research date:** 2026-02-17
**Valid until:** Until scripts are edited — these are findings from live source code, not docs
