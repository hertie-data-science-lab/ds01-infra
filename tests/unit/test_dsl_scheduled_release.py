"""Unit tests for scripts/maintenance/dsl-scheduled-release.sh.

The driver reaches GitHub only through `gh` and `curl`, so both are stubbed on
PATH (plus `date`, to make "how old is the newest run" deterministic). The
assertions are on the journal lines and the exit code, because those are the
only two things systemd and the OnFailure alert act on.
"""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[2]
DRIVER = REPO / "scripts/maintenance/dsl-scheduled-release.sh"

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(shutil.which("jq") is None, reason="driver parses JSON with jq"),
]

GH_STUB = """#!/bin/bash
cat "$STUB_DIR/search.json"
"""

# Echoes the status code for a dispatch, or writes the runs body and echoes 200.
# Every argv it is handed is appended to argv.log, so a test can prove the token
# is never passed on a command line. A dispatch file holding several codes is
# consumed one line per call, which is how the 5xx retry is exercised.
CURL_STUB = """#!/bin/bash
printf '%s\\n' "$@" >>"$STUB_DIR/argv.log"
out=/dev/null
url=
args=("$@")
for ((i = 0; i < ${#args[@]}; i++)); do
    case "${args[i]}" in
        -o) out="${args[i + 1]}" ;;
        https://*) url="${args[i]}" ;;
    esac
done
org=${url#https://api.github.com/repos/}
org=${org%%/*}
case "$url" in
    */dispatches)
        f="$STUB_DIR/dispatch-$org"
        code=$(head -1 "$f")
        if [ "$(wc -l <"$f")" -gt 1 ]; then
            tail -n +2 "$f" >"$f.rest"
            mv "$f.rest" "$f"
        fi
        printf '%s' "$code"
        ;;
    */runs*)
        cp "$STUB_DIR/runs-$org.json" "$out"
        printf '200'
        ;;
esac
"""

DATE_STUB = """#!/bin/bash
if [ "$1" = "-d" ]; then echo "$STUB_RUN_EPOCH"; else echo "$STUB_NOW_EPOCH"; fi
"""

# The 5xx retry sleeps; the tick's timing is systemd's business, not a test's.
SLEEP_STUB = """#!/bin/bash
exit 0
"""

NOW = 1_757_000_000
TOKEN = "gho_stub_token_sentinel"


def _runs(*conclusions, created_at="2026-09-04T12:00:00Z"):
    return {
        "workflow_runs": [
            {"status": "completed", "conclusion": c, "created_at": created_at} for c in conclusions
        ]
    }


def _tick(tmp_path, orgs, *, minutes_since_run=10):
    """Run one tick.

    `orgs` maps org -> (dispatch status, runs body). A dispatch status may be a
    list, one status per attempt. A runs body may be a raw string, to hand the
    driver something that is not JSON.
    """
    stub = tmp_path / "bin"
    stub.mkdir()
    for name, body in (
        ("gh", GH_STUB),
        ("curl", CURL_STUB),
        ("date", DATE_STUB),
        ("sleep", SLEEP_STUB),
    ):
        path = stub / name
        path.write_text(body)
        path.chmod(0o755)

    search = [{"name": ".github", "owner": {"login": org}} for org in orgs]
    (tmp_path / "search.json").write_text(json.dumps(search))
    for org, (code, runs) in orgs.items():
        codes = code if isinstance(code, list) else [code]
        (tmp_path / f"dispatch-{org}").write_text("\n".join(str(c) for c in codes) + "\n")
        body = runs if isinstance(runs, str) else json.dumps(runs or {"workflow_runs": []})
        (tmp_path / f"runs-{org}.json").write_text(body)

    return subprocess.run(
        ["bash", str(DRIVER)],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{stub}:/usr/bin:/bin",
            "GH_TOKEN": TOKEN,
            "STUB_DIR": str(tmp_path),
            "STUB_NOW_EPOCH": str(NOW),
            "STUB_RUN_EPOCH": str(NOW - minutes_since_run * 60),
        },
    )


def test_healthy_tick_logs_only_the_summary(tmp_path):
    result = _tick(tmp_path, {"orga": (204, _runs("success", "success"))})
    assert result.returncode == 0
    assert result.stdout.strip() == "dispatched=1 ok=1 pruned=0 failing=0 silent=0"


def test_a_deleted_org_is_pruned_not_alerted(tmp_path):
    result = _tick(tmp_path, {"gone": (404, None)})
    assert result.returncode == 0
    assert "prune gone" in result.stdout
    assert "pruned=1" in result.stdout


def test_a_revoked_driver_token_fails_the_tick(tmp_path):
    # Every org refused, so the credential is the only explanation left.
    result = _tick(tmp_path, {"orga": (401, None), "orgb": (401, None)})
    assert result.returncode == 1
    assert "token-dead (all 2 orgs refused the dispatch)" in result.stdout
    assert "dispatch-refused" not in result.stdout


def test_one_refused_org_is_not_a_dead_token(tmp_path):
    # 403 is also an archived hub repo, Actions disabled, or a secondary rate
    # limit — the other org going through says the token is fine.
    result = _tick(tmp_path, {"orga": (403, None), "orgb": (204, _runs("success"))})
    assert result.returncode == 1
    assert "dispatch-refused orga (403)" in result.stdout
    assert "token-dead" not in result.stdout


def test_a_refused_org_still_leaves_the_later_orgs_driven(tmp_path):
    # The orgs are dispatched in sorted order, so orgb is reached after orga.
    result = _tick(tmp_path, {"orga": (403, None), "orgb": (204, _runs("success"))})
    assert result.returncode == 1
    assert "dispatched=2 ok=1 pruned=0 failing=0 silent=0" in result.stdout


def test_a_5xx_dispatch_is_retried_once(tmp_path):
    result = _tick(tmp_path, {"orga": ([503, 204], _runs("success"))})
    assert result.returncode == 0
    assert "retry orga (dispatch 503)" in result.stdout
    assert "dispatched=1 ok=1" in result.stdout


def test_three_consecutive_failures_fail_the_tick(tmp_path):
    result = _tick(tmp_path, {"orga": (204, _runs("failure", "failure", "failure"))})
    assert result.returncode == 1
    assert "failing orga" in result.stdout


def test_a_cancelled_run_does_not_break_a_failure_streak(tmp_path):
    # The toolkit's queue-of-one concurrency cancels a queued run; that is not
    # evidence the workflow recovered.
    runs = _runs("failure", "cancelled", "failure", "failure")
    result = _tick(tmp_path, {"orga": (204, runs)})
    assert result.returncode == 1
    assert "failing orga" in result.stdout


def test_two_failures_and_an_older_success_are_tolerated(tmp_path):
    result = _tick(tmp_path, {"orga": (204, _runs("failure", "failure", "success"))})
    assert result.returncode == 0
    assert "failing orga" not in result.stdout


def test_a_stale_newest_run_is_silent(tmp_path):
    result = _tick(tmp_path, {"orga": (204, _runs("success"))}, minutes_since_run=61)
    assert result.returncode == 1
    assert "silent orga" in result.stdout


def test_an_org_that_never_ran_is_silent(tmp_path):
    result = _tick(tmp_path, {"orga": (204, {"workflow_runs": []})})
    assert result.returncode == 1
    assert "silent orga (no runs)" in result.stdout


def test_a_truncated_org_search_drives_nothing(tmp_path):
    # Driving an unknowable subset of orgs is worse than not driving at all.
    orgs = {f"o{i}": (204, _runs("success")) for i in range(100)}
    result = _tick(tmp_path, orgs)
    assert result.returncode == 1
    assert "search limit" in result.stdout
    assert "dispatched=" not in result.stdout


def test_a_malformed_observe_body_does_not_abort_the_tick(tmp_path):
    # A 200 we cannot parse is one org's problem: the orgs after it must still be
    # dispatched, and the summary line must still be printed.
    result = _tick(
        tmp_path,
        {"orga": (204, "<html>502 whoops"), "orgb": (204, _runs("success"))},
    )
    assert result.returncode == 1
    assert "observe-failed orga (parse)" in result.stdout
    assert "dispatched=2 ok=2 pruned=0 failing=0 silent=0" in result.stdout


def test_no_response_body_is_ever_logged(tmp_path):
    # Bodies can carry student names; the journal is posted to Teams on failure.
    runs = _runs("failure", "failure", "failure")
    runs["workflow_runs"][0]["actor"] = {"login": "a-student-handle"}
    result = _tick(tmp_path, {"orga": (204, runs)})
    assert "a-student-handle" not in result.stdout + result.stderr


def test_the_token_never_reaches_a_command_line(tmp_path):
    # /proc on the box is world-readable, so a token in argv is a token in `ps`.
    result = _tick(tmp_path, {"orga": (204, _runs("success"))})
    argv = (tmp_path / "argv.log").read_text()
    assert TOKEN not in argv
    assert TOKEN not in result.stdout + result.stderr
    # ...and it is genuinely still sent, from a file curl reads itself.
    assert [line for line in argv.splitlines() if line.startswith("@") and line.endswith("/auth")]
