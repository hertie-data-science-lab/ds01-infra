#!/usr/bin/env python3
"""dsl-alert-bridge.py - turn an Alertmanager webhook into a mail through Graph.

Alertmanager can post a webhook; it cannot run a script. So the lab's one mail channel
(`dsl-alert-mail.py`) is put behind the smallest possible HTTP endpoint, and Alertmanager
gets a `webhook_configs` receiver beside its `msteamsv2_configs` one. Two independent
channels on the same alert, the same shape `dsl-alert.sh` and `config-watchdog.sh` have.

Why this exists at all: every Prometheus alert on this box - exporter down, GPU
overheating, disk filling - has only ever gone to a Teams webhook, and that webhook has
never been provisioned (prod's file holds PASTE_LOGIC_AZURE_URL_HERE). Alert delivery from
the monitoring stack is currently zero.

The container reaches this over `host.docker.internal:host-gateway`, exactly as Prometheus
already scrapes the host's ds01-exporter. That means the port is open on the docker bridge,
which is a host interface, which every logged-in user on this box can reach - and unlike a
metrics endpoint, this one SENDS MAIL AS THE LAB. So a bearer token is mandatory: the
bridge refuses to start without one, and there is no unauthenticated mode to fall back to.
Alertmanager reads the same token from the same file, mounted read-only.

    config/runtime/alertmanager-mail-token.txt   git-ignored, 0640, root:65534
                                                 `openssl rand -hex 32`

    Group 65534 is `nobody`, which is what the prom/alertmanager container runs as -
    NOT the `docker` group, which on this box has 21 student accounts in it. That
    distinction is the whole protection: `deploy.sh` chowns it root:65534 for exactly
    this reason, and widening it to a group a user can be in would hand the mail
    channel to everyone in that group.

The token is only an origin check. Anyone who can read the file can make the lab mail
itself an alert; nobody who cannot read it can make the lab mail anything.

The HTTP reply comes BEFORE the mail is sent. Graph is a second network hop with its own
retry, and Alertmanager's notify deadline is not ours to spend - a slow send would look
like a failed webhook and be retried, mailing twice. A send that fails says so in the
journal; the alert is still firing, and `repeat_interval` brings it back.

The journal carries alert NAMES, statuses and counts - never an alert's labels or
annotations, which on this box can name a user, a container or a path.

Run by dsl-alert-bridge.service. Provisioning is in docs/admin/maintenance.md.
"""

from __future__ import annotations

import hmac
import json
import os
import subprocess
import sys
import threading
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

INFRA_ROOT = Path(__file__).resolve().parents[2]
MAILER = INFRA_ROOT / "scripts/maintenance/dsl-alert-mail.py"
DEFAULT_TOKEN_FILE = INFRA_ROOT / "config/runtime/alertmanager-mail-token.txt"

# 0.0.0.0 for the same reason ds01-exporter binds there: the caller is a container, which
# reaches the host over the docker bridge and not over loopback. The bearer token, not the
# bind address, is what makes that safe.
BIND = os.environ.get("DSL_ALERT_BRIDGE_BIND", "0.0.0.0")  # noqa: S104
PORT = int(os.environ.get("DSL_ALERT_BRIDGE_PORT", "9099"))
# An Alertmanager group is a handful of alerts; anything this size is not one of ours.
MAX_BODY = 1 << 20
# Long enough for a token request plus a send with one retry, and short enough that a
# wedged Graph cannot pile threads up until the next alert group arrives.
MAIL_TIMEOUT = 120


def log(msg: str) -> None:
    print(msg, flush=True)


def read_token(path: Path) -> str | None:
    """The shared secret, or None when there is not one to read.

    Whitespace-stripped, because Prometheus' own `credentials_file` strips it and the two
    sides have to agree about a trailing newline an editor adds on save."""
    try:
        token = path.read_text().strip()
    except OSError as exc:
        log(f"token file unreadable: {exc}")
        return None
    if not token:
        log(f"token file {path} is empty")
        return None
    return token


def authorised(header: str | None, token: str) -> bool:
    """Whether an Authorization header carries our bearer token.

    `compare_digest`, not `==`: the comparison is against a secret, and string equality
    returns as soon as it finds a difference."""
    if not header:
        return False
    scheme, _, credential = header.partition(" ")
    if scheme.lower() != "bearer":
        return False
    return hmac.compare_digest(credential.strip(), token)


def _alert_line(alert: dict) -> str:
    """One alert, as the lines a person needs to act on it."""
    labels = alert.get("labels") or {}
    annotations = alert.get("annotations") or {}
    parts = [f"{labels.get('alertname', 'alert')} [{alert.get('status', '?')}]"]
    for key in ("summary", "description"):
        value = annotations.get(key)
        if value:
            parts.append(f"  {value}")
    detail = ", ".join(f"{k}={v}" for k, v in sorted(labels.items()) if k != "alertname")
    if detail:
        parts.append(f"  {detail}")
    for key, label in (("startsAt", "started"), ("generatorURL", "graph")):
        value = alert.get(key)
        if value:
            parts.append(f"  {label}: {value}")
    return "\n".join(parts)


def compose(payload: dict) -> tuple[str, str]:
    """An Alertmanager webhook payload as (subject, body).

    The subject names the alert and its status, which is what has to be readable in a
    notification on a phone. Everything that could identify a user or a container - every
    label and annotation - stays in the body, which goes to a mailbox rather than a
    journal.

    Plain text, not HTML: unlike the monthly report there is nothing here whose meaning is
    its alignment, and a text alert renders in every client without help."""
    alerts = payload.get("alerts") or []
    status = str(payload.get("status", "firing")).upper()
    common = payload.get("commonLabels") or {}
    names = sorted({(a.get("labels") or {}).get("alertname", "alert") for a in alerts})
    name = common.get("alertname") or (names[0] if len(names) == 1 else "multiple alerts")
    count = f" ({len(alerts)})" if len(alerts) > 1 else ""
    severity = common.get("severity")
    subject = f"[ds01] {status}: {name}{count}"
    if severity == "critical":
        subject = f"[ds01 CRITICAL] {status}: {name}{count}"

    body = [f"Alertmanager receiver: {payload.get('receiver', '?')}", ""]
    body.extend(_alert_line(alert) for alert in alerts)
    if not alerts:
        body.append("(the payload carried no alerts)")
    return subject, "\n\n".join(body) + "\n"


def deliver(subject: str, body: str) -> bool:
    """Hand one composed alert to the mailer.

    A subprocess, like every other caller here: the Graph certificate flow, the recipient
    vetting and the standing archive Cc live in exactly one place. Body on stdin - /proc on
    this box is world-readable, and an alert body can name a user."""
    try:
        result = subprocess.run(
            [sys.executable, str(MAILER), subject],
            input=body,
            text=True,
            timeout=MAIL_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        log(f"mail failed: {exc}")
        return False
    return result.returncode == 0


class Handler(BaseHTTPRequestHandler):
    """POST anything, get a 202 and a mail. Everything else is refused."""

    server_version = "dsl-alert-bridge"
    sys_version = ""
    token = ""

    def log_message(self, fmt: str, *args) -> None:
        """Silence the default access log: it prints the request line and the peer, per
        request, into a journal that dsl-alert.sh can post onwards."""

    def _reply(self, status: HTTPStatus) -> None:
        self.send_response(status)
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler's spelling
        if not authorised(self.headers.get("Authorization"), self.token):
            # No detail: an unauthenticated caller learns only that it was refused.
            log("refused an unauthenticated POST")
            self._reply(HTTPStatus.UNAUTHORIZED)
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 < length <= MAX_BODY:
            log(f"refused a POST with an unusable Content-Length ({length})")
            self._reply(HTTPStatus.BAD_REQUEST)
            return
        raw = self.rfile.read(length)
        try:
            payload = json.loads(raw)
        except ValueError:
            log("refused a POST whose body was not JSON")
            self._reply(HTTPStatus.BAD_REQUEST)
            return
        if not isinstance(payload, dict):
            log("refused a POST whose body was not an Alertmanager payload")
            self._reply(HTTPStatus.BAD_REQUEST)
            return

        subject, body = compose(payload)
        # Answered before the mail is sent: Graph is a second network hop, and spending
        # Alertmanager's notify deadline on it would get this webhook retried and the
        # alert mailed twice.
        self._reply(HTTPStatus.ACCEPTED)
        log(f"accepted {subject}")
        threading.Thread(
            target=lambda: log(f"{'mailed' if deliver(subject, body) else 'FAILED'}: {subject}"),
            name="deliver",
        ).start()


def main() -> int:
    token_file = Path(os.environ.get("DSL_ALERT_BRIDGE_TOKEN_FILE") or DEFAULT_TOKEN_FILE)
    token = read_token(token_file)
    if token is None:
        # Refusing to start is the point. There is no unauthenticated mode: this endpoint
        # sends mail as the lab, and every user on this box can reach the port.
        log(f"no bearer token in {token_file} - refusing to start (docs/admin/maintenance.md)")
        return 1
    Handler.token = token
    server = ThreadingHTTPServer((BIND, PORT), Handler)
    log(f"listening on {BIND}:{PORT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
