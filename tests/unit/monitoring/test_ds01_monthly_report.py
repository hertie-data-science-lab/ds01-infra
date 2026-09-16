"""Unit tests for the monthly report's two delivery channels.

Covers the bug that stopped the report arriving: the webhook guard accepted the
placeholder the repo ships (`PASTE_LOGIC_AZURE_URL_HERE`), so every monthly run
POSTed to a string that is not a URL and failed into
/var/log/ds01/monthly-report.log. And the mail channel added beside it, which
must reach `dsl-alert-mail.py` with the report on stdin and the ASCII charts
intact.

Nothing here touches the network: `_post_webhook` and `subprocess.run` are the
two boundaries, and each is replaced by a recorder.
"""

import importlib.util
import sys
from importlib.machinery import SourceFileLoader
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[3]
REPORT = REPO / "scripts/monitoring/ds01-monthly-report"

# A heatmap row and a bar-chart row, as generate_report() draws them: rows of text
# whose meaning is their alignment.
HEATMAP = "Mon  |  ....##@@##..  |\nTue  |  ..####@@....  |"


@pytest.fixture(scope="module")
def report():
    """The generator imported as a module - its filename has no `.py` and a hyphen."""
    name = "ds01_monthly_report"
    spec = importlib.util.spec_from_file_location(
        name, REPORT, loader=SourceFileLoader(name, str(REPORT))
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(autouse=True)
def _no_ambient_mail_config(monkeypatch, tmp_path_factory):
    """No test may be configured by the box it runs on."""
    monkeypatch.delenv("DSL_ALERT_TO", raising=False)
    monkeypatch.delenv("DS01_TEAMS_WEBHOOK_URL", raising=False)


# ------------------------------------------------------------------ the webhook guard


@pytest.mark.parametrize(
    "value",
    [
        "PASTE_LOGIC_AZURE_URL_HERE",  # what the repo actually ships, and what prod holds
        "PLACEHOLDER_URL",  # what the old check looked for
        "",
        "http://logic.azure.com/workflows/x",  # not https
    ],
)
def test_a_webhook_that_is_not_an_https_url_is_no_webhook(report, monkeypatch, value):
    # The whole bug: this returned the placeholder, post_to_teams POSTed to it, and the
    # monthly run failed every month instead of quietly skipping a channel it never had.
    monkeypatch.setenv("DS01_TEAMS_WEBHOOK_URL", value)
    assert report._load_teams_webhook_url() is None


def test_an_https_webhook_is_used(report, monkeypatch):
    url = "https://prod-1.westeurope.logic.azure.com/workflows/abc/triggers/manual"
    monkeypatch.setenv("DS01_TEAMS_WEBHOOK_URL", url)
    assert report._load_teams_webhook_url() == url


def test_the_placeholder_file_on_disk_is_read_as_unconfigured(report, monkeypatch, tmp_path):
    # The prod path: the env var is unset and the git-ignored file holds the placeholder.
    runtime = tmp_path / "config/runtime"
    runtime.mkdir(parents=True)
    (runtime / "teams-webhook-url.txt").write_text("PASTE_LOGIC_AZURE_URL_HERE\n")
    monkeypatch.setattr(report, "INFRA_ROOT", tmp_path)
    assert report._load_teams_webhook_url() is None


def test_a_provisioned_file_is_read_a_line_at_a_time(report, monkeypatch, tmp_path):
    runtime = tmp_path / "config/runtime"
    runtime.mkdir(parents=True)
    (runtime / "teams-webhook-url.txt").write_text("https://logic.azure.com/w/1\nstray\n")
    monkeypatch.setattr(report, "INFRA_ROOT", tmp_path)
    assert report._load_teams_webhook_url() == "https://logic.azure.com/w/1"


def test_an_unconfigured_webhook_posts_nothing(report, monkeypatch):
    posted = []
    monkeypatch.setattr(report, "_post_webhook", lambda *a, **k: posted.append(a))
    monkeypatch.setattr(report, "_load_teams_webhook_url", lambda: None)
    assert report.post_to_teams("{}", "# report") is False
    assert posted == []


# -------------------------------------------------------------------- the mail body


def test_the_report_is_wrapped_in_one_pre_so_the_charts_survive(report):
    body = report.build_mail_body(f"# March 2026\n\n{HEATMAP}\n")
    assert body.count("<pre") == 1
    # Verbatim, spacing included: a client that reflowed these would turn the month's
    # busiest hour into noise.
    assert HEATMAP in body


def test_markup_in_the_report_is_escaped_not_shipped(report):
    # The report interpolates values nobody here controls - ds01-hub issue titles,
    # container names, usernames.
    body = report.build_mail_body("issue: <script>alert(1)</script> & co")
    assert "<script>" not in body
    assert "&lt;script&gt;alert(1)&lt;/script&gt; &amp; co" in body


# ----------------------------------------------------------------- the mail delivery


@pytest.fixture
def mailer_calls(report, monkeypatch, tmp_path):
    """Capture the mailer subprocess; `mailer_calls.rc` sets its exit status."""

    class Recorder(list):
        rc = 0

        def __call__(self, argv, **kwargs):
            self.append({"argv": argv, **kwargs})

            class Completed:
                returncode = self.rc

            return Completed()

    recorder = Recorder()
    monkeypatch.setattr(report.subprocess, "run", recorder)
    monkeypatch.setenv("DSL_ALERT_TO", "h.baker@hertie-school.org")
    return recorder


def test_the_report_reaches_the_mailer_as_html_on_stdin(report, mailer_calls):
    assert report.mail_report(f"# March 2026\n\n{HEATMAP}\n", 2026, 3) is True
    call = mailer_calls[0]
    assert str(report.MAILER) in call["argv"]
    assert "--html" in call["argv"]
    assert "[ds01] Monthly report - March 2026" in call["argv"]
    # On stdin, never argv: /proc on this box is world-readable.
    assert HEATMAP in call["input"]
    assert not any(HEATMAP in str(arg) for arg in call["argv"])


def test_no_recipient_is_named_on_the_command_line(report, mailer_calls):
    # Who the lab mails is a deployment decision in one root-only file, not a constant
    # compiled into a report generator.
    report.mail_report("# report", 2026, 3)
    assert "--to" not in mailer_calls[0]["argv"]


def test_a_failed_send_is_reported_and_does_not_raise(report, mailer_calls):
    mailer_calls.rc = 1
    assert report.mail_report("# report", 2026, 3) is False


def test_a_mailer_that_cannot_be_run_does_not_lose_the_run(report, monkeypatch, capsys):
    # The report is already on disk by this point; a broken mailer must not take it down.
    monkeypatch.setenv("DSL_ALERT_TO", "h.baker@hertie-school.org")

    def boom(*_args, **_kwargs):
        raise OSError("no such file")

    monkeypatch.setattr(report.subprocess, "run", boom)
    assert report.mail_report("# report", 2026, 3) is False
    assert "Mail delivery failed" in capsys.readouterr().err


def test_an_unprovisioned_box_skips_mail_quietly(report, monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(report, "MAIL_ENV_FILE", tmp_path / "absent.env")
    ran = []
    monkeypatch.setattr(report.subprocess, "run", lambda *a, **k: ran.append(a))
    assert report.mail_report("# report", 2026, 3) is False
    assert ran == []
    assert "Mail not configured" in capsys.readouterr().err


def test_the_env_file_alone_is_enough_to_try(report, monkeypatch, tmp_path, mailer_calls):
    # The cron case: nothing in the environment, but /etc/dsl-alert-mail.env exists and
    # the mailer reads it itself.
    monkeypatch.delenv("DSL_ALERT_TO")
    env_file = tmp_path / "dsl-alert-mail.env"
    env_file.write_text("DSL_ALERT_TO=h.baker@hertie-school.org\n")
    monkeypatch.setattr(report, "MAIL_ENV_FILE", env_file)
    assert report.mail_report("# report", 2026, 3) is True
