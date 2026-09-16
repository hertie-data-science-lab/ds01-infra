"""Unit tests for the infra alarms' issue loop (.github/actions/alarm/alarm.sh).

This is the script that decides whether an unattended failure files an issue,
comments on the open one, or stays quiet - and, through its `report` output,
whether the maintainer is mailed. Its three failure modes are all silent: a
throttle that never engages mails on every tick until nobody reads it, a throttle
that never expires means the second week of an outage says nothing, and a title
match that is too loose means one alarm closes another's issue.

`gh` is stubbed on PATH, as test_dsl_alert_mail.py and test_dsl_scheduled_release.py
stub the commands they drive; jq is real, because the script's matching IS a jq
expression.
"""

import json
import subprocess
import time
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
ALARM = REPO / ".github/actions/alarm/alarm.sh"

TITLE = "ds01-runner is offline"
RUN_URL = "https://github.com/hertie-data-science-lab/ds01-infra/actions/runs/1"

# Answers `gh issue list --json ...` from a fixture, and records every other call.
GH_STUB = """#!/bin/bash
printf '%s\\n' "$*" >>"$STUB_DIR/gh.log"
if [ "$1 $2" = "issue list" ]; then
    cat "$STUB_DIR/issues.json"
    exit 0
fi
exit 0
"""


def _iso(seconds_ago: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - seconds_ago))


@pytest.fixture
def alarm(tmp_path):
    """Run alarm.sh against a stubbed `gh`; returns a callable and the recorded calls."""
    stub = tmp_path / "bin"
    stub.mkdir()
    gh = stub / "gh"
    gh.write_text(GH_STUB)
    gh.chmod(0o755)
    issues = tmp_path / "issues.json"
    issues.write_text("[]")
    output = tmp_path / "github_output"
    output.write_text("")

    class Runner:
        log = tmp_path / "gh.log"
        outputs = output

        def open_issues(self, *issues_):
            issues.write_text(json.dumps(list(issues_)))

        def __call__(self, mode, note="the run failed"):
            return subprocess.run(
                ["bash", str(ALARM), mode],
                capture_output=True,
                text=True,
                env={
                    "PATH": f"{stub}:/usr/bin:/bin",
                    "STUB_DIR": str(tmp_path),
                    "GITHUB_OUTPUT": str(output),
                    "GH_TOKEN": "stub",
                    "ALARM_REPO": "hertie-data-science-lab/ds01-infra",
                    "ALARM_TITLE": TITLE,
                    "ALARM_NOTE": note,
                    "ALARM_RUN_URL": RUN_URL,
                },
            )

        def calls(self):
            return self.log.read_text() if self.log.exists() else ""

        def output_text(self):
            return output.read_text()

    return Runner()


def _issue(number, title=TITLE, age_seconds=0):
    return {"number": number, "title": title, "updatedAt": _iso(age_seconds)}


# --------------------------------------------------------------------------- reporting


def test_a_first_failure_files_an_issue_and_mails(alarm):
    result = alarm("report")
    assert result.returncode == 0, result.stderr
    assert "issue create" in alarm.calls()
    # `report=true` is what gates the mail: a maintainer who gets an email can always
    # find the thread it came from.
    assert "report=true" in alarm.output_text()


def test_a_second_failure_within_six_hours_says_nothing(alarm):
    # The alarm fires on EVERY tick while a fault stands. A comment per run buries the
    # thread and mails hourly about one fault.
    alarm.open_issues(_issue(7, age_seconds=60 * 60))
    result = alarm("report")
    assert result.returncode == 0, result.stderr
    assert "issue comment" not in alarm.calls()
    assert "issue create" not in alarm.calls()
    assert "report=false" in alarm.output_text()
    assert "see issue 7" in result.stdout


def test_a_failure_after_six_quiet_hours_comments_and_mails(alarm):
    # The other direction: a throttle that never expires means the second week of an
    # outage says nothing at all.
    alarm.open_issues(_issue(7, age_seconds=7 * 60 * 60))
    result = alarm("report")
    assert result.returncode == 0, result.stderr
    assert "issue comment 7" in alarm.calls()
    assert "report=true" in alarm.output_text()


def test_an_unparseable_timestamp_is_treated_as_long_overdue(alarm):
    # The point of the issue is that somebody hears; failing closed would be silence.
    alarm.open_issues({"number": 7, "title": TITLE, "updatedAt": "not a date"})
    result = alarm("report")
    assert result.returncode == 0, result.stderr
    assert "issue comment 7" in alarm.calls()
    assert "report=true" in alarm.output_text()


def test_an_issue_with_another_title_is_not_this_alarm(alarm):
    # `--search` is a WORD match, so "ds01-runner is offline" also hits "Deploy is
    # failing" once both words appear. A loose match here files nothing while another
    # alarm's issue is open.
    alarm.open_issues(_issue(9, title="Deploy is failing", age_seconds=60))
    result = alarm("report")
    assert result.returncode == 0, result.stderr
    assert "issue create" in alarm.calls()


# ------------------------------------------------------------------------------ closing


def test_a_green_run_closes_the_open_issue(alarm):
    alarm.open_issues(_issue(7, age_seconds=60))
    result = alarm("close")
    assert result.returncode == 0, result.stderr
    assert "issue close 7" in alarm.calls()
    assert RUN_URL in alarm.calls()


def test_closing_leaves_another_alarms_issue_alone(alarm):
    # The failure this guards: one alarm's green run closing another's open issue, which
    # then refiles on the next tick with a fresh mail.
    alarm.open_issues(_issue(9, title="Deploy is failing", age_seconds=60), _issue(7))
    alarm("close")
    calls = alarm.calls()
    assert "issue close 7" in calls
    assert "issue close 9" not in calls


def test_closing_nothing_is_not_an_error(alarm):
    result = alarm("close")
    assert result.returncode == 0, result.stderr
    assert "issue close" not in alarm.calls()
    # A close never mails: recovery is not news.
    assert "report=" not in alarm.output_text()


def test_an_unknown_mode_is_refused(alarm):
    result = alarm("panic")
    assert result.returncode == 1
    assert "usage" in result.stderr
