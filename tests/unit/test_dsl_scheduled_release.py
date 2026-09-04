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
CURL_STUB = """#!/bin/bash
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
    */dispatches) cat "$STUB_DIR/dispatch-$org" ;;
    */runs*)
        cp "$STUB_DIR/runs-$org.json" "$out"
        printf '200'
        ;;
esac
"""

DATE_STUB = """#!/bin/bash
if [ "$1" = "-d" ]; then echo "$STUB_RUN_EPOCH"; else echo "$STUB_NOW_EPOCH"; fi
"""

NOW = 1_757_000_000


def _runs(*conclusions, created_at="2026-09-04T12:00:00Z"):
    return {
        "workflow_runs": [
            {"status": "completed", "conclusion": c, "created_at": created_at} for c in conclusions
        ]
    }


def _tick(tmp_path, orgs, *, minutes_since_run=10):
    """Run one tick. `orgs` maps org -> (dispatch status, runs body)."""
    stub = tmp_path / "bin"
    stub.mkdir()
    for name, body in (("gh", GH_STUB), ("curl", CURL_STUB), ("date", DATE_STUB)):
        path = stub / name
        path.write_text(body)
        path.chmod(0o755)

    search = [{"name": ".github", "owner": {"login": org}} for org in orgs]
    (tmp_path / "search.json").write_text(json.dumps(search))
    for org, (code, runs) in orgs.items():
        (tmp_path / f"dispatch-{org}").write_text(str(code))
        (tmp_path / f"runs-{org}.json").write_text(json.dumps(runs or {"workflow_runs": []}))

    return subprocess.run(
        ["bash", str(DRIVER)],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{stub}:/usr/bin:/bin",
            "GH_TOKEN": "stub",
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
    result = _tick(tmp_path, {"orga": (401, None)})
    assert result.returncode == 1
    assert "token-dead orga" in result.stdout


def test_three_consecutive_failures_fail_the_tick(tmp_path):
    result = _tick(tmp_path, {"orga": (204, _runs("failure", "failure", "failure"))})
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


def test_no_response_body_is_ever_logged(tmp_path):
    # Bodies can carry student names; the journal is posted to Teams on failure.
    runs = _runs("failure", "failure", "failure")
    runs["workflow_runs"][0]["actor"] = {"login": "a-student-handle"}
    result = _tick(tmp_path, {"orga": (204, runs)})
    assert "a-student-handle" not in result.stdout + result.stderr
