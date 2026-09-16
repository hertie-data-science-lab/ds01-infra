"""Unit tests for the config watchdog's drift branch and its two alert channels.

The watchdog is run for real against a temporary infra tree, with the commands it
shells out to stubbed on PATH - the same shape as the shell half of
test_dsl_alert_mail.py. What matters is the branch nobody ever sees until it
matters: a drifted config is restored, and a human is told on both channels.

The drift alert has been Teams-only and Teams has never been provisioned - prod's
webhook file holds `PASTE_LOGIC_AZURE_URL_HERE` - so every drift alert since the
watchdog was written has gone nowhere. These tests pin down both halves of the
fix: the placeholder is not a webhook, and mail goes independently.
"""

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
WATCHDOG = REPO / "scripts/maintenance/config-watchdog.sh"

DEPLOYED = "gpu:\n  max_per_user: 1\n"
DRIFTED = "gpu:\n  max_per_user: 8\n"
SHA = "0f71c0d0f71c0d0f71c0d0f71c0d0f71c0d0f71c"

# Records what it was asked to do and, for the mailer call, what arrived on stdin.
# One stub serves both python3 calls: the Teams payload build (`-c ...`) and the
# mailer itself.
PYTHON3_STUB = """#!/bin/bash
printf '%s\\n' "$@" >>"$STUB_DIR/python3.argv"
if [ "$1" = "-c" ]; then
    echo '{"text": "stub payload"}'
    exit 0
fi
cat >>"$STUB_DIR/mail.stdin"
exit ${STUB_MAIL_RC:-0}
"""

CURL_STUB = """#!/bin/bash
printf '%s\\n' "$@" >>"$STUB_DIR/curl.argv"
exit ${STUB_CURL_RC:-0}
"""

# Stands in for `runuser -u <owner> -- git -C <staging> show <sha>:<path>`, so
# neither a second user nor a git checkout is needed to reach the drift branch.
RUNUSER_STUB = """#!/bin/bash
cat "$STUB_DIR/deployed.yaml"
"""

# macOS has no sha256sum. openssl is on both, and the script only ever compares
# this command's output with itself.
SHA256SUM_STUB = """#!/bin/bash
if [ $# -gt 0 ]; then
    printf '%s  %s\\n' "$(openssl dgst -sha256 "$1" | sed 's/.*= *//')" "$1"
else
    printf '%s  -\\n' "$(openssl dgst -sha256 | sed 's/.*= *//')"
fi
"""

LOGGER_STUB = "#!/bin/bash\nexit 0\n"

STUBS = {
    "python3": PYTHON3_STUB,
    "curl": CURL_STUB,
    "runuser": RUNUSER_STUB,
    "sha256sum": SHA256SUM_STUB,
    "logger": LOGGER_STUB,
}


@pytest.fixture
def box(tmp_path):
    """A temporary infra tree with a drifted live config, ready for `--full`."""
    infra = tmp_path / "opt/ds01-infra"
    (infra / "scripts/maintenance").mkdir(parents=True)
    (infra / "config/runtime").mkdir(parents=True)
    (infra / "scripts/maintenance/config-watchdog.sh").write_bytes(WATCHDOG.read_bytes())
    (infra / "config/runtime/resource-limits.yaml").write_text(DRIFTED)
    (tmp_path / "deployed.yaml").write_text(DEPLOYED)
    (tmp_path / "current-sha").write_text(SHA + "\n")

    stub = tmp_path / "bin"
    stub.mkdir()
    for name, body in STUBS.items():
        path = stub / name
        path.write_text(body)
        path.chmod(0o755)
    return tmp_path


def _run(box, **env):
    """One `--full` tick against the temporary tree."""
    infra = box / "opt/ds01-infra"
    return subprocess.run(
        ["bash", str(infra / "scripts/maintenance/config-watchdog.sh"), "--full"],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{box / 'bin'}:/usr/bin:/bin",
            "STUB_DIR": str(box),
            "LOG_FILE": str(box / "config-watchdog.log"),
            "CRON_FILE": str(box / "ds01-maintenance"),
            "CURRENT_SHA_FILE": str(box / "current-sha"),
            "STAGING": str(box / "staging"),
            # No ambient mail provisioning: a test describes its own environment.
            "DSL_ALERT_ENV_FILE": str(box / "absent.env"),
            **env,
        },
    )


def _live_config(box):
    return (box / "opt/ds01-infra/config/runtime/resource-limits.yaml").read_text()


def _webhook_file(box, value):
    (box / "opt/ds01-infra/config/runtime/teams-webhook-url.txt").write_text(value)


def test_drift_is_restored_to_the_deployed_config(box):
    result = _run(box)
    assert result.returncode == 0
    assert "Config has drifted" in result.stdout
    assert _live_config(box) == DEPLOYED


def test_a_config_that_matches_the_deployed_sha_alerts_nobody(box):
    (box / "opt/ds01-infra/config/runtime/resource-limits.yaml").write_text(DEPLOYED)
    result = _run(box, DSL_ALERT_TO="h.baker@hertie-school.org")
    assert result.returncode == 0
    assert not (box / "curl.argv").exists()
    assert not (box / "mail.stdin").exists()


# ------------------------------------------------------------------ the webhook guard


def test_the_shipped_placeholder_is_not_a_webhook(box):
    # The bug: the old test rejected `PLACEHOLDER*`, the file says
    # `PASTE_LOGIC_AZURE_URL_HERE`, so the watchdog POSTed drift to a non-URL and
    # logged a WARNING every time instead of skipping a channel it never had.
    _webhook_file(box, "PASTE_LOGIC_AZURE_URL_HERE\n")
    result = _run(box)
    assert not (box / "curl.argv").exists()
    assert "WARNING: Teams drift alert POST failed" not in result.stdout
    assert _live_config(box) == DEPLOYED


def test_an_https_webhook_is_posted_to(box):
    _webhook_file(box, "https://prod-1.logic.azure.com/workflows/abc\n")
    result = _run(box)
    assert result.returncode == 0
    assert "https://prod-1.logic.azure.com/workflows/abc" in (box / "curl.argv").read_text()


def test_a_failed_post_does_not_fail_the_watchdog(box):
    # An alerter must not become the outage: the restore still has to happen.
    _webhook_file(box, "https://prod-1.logic.azure.com/workflows/abc\n")
    result = _run(box, STUB_CURL_RC="7")
    assert result.returncode == 0
    assert "WARNING: Teams drift alert POST failed" in result.stdout
    assert _live_config(box) == DEPLOYED


# -------------------------------------------------------------------- the mail channel


def test_drift_is_mailed_with_the_diff_on_stdin(box):
    result = _run(box, DSL_ALERT_TO="h.baker@hertie-school.org")
    assert result.returncode == 0
    argv = (box / "python3.argv").read_text()
    assert "dsl-alert-mail.py" in argv
    assert "[ds01] config drift on" in argv
    body = (box / "mail.stdin").read_text()
    assert "config/runtime/resource-limits.yaml differs from deployed" in body
    # The diff rides on stdin, never argv: /proc on this box is world-readable.
    assert "max_per_user: 8" in body
    assert "max_per_user: 8" not in argv


def test_mail_goes_even_when_teams_is_unconfigured(box):
    # Two independent channels, exactly as dsl-alert.sh has it.
    _webhook_file(box, "PASTE_LOGIC_AZURE_URL_HERE\n")
    _run(box, DSL_ALERT_TO="h.baker@hertie-school.org")
    assert not (box / "curl.argv").exists()
    assert (box / "mail.stdin").exists()


def test_a_failing_mailer_does_not_fail_the_watchdog(box):
    result = _run(box, DSL_ALERT_TO="h.baker@hertie-school.org", STUB_MAIL_RC="1")
    assert result.returncode == 0
    assert "WARNING: mail drift alert failed" in result.stdout
    assert _live_config(box) == DEPLOYED


def test_an_unprovisioned_box_says_nothing_on_either_channel(box):
    result = _run(box)
    assert result.returncode == 0
    assert not (box / "curl.argv").exists()
    assert not (box / "mail.stdin").exists()
    assert "WARNING" not in result.stdout.replace("WARNING: Config has drifted", "")


def test_the_env_file_alone_makes_the_watchdog_try_to_mail(box):
    # The cron case: the environment carries nothing, but /etc/dsl-alert-mail.env
    # exists and the mailer reads it itself.
    env_file = box / "mail.env"
    env_file.write_text("DSL_ALERT_TO=h.baker@hertie-school.org\n")
    _run(box, DSL_ALERT_ENV_FILE=str(env_file))
    assert "dsl-alert-mail.py" in (box / "python3.argv").read_text()
