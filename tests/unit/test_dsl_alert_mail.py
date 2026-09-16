"""Unit tests for the mail channel of the OnFailure alerter.

Two levels. The Python mailer is imported and its one network helper (`_post`) is
replaced, so every assertion is on what would have gone to Entra and to Graph -
the signed assertion, the sendMail body - and on what reached the journal, which
must carry neither the token nor the message. The credential is a throwaway
self-signed certificate generated here; nothing about the real one is needed.

The shell alerter is run for real with `python3` stubbed on PATH, as
test_dsl_scheduled_release.py stubs `gh` and `curl`: what matters is that a
configured recipient reaches the mailer, and that a mailer failure still leaves
the alerter exiting 0.
"""

import base64
import datetime as dt
import importlib.util
import io
import json
import subprocess
import sys
import urllib.parse
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

pytest.importorskip("cryptography", reason="the Graph credential is a certificate")

from cryptography import x509  # noqa: E402
from cryptography.hazmat.primitives import hashes, serialization  # noqa: E402
from cryptography.hazmat.primitives.asymmetric import padding, rsa  # noqa: E402
from cryptography.x509.oid import NameOID  # noqa: E402

REPO = Path(__file__).resolve().parents[2]
MAILER = REPO / "scripts/maintenance/dsl-alert-mail.py"
ALERTER = REPO / "scripts/maintenance/dsl-alert.sh"

TENANT = "11111111-1111-1111-1111-111111111111"
CLIENT = "22222222-2222-2222-2222-222222222222"
SENDER = "datasciencelab@hertie-school.org"
TO = "h.baker@hertie-school.org"
TOKEN = "eyJ_stub_access_token_sentinel"
BODY = "Sep 04 12:00:00 ds01 dsl-scheduled-release[1]: failing SENTINEL-ORG"

TOKEN_URL = f"https://login.microsoftonline.com/{TENANT}/oauth2/v2.0/token"
SEND_URL = f"https://graph.microsoft.com/v1.0/users/{urllib.parse.quote(SENDER)}/sendMail"


@pytest.fixture(scope="module")
def mailer():
    """The script imported as a module - its name has a hyphen, so no plain import."""
    spec = importlib.util.spec_from_file_location("dsl_alert_mail", MAILER)
    mod = importlib.util.module_from_spec(spec)
    # In sys.modules before exec: @dataclass resolves annotations through it.
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def credential(tmp_path_factory):
    """A throwaway self-signed certificate + key, as one PEM, like the real secret."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "dsl-alert-test")])
    now = dt.datetime.now(dt.timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - dt.timedelta(days=1))
        .not_valid_after(now + dt.timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    pem = cert.public_bytes(serialization.Encoding.PEM) + key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    path = tmp_path_factory.mktemp("cred") / "graph.pem"
    path.write_bytes(pem)
    return path, cert


@pytest.fixture
def env(monkeypatch, credential):
    """A fully-configured environment; a test unsets what it wants missing."""
    path, _cert = credential
    for key, value in (
        ("GRAPH_TENANT_ID", TENANT),
        ("GRAPH_CLIENT_ID", CLIENT),
        ("GRAPH_SENDER", SENDER),
        ("GRAPH_CLIENT_CERT_FILE", str(path)),
        ("DSL_ALERT_TO", TO),
        # Point the env-file fallback at nothing: these tests must describe the
        # environment they set up, not whatever /etc/dsl-alert-mail.env says on the box
        # they happen to run on.
        ("DSL_ALERT_ENV_FILE", "/nonexistent/dsl-alert-mail.env"),
    ):
        monkeypatch.setenv(key, value)


@pytest.fixture
def posts(mailer, monkeypatch):
    """Capture every POST; `posts.replies` queues (status, headers) by URL."""

    class Recorder(list):
        replies = {}

        def __call__(self, url, data, headers):
            self.append({"url": url, "data": data, "headers": headers})
            queue = self.replies.get(url, [(200, {})])
            status, response_headers = queue[0] if len(queue) == 1 else queue.pop(0)
            body = json.dumps({"access_token": TOKEN}).encode() if url == TOKEN_URL else b""
            return status, body, response_headers

        def to(self, url):
            return [call for call in self if call["url"] == url]

    recorder = Recorder()
    recorder.replies = {TOKEN_URL: [(200, {})], SEND_URL: [(202, {})]}
    monkeypatch.setattr(mailer, "_post", recorder)
    monkeypatch.setattr(mailer.time, "sleep", lambda _seconds: None)
    return recorder


def _unb64(part: str) -> bytes:
    return base64.urlsafe_b64decode(part + "=" * (-len(part) % 4))


def _assertion(posts):
    """The client assertion the mailer sent to Entra, split into its JWT parts."""
    form = urllib.parse.parse_qs(posts.to(TOKEN_URL)[0]["data"].decode())
    jwt = form["client_assertion"][0]
    header, claims, _signature = jwt.split(".")
    return json.loads(_unb64(header)), json.loads(_unb64(claims)), jwt


def _sent(posts):
    return json.loads(posts.to(SEND_URL)[0]["data"])


# ------------------------------------------------------------------ the token request


def test_the_assertion_is_signed_rs256_and_identifies_the_certificate(
    mailer, env, posts, credential
):
    _path, cert = credential
    assert mailer.main(["subject", BODY]) == 0
    header, _claims, _jwt = _assertion(posts)
    assert header["alg"] == "RS256"
    # x5t is the SHA-1 thumbprint, unpadded base64url - how Entra finds the public half.
    expected = base64.urlsafe_b64encode(cert.fingerprint(hashes.SHA1())).rstrip(b"=").decode()
    assert header["x5t"] == expected


def test_the_assertion_is_addressed_to_the_tenant_and_issued_by_the_app(mailer, env, posts):
    assert mailer.main(["subject", BODY]) == 0
    _header, claims, _jwt = _assertion(posts)
    assert claims["aud"] == TOKEN_URL
    assert claims["iss"] == CLIENT
    assert claims["sub"] == CLIENT
    assert claims["exp"] > claims["nbf"]


def test_the_signature_verifies_against_the_certificate(mailer, env, posts, credential):
    # Proves the signed input is the header.claims pair Entra will check, not just
    # that something was signed.
    _path, cert = credential
    assert mailer.main(["subject", BODY]) == 0
    _header, _claims, jwt = _assertion(posts)
    signing_input, _, signature = jwt.rpartition(".")
    cert.public_key().verify(
        _unb64(signature), signing_input.encode(), padding.PKCS1v15(), hashes.SHA256()
    )


def test_a_refused_token_request_sends_nothing(mailer, env, posts, capsys):
    posts.replies[TOKEN_URL] = [(401, {})]
    assert mailer.main(["subject", BODY]) == 1
    assert posts.to(SEND_URL) == []
    assert "401" in capsys.readouterr().out


# ---------------------------------------------------------------------- the sendMail


def test_the_message_goes_from_the_sender_to_the_recipient(mailer, env, posts):
    assert mailer.main(["[ds01] dsl-scheduled-release.service failed", BODY]) == 0
    call = posts.to(SEND_URL)[0]
    assert call["url"] == SEND_URL  # the sender mailbox, not /me
    assert call["headers"]["Authorization"] == f"Bearer {TOKEN}"
    message = _sent(posts)["message"]
    assert message["toRecipients"] == [{"emailAddress": {"address": TO}}]
    assert message["subject"] == "[ds01] dsl-scheduled-release.service failed"
    assert message["body"] == {"contentType": "Text", "content": BODY}


def test_the_alert_is_not_kept_in_sent_items(mailer, env, posts):
    # Nobody reads that mailbox, and an outage can mean one alert per tick.
    assert mailer.main(["subject", BODY]) == 0
    assert _sent(posts)["saveToSentItems"] is False


def test_the_body_is_read_from_stdin_when_not_given(mailer, env, posts, monkeypatch):
    monkeypatch.setattr(mailer.sys, "stdin", io.StringIO(BODY))
    assert mailer.main(["subject"]) == 0
    assert _sent(posts)["message"]["body"]["content"] == BODY


def test_a_rejected_send_exits_one(mailer, env, posts, capsys):
    posts.replies[SEND_URL] = [(403, {})]
    assert mailer.main(["subject", BODY]) == 1
    assert "403" in capsys.readouterr().out


def test_a_throttled_send_is_retried_once(mailer, env, posts, capsys):
    posts.replies[SEND_URL] = [(429, {"retry-after": "1"}), (202, {})]
    assert mailer.main(["subject", BODY]) == 0
    assert len(posts.to(SEND_URL)) == 2
    assert "retrying once in 1s" in capsys.readouterr().out


def test_a_second_failure_is_not_retried_again(mailer, env, posts):
    posts.replies[SEND_URL] = [(503, {}), (503, {})]
    assert mailer.main(["subject", BODY]) == 1
    assert len(posts.to(SEND_URL)) == 2


def test_an_unreadable_retry_after_falls_back_to_the_default(mailer, env, posts):
    # Graph may answer with the HTTP-date form, which we do not parse.
    assert mailer.retry_after_seconds({"retry-after": "Wed, 21 Oct 2026 07:28:00 GMT"}) == 5.0
    assert mailer.retry_after_seconds({"retry-after": "9999"}) == 60.0


# ------------------------------------------------------------------- what is logged


def test_neither_the_token_nor_the_message_reaches_the_journal(
    mailer, env, posts, capsys, credential
):
    # The journal of a failed unit is itself posted to Teams.
    path, _cert = credential
    assert mailer.main(["subject", BODY]) == 0
    out = capsys.readouterr()
    printed = out.out + out.err
    assert TOKEN not in printed
    assert "SENTINEL-ORG" not in printed
    assert path.read_text() not in printed
    assert TO not in printed
    assert "h***@hertie-school.org (202)" in out.out


# ----------------------------------------------------------------------- the config


@pytest.mark.parametrize("missing", ["GRAPH_TENANT_ID", "GRAPH_SENDER", "GRAPH_CLIENT_CERT_FILE"])
def test_a_half_configured_env_names_the_missing_variable(
    mailer, env, posts, capsys, monkeypatch, missing
):
    # The values are a root-only file no journal line can quote back, so "not
    # configured" alone would be undebuggable.
    monkeypatch.delenv(missing)
    assert mailer.main(["subject", BODY]) == 1
    assert missing in capsys.readouterr().out
    assert posts == []


def test_whitespace_in_an_interpolated_value_is_refused_by_name(
    mailer, env, posts, capsys, monkeypatch
):
    # tenant_id goes into the token URL, where a newline raises InvalidURL.
    monkeypatch.setenv("GRAPH_TENANT_ID", f"{TENANT}\n{TENANT}")
    assert mailer.main(["subject", BODY]) == 1
    assert "GRAPH_TENANT_ID" in capsys.readouterr().out
    assert posts == []


def test_a_malformed_credential_is_one_line_not_a_traceback(
    mailer, env, posts, capsys, monkeypatch, tmp_path
):
    bad = tmp_path / "not.pem"
    # Assembled, not written out: a literal PEM header in a tracked file trips
    # secret scanners.
    rule = "-" * 5
    bad.write_text(f"{rule}BEGIN CERTIFICATE{rule}\nnope\n{rule}END CERTIFICATE{rule}\n")
    monkeypatch.setenv("GRAPH_CLIENT_CERT_FILE", str(bad))
    assert mailer.main(["subject", BODY]) == 1
    assert "no readable PEM certificate" in capsys.readouterr().out
    assert posts == []


def test_a_missing_credential_file_is_reported(mailer, env, posts, capsys, monkeypatch, tmp_path):
    monkeypatch.setenv("GRAPH_CLIENT_CERT_FILE", str(tmp_path / "absent.pem"))
    assert mailer.main(["subject", BODY]) == 1
    assert "GRAPH_CLIENT_CERT_FILE unreadable" in capsys.readouterr().out


def test_no_subject_is_a_usage_line(mailer, env, posts, capsys):
    assert mailer.main([]) == 1
    assert "usage" in capsys.readouterr().out


# ------------------------------------------------------ recipients, Cc and the archive


def _addresses(message, line):
    return [r["emailAddress"]["address"] for r in message.get(line, [])]


def test_a_comma_separated_to_reaches_everyone_named(mailer, env, posts, monkeypatch):
    monkeypatch.setenv("DSL_ALERT_TO", f"{TO}, second@hertie-school.org")
    assert mailer.main(["subject", BODY]) == 0
    # One POST, not one per recipient: the text is identical for all of them.
    assert len(posts.to(SEND_URL)) == 1
    assert _addresses(_sent(posts)["message"], "toRecipients") == [
        TO,
        "second@hertie-school.org",
    ]


def test_the_archive_cc_rides_on_every_alert(mailer, env, posts, monkeypatch):
    monkeypatch.setenv("DSL_ALERT_CC", SENDER)
    assert mailer.main(["subject", BODY]) == 0
    assert _addresses(_sent(posts)["message"], "ccRecipients") == [SENDER]


def test_no_cc_line_is_sent_when_nothing_is_copied(mailer, env, posts):
    assert mailer.main(["subject", BODY]) == 0
    assert "ccRecipients" not in _sent(posts)["message"]


def test_a_cc_flag_adds_to_the_archive_rather_than_replacing_it(mailer, env, posts, monkeypatch):
    # The whole point of the asymmetry: a ticket notifier names the person who opened the
    # ticket, and must not be able to drop the mailbox that keeps the record.
    monkeypatch.setenv("DSL_ALERT_CC", SENDER)
    assert mailer.main(["--cc", "student@students.hertie-school.org", "subject", BODY]) == 0
    assert _addresses(_sent(posts)["message"], "ccRecipients") == [
        SENDER,
        "student@students.hertie-school.org",
    ]


def test_a_to_flag_replaces_the_environment(mailer, env, posts):
    assert mailer.main(["--to", "someone@hertie-school.org", "subject", BODY]) == 0
    assert _addresses(_sent(posts)["message"], "toRecipients") == ["someone@hertie-school.org"]


def test_an_address_on_both_lines_gets_one_copy(mailer, env, posts, monkeypatch):
    monkeypatch.setenv("DSL_ALERT_CC", TO)
    assert mailer.main(["--cc", TO, "subject", BODY]) == 0
    message = _sent(posts)["message"]
    assert _addresses(message, "toRecipients") == [TO]
    assert "ccRecipients" not in message


def test_a_malformed_cc_is_dropped_and_the_alert_still_goes(mailer, env, posts, capsys):
    # Graph rejects the whole message for one bad recipient, and the Cc can carry whatever
    # a public web form collected - so one typo must not cost the notification itself.
    assert mailer.main(["--cc", "not-an-address", "subject", BODY]) == 0
    assert "ccRecipients" not in _sent(posts)["message"]
    out = capsys.readouterr().out
    assert "dropped" in out
    assert "not-an-address" not in out  # masked, like every other address


def test_a_malformed_to_sends_nothing(mailer, env, posts, capsys, monkeypatch):
    # The To line is ours, from a file we control: a bad address there is a
    # misconfiguration, and delivering to the rest would quietly send less than was asked.
    monkeypatch.setenv("DSL_ALERT_TO", f"{TO},nonsense")
    assert mailer.main(["subject", BODY]) == 1
    assert posts.to(SEND_URL) == []
    assert "unusable" in capsys.readouterr().out


# ---------------------------------------------------------- the certificate, two ways


def test_the_certificate_can_arrive_as_a_value_not_a_file(
    mailer, env, posts, monkeypatch, credential
):
    # How it arrives in GitHub Actions, where a secret is a value and not a file.
    path, _cert = credential
    monkeypatch.delenv("GRAPH_CLIENT_CERT_FILE")
    monkeypatch.setenv("GRAPH_CLIENT_CERT", path.read_text())
    assert mailer.main(["subject", BODY]) == 0
    assert _sent(posts)["message"]["subject"] == "subject"


def test_both_certificate_variables_set_is_refused(
    mailer, env, posts, monkeypatch, credential, capsys
):
    # Two credentials in one environment is a rotation that went half-finished; picking a
    # winner would hide it.
    path, _cert = credential
    monkeypatch.setenv("GRAPH_CLIENT_CERT", path.read_text())
    assert mailer.main(["subject", BODY]) == 1
    assert posts.to(SEND_URL) == []
    assert "exactly one" in capsys.readouterr().out


def test_neither_certificate_variable_set_is_refused(mailer, env, posts, monkeypatch, capsys):
    monkeypatch.delenv("GRAPH_CLIENT_CERT_FILE")
    assert mailer.main(["subject", BODY]) == 1
    assert "exactly one" in capsys.readouterr().out


# ------------------------------------------------------------------------ HTML bodies


def test_html_is_sent_as_html(mailer, env, posts):
    # The monthly report's heatmap and bar chart are ASCII; only a <pre> keeps them aligned.
    assert mailer.main(["--html", "subject", "<pre>chart</pre>"]) == 0
    assert _sent(posts)["message"]["body"] == {
        "contentType": "HTML",
        "content": "<pre>chart</pre>",
    }


def test_the_body_is_plain_text_by_default(mailer, env, posts):
    assert mailer.main(["subject", BODY]) == 0
    assert _sent(posts)["message"]["body"]["contentType"] == "Text"


# ------------------------------------------ the env file, for a caller systemd did not start


def _env_file(tmp_path, monkeypatch, text: str):
    path = tmp_path / "dsl-alert-mail.env"
    path.write_text(text)
    monkeypatch.setenv("DSL_ALERT_ENV_FILE", str(path))
    return path


def test_the_env_file_fills_a_variable_systemd_did_not_set(
    mailer, env, posts, monkeypatch, tmp_path
):
    # config-watchdog.sh and ds01-monthly-report run from CRON, which inherits nothing
    # from dsl-alert@.service's EnvironmentFile. Without this they would be configured
    # under systemd and unconfigured on a schedule.
    monkeypatch.delenv("DSL_ALERT_TO")
    _env_file(tmp_path, monkeypatch, f"# the mail channel\nDSL_ALERT_TO={TO}\n")
    assert mailer.main(["subject", BODY]) == 0
    assert _addresses(_sent(posts)["message"], "toRecipients") == [TO]


def test_the_environment_wins_over_the_env_file(mailer, env, posts, monkeypatch, tmp_path):
    # A one-off `DSL_ALERT_TO=... ` in front of the command has to keep meaning what it says.
    _env_file(tmp_path, monkeypatch, "DSL_ALERT_TO=file@hertie-school.org\n")
    assert mailer.main(["subject", BODY]) == 0
    assert _addresses(_sent(posts)["message"], "toRecipients") == [TO]


def test_quotes_and_an_export_prefix_are_accepted(mailer, env, posts, monkeypatch, tmp_path):
    # The subset systemd's own EnvironmentFile accepts, which is what an admin who has
    # written one before will type.
    monkeypatch.delenv("DSL_ALERT_TO")
    monkeypatch.delenv("DSL_ALERT_CC", raising=False)
    _env_file(
        tmp_path,
        monkeypatch,
        f"export DSL_ALERT_TO='{TO}'\nDSL_ALERT_CC=\"{SENDER}\"\n",
    )
    assert mailer.main(["subject", BODY]) == 0
    message = _sent(posts)["message"]
    assert _addresses(message, "toRecipients") == [TO]
    assert _addresses(message, "ccRecipients") == [SENDER]


def test_the_env_file_cannot_set_anything_but_the_mail_variables(
    mailer, env, posts, monkeypatch, tmp_path
):
    # The threat is not a hostile line in a root-only file - it is a stray PATH= an admin
    # left in it, and a mailer that quietly rewrote its own PATH would be very hard to
    # explain. Which is also why the file is parsed and never sourced.
    monkeypatch.setenv("PATH", "/usr/bin")
    _env_file(tmp_path, monkeypatch, "PATH=/tmp/evil\nLD_PRELOAD=/tmp/evil.so\n")
    assert mailer.main(["subject", BODY]) == 0
    assert mailer.os.environ["PATH"] == "/usr/bin"
    assert "LD_PRELOAD" not in mailer.os.environ


def test_an_absent_env_file_is_a_silent_no_op(mailer, env, posts, monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("DSL_ALERT_ENV_FILE", str(tmp_path / "absent.env"))
    assert mailer.main(["subject", BODY]) == 0
    assert "absent.env" not in capsys.readouterr().out


# ------------------------------------------------------- the shell alerter's mail path


PYTHON3_STUB = """#!/bin/bash
printf '%s\\n' "$@" >>"$STUB_DIR/argv.log"
cat >>"$STUB_DIR/stdin.log"
exit ${STUB_MAIL_RC:-0}
"""

JOURNALCTL_STUB = """#!/bin/bash
echo "Sep 04 12:00:00 ds01 unit[1]: SENTINEL-JOURNAL-LINE"
"""


def _alert(tmp_path, **env):
    """Run the alerter with python3 and journalctl stubbed, and no Teams webhook."""
    stub = tmp_path / "bin"
    stub.mkdir()
    for name, body in (("python3", PYTHON3_STUB), ("journalctl", JOURNALCTL_STUB)):
        path = stub / name
        path.write_text(body)
        path.chmod(0o755)
    return subprocess.run(
        ["bash", str(ALERTER), "dsl-scheduled-release.service"],
        capture_output=True,
        text=True,
        env={
            "PATH": f"{stub}:/usr/bin:/bin",
            "STUB_DIR": str(tmp_path),
            "DS01_TEAMS_WEBHOOK_URL": "",
            **env,
        },
    )


def test_the_alerter_mails_the_journal_tail_when_a_recipient_is_set(tmp_path):
    result = _alert(tmp_path, DSL_ALERT_TO=TO)
    assert result.returncode == 0
    argv = (tmp_path / "argv.log").read_text()
    assert "scripts/maintenance/dsl-alert-mail.py" in argv
    assert "[ds01] dsl-scheduled-release.service failed" in argv
    # The tail goes on stdin, never argv: /proc here is world-readable.
    assert "SENTINEL-JOURNAL-LINE" in (tmp_path / "stdin.log").read_text()
    assert "SENTINEL-JOURNAL-LINE" not in argv


def test_a_failing_mailer_does_not_fail_the_alerter(tmp_path):
    # An alerter must not become the outage.
    result = _alert(tmp_path, DSL_ALERT_TO=TO, STUB_MAIL_RC="1")
    assert result.returncode == 0
    assert "WARNING: mail alert failed" in result.stdout


def test_no_recipient_and_no_webhook_is_a_journal_only_no_op(tmp_path):
    result = _alert(tmp_path)
    assert result.returncode == 0
    assert "not posted" in result.stdout
    assert not (tmp_path / "argv.log").exists()
