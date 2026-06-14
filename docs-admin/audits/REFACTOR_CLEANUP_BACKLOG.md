# Refactor / Cleanup Backlog

Follow-up items surfaced during the 2026-06 cleanup pass (stacked PRs #59–#62).
These were **deliberately not done** in that pass — each either needs an owner
decision, GPU/Docker verification, or carries more risk than its value on the
live create path. Grouped by why it was deferred.

## A. Needs an owner decision (cannot be done autonomously)

| Item | Location | Finding | Recommended action |
|------|----------|---------|--------------------|
| Test-only lib `docker-utils.sh` | `scripts/lib/docker-utils.sh` | Referenced only by `testing/unit/lib/test_docker_utils.py` (+ a comment in `config/label-schema.yaml`); no production script sources it. | Decide: wire into the scripts that hand-roll container/label queries, **or** remove lib + its test. |
| `container-session.sh` — **live, keep** | `scripts/lib/container-session.sh` | **Not** test-only: it is the live `start`/`run`/`attach` handler, reached via 3 symlinks (`scripts/user/atomic/container-{start,run,attach}`). An earlier content-grep read it as "test-only" — a blind spot, since symlink *targets* aren't matched by `grep -r`. Under active edit on `refactor/unified-user-caps`. | No removal. Keep. (Caution: audit lib usage with `find -type l -lname`, not content-grep alone.) |
| Legacy `aime.mlc.*` label fallback | `scripts/docker/{container-owner-tracker,ds01-resource-query,gpu-state-reader,sync-container-owners}.py`, `scripts/monitoring/detect-workloads.py`, `scripts/lib/ds01_core.py` | ~10 `# TODO: remove when no legacy containers remain (Phase 7 migration)` sites guarding `aime.mlc.USER` / `aime.mlc.DS01_MANAGED` fallbacks. | Confirm `docker ps --filter label=aime.mlc.USER` returns nothing in production, then remove the fallbacks (~50 LOC). |
| `config/usr-mirrors` lib drift | `config/usr-mirrors/local/lib/interactive-select.sh` vs `scripts/lib/interactive-select.sh` | The mirrored copy **differs** (19 diff lines) from canonical. | Determine whether `usr-mirrors` is a deploy artifact that should be regenerated from `scripts/lib/`, or intentionally divergent — then reconcile/document. |
| Planning docs in user-facing tree | `docs-admin/planning/{INTEGRATION_TEST_RESULTS,REFACTORING_PLAN,IMPLEMENTATION_LOG}.md` | Point-in-time records living in admin docs. `.planning/` is **not tracked**, so a `git mv` there would delete them. | Decide: archive (e.g. under `archive/`), delete (history preserved), or keep. |
| Old archive dir | `archive/deprecated-scripts-2025-11/` | Superseded backups, but **referenced** by `docs-admin/planning/REFACTORING_PLAN.md` — so PR1's "delete only if unreferenced" condition was not met. | Remove once the referencing doc is archived/updated. (`archive/2025-12-cleanup/` is organised — keep.) |
| Deprecated config dir | `config/etc-mirrors/` (+ its `.deprecated` notice) | Whole dir marked deprecated ("retained for reference, NOT deployed"); superseded by `config/deploy/`. | Confirm nothing reads it, then remove the directory (not just the marker). |
| Throwaway test toolkit | `testing/cleanup-automation/test-*.sh` + `testing/{fix,diagnose,quick-test,test}-gid*.sh`, `test-mlc-remove-error-handling.sh`, `test-phase-3.1-validation.sh`, `e2e_custom_image_test.sh` | Ad-hoc manual-test scripts, **but documented** as procedures in `TESTING-GUIDE.md` / `GID-FIX-STATUS.md` / `SUMMARY.md`. | Consolidate the worthwhile cases into the pytest suite, then remove scripts **and** their how-to docs together (don't leave dangling instructions). |

## B. Valuable but needs GPU/Docker verification (don't change blind)

| Item | Location | Finding | Recommended action |
|------|----------|---------|--------------------|
| Unguarded subprocess timeouts | `scripts/docker/{gpu-state-reader,ds01-resource-query,gpu-availability-checker}.py` (9 calls) | Lack `timeout=` and are **not** inside a broad `try/except`, so adding a timeout converts a hang into an *uncaught* `TimeoutExpired` crash. | Add `timeout=` **with** appropriate handling; verify on a GPU host. (The guarded calls were already handled in PR #61.) |
| Allocator subprocess timeouts | `scripts/docker/gpu_allocator_v2.py` (9 calls) | Live, state-mutating allocation path; a mid-allocation timeout could leave inconsistent state. | Add timeouts carefully with state-consistency review + GPU verification. |
| `enforce-containers.sh` eval | `scripts/docker/enforce-containers.sh:99` | Same `eval echo "~$user"` as PR #62 fixed elsewhere, but here it is **literal text inside a quoted heredoc** (`<<'ENABLEEOF'`) generating `scripts/user/enable-container-enforcement.sh`. | Harden the generated script's home lookup (getent), keeping generator/generated in sync; verify the generated output. |
| Inline-Python injection | `scripts/monitoring/resource-alert-checker.sh` (~12 `python3 -c "...$var..."` sites) | Shell vars (incl. usernames that may contain `@`/`.`) interpolated into `python3 -c` strings. Inputs are largely internal/sanitised, so risk is mostly theoretical, but fragile. | Pass values via argv/stdin instead of string interpolation; verify each rewritten block. |

## C. Considered and intentionally skipped (low value vs. risk)

- **Resource-limit parsing dedup** between `mlc-create-wrapper.sh` and `mlc-create-from-image.sh`: not actually identical (the wrapper does extra group/slice handling); no clean shared extraction, and it sits on the critical create path.
- **`now_utc`/waste-detection dedup** in `gpu-utilization-monitor.py` / `mig-utilization-monitor.py`: the monitors import no shared Python, so deduping ~10 lines means adding import coupling for little gain.
- **`error-messages.sh` triple-source** in `mlc-create-wrapper.sh`: collapsing the 3 conditional sources to one guarded source changes error-path control flow on the critical script and can't be verified without GPU/Docker.
- **Info-level shellcheck** (SC2086/SC2001/SC2012/SC2162): CI uses `shellcheck -S warning`, which ignores these; re-quoting risks changing word-splitting. (A full zero-out was the goal of the abandoned `refactor/ci-overhaul` branch.)
- **The 5 divergent system-script loggers** (`setup-docker-cgroups`, `setup-docker-permissions`, `setup-disk-quotas`, `migrate-to-opa`, `setup-opa-authz`): use a distinct `[OK]`/`[WARN]` convention; consolidating onto `logging.sh` (PR #60) would change their output.
