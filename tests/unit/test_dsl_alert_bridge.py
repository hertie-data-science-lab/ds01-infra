"""Unit tests for the Alertmanager-to-mail bridge.

The bridge is the one piece of this mail stack that LISTENS, on a port every
account on the box can reach, and that sends mail as the lab when it is asked to.
So the tests that matter are about who is allowed to ask.

The HTTP half runs a real server on loopback and talks to it with the stdlib -
nothing leaves the machine, and `deliver` is replaced, so no test can reach Graph.
"""

import json
import threading
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
BRIDGE = REPO / "scripts/maintenance/dsl-alert-bridge.py"

TOKEN = "3f7c" * 16

FIRING = {
    "receiver": "ds01-teams",
    "status": "firing",
    "commonLabels": {"alertname": "DS01ExporterDown", "severity": "critical"},
    "alerts": [
        {
            "status": "firing",
            "labels": {"alertname": "DS01ExporterDown", "severity": "critical", "job": "ds01"},
            "annotations": {
                "summary": "ds01-exporter is not responding",
                "description": "No scrape for 5m",
            },
            "startsAt": "2026-09-16T04:00:00Z",
            "generatorURL": "http://localhost:9090/graph?g0.expr=up",
        }
    ],
}


@pytest.fixture(scope="module")
def bridge():
    """The script imported as a module - its name has a hyphen, so no plain import."""
    import importlib.util
    import sys

    spec = importlib.util.spec_from_file_location("dsl_alert_bridge", BRIDGE)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


# ---------------------------------------------------------------------- the bearer token


def test_a_missing_token_file_refuses_to_start(bridge, monkeypatch, tmp_path, capsys):
    # There is no unauthenticated mode. This endpoint mails as the lab, and the port is
    # on a host interface every logged-in user can reach.
    monkeypatch.setenv("DSL_ALERT_BRIDGE_TOKEN_FILE", str(tmp_path / "absent.txt"))
    assert bridge.main() == 1
    assert "refusing to start" in capsys.readouterr().out


def test_an_empty_token_file_refuses_to_start(bridge, monkeypatch, tmp_path, capsys):
    path = tmp_path / "token.txt"
    path.write_text("\n")
    monkeypatch.setenv("DSL_ALERT_BRIDGE_TOKEN_FILE", str(path))
    assert bridge.main() == 1
    assert "refusing to start" in capsys.readouterr().out


def test_the_token_is_read_without_the_newline_an_editor_adds(bridge, tmp_path):
    # Prometheus' own credentials_file strips whitespace; the two sides have to agree.
    path = tmp_path / "token.txt"
    path.write_text(f"{TOKEN}\n")
    assert bridge.read_token(path) == TOKEN


@pytest.mark.parametrize(
    "header",
    [None, "", "Bearer", "Bearer wrong", "Basic " + TOKEN, TOKEN],
)
def test_anything_but_the_bearer_token_is_refused(bridge, header):
    assert bridge.authorised(header, TOKEN) is False


def test_the_bearer_token_is_accepted_however_it_is_cased(bridge):
    assert bridge.authorised(f"Bearer {TOKEN}", TOKEN) is True
    assert bridge.authorised(f"bearer {TOKEN}", TOKEN) is True


# ------------------------------------------------------------------------- the composing


def test_the_subject_names_the_alert_and_its_status(bridge):
    subject, _body = bridge.compose(FIRING)
    # Critical is called out: this is what has to be readable in a phone notification.
    assert subject == "[ds01 CRITICAL] FIRING: DS01ExporterDown"


def test_a_resolved_group_says_so(bridge):
    payload = {**FIRING, "status": "resolved", "commonLabels": {"alertname": "DS01DiskFull"}}
    subject, _body = bridge.compose(payload)
    assert subject == "[ds01] RESOLVED: DS01DiskFull"


def test_a_group_of_several_alerts_is_counted(bridge):
    payload = {**FIRING, "alerts": FIRING["alerts"] * 3}
    subject, _body = bridge.compose(payload)
    assert subject.endswith("(3)")


def test_the_body_carries_what_a_person_needs_to_act(bridge):
    _subject, body = bridge.compose(FIRING)
    assert "ds01-exporter is not responding" in body
    assert "No scrape for 5m" in body
    assert "job=ds01" in body
    assert "http://localhost:9090/graph?g0.expr=up" in body


def test_labels_stay_out_of_the_subject(bridge):
    # An alert's labels on this box can name a user, a container or a path. The subject
    # is the line that ends up in notifications and previews; the body goes to a mailbox.
    payload = {
        "status": "firing",
        "commonLabels": {"alertname": "DS01ContainerOOM"},
        "alerts": [
            {"status": "firing", "labels": {"alertname": "DS01ContainerOOM", "user": "212345"}}
        ],
    }
    subject, body = bridge.compose(payload)
    assert "212345" not in subject
    assert "user=212345" in body


def test_a_payload_with_no_alerts_still_composes(bridge):
    _subject, body = bridge.compose({"status": "firing", "alerts": []})
    assert "no alerts" in body


# ------------------------------------------------------------------------------ the POST


@pytest.fixture
def served(bridge, monkeypatch):
    """A running bridge on loopback, with the mailer replaced. Yields (url, sent)."""
    sent: list[tuple[str, str]] = []
    done = threading.Event()

    def fake_deliver(subject, body):
        sent.append((subject, body))
        done.set()
        return True

    monkeypatch.setattr(bridge, "deliver", fake_deliver)
    monkeypatch.setattr(bridge.Handler, "token", TOKEN)
    server = ThreadingHTTPServer(("127.0.0.1", 0), bridge.Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/alert", sent, done
    finally:
        server.shutdown()
        server.server_close()


def _post(url, payload, token=TOKEN, raw=None):
    data = raw if raw is not None else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            return resp.status
    except urllib.error.HTTPError as exc:
        return exc.code


def test_an_authorised_post_is_accepted_and_mailed(served):
    url, sent, done = served
    assert _post(url, FIRING) == 202
    assert done.wait(5)
    subject, body = sent[0]
    assert subject == "[ds01 CRITICAL] FIRING: DS01ExporterDown"
    assert "No scrape for 5m" in body


def test_an_unauthenticated_post_mails_nothing(served):
    url, sent, _done = served
    assert _post(url, FIRING, token=None) == 401
    assert sent == []


def test_a_wrong_token_mails_nothing(served):
    url, sent, _done = served
    assert _post(url, FIRING, token="0" * 64) == 401
    assert sent == []


def test_a_body_that_is_not_json_is_refused(served):
    url, sent, _done = served
    assert _post(url, None, raw=b"not json") == 400
    assert sent == []


def test_a_json_body_that_is_not_an_object_is_refused(served):
    url, sent, _done = served
    assert _post(url, None, raw=b"[1, 2, 3]") == 400
    assert sent == []


def test_an_empty_body_is_refused(served):
    url, sent, _done = served
    assert _post(url, None, raw=b"") == 400
    assert sent == []


def test_a_get_is_refused(served):
    url, sent, _done = served
    try:
        with urllib.request.urlopen(url, timeout=5) as resp:
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
    assert status == 501
    assert sent == []


# ------------------------------------------------------------------------- the delivery


def test_the_alert_reaches_the_mailer_on_stdin(bridge, monkeypatch):
    calls = []

    class Completed:
        returncode = 0

    monkeypatch.setattr(
        bridge.subprocess, "run", lambda argv, **kw: (calls.append((argv, kw)), Completed())[1]
    )
    assert bridge.deliver("[ds01] FIRING: X", "body with 212345 in it") is True
    argv, kwargs = calls[0]
    assert str(bridge.MAILER) in argv
    assert "[ds01] FIRING: X" in argv
    # On stdin, never argv: /proc on this box is world-readable and an alert body can
    # name a user.
    assert kwargs["input"] == "body with 212345 in it"
    assert not any("212345" in str(arg) for arg in argv)


def test_a_mailer_that_cannot_be_run_is_a_journal_line_not_a_crash(bridge, monkeypatch, capsys):
    def boom(*_args, **_kwargs):
        raise OSError("no such file")

    monkeypatch.setattr(bridge.subprocess, "run", boom)
    assert bridge.deliver("subject", "body") is False
    assert "mail failed" in capsys.readouterr().out
