#!/usr/bin/env python3
"""dsl-alert-mail.py <subject> [body] - mail one alert through Microsoft Graph.

The mail channel of `dsl-alert.sh`. Teams is a webhook this box may or may not have;
this is the channel that reaches a human who is not looking at the journal.

One transport, Microsoft Graph (application auth, certificate credential). There is
deliberately no SMTP fallback: the tenant disables SMTP AUTH, so a fallback could never
fire, and an alerter with a second untested send path is an alerter that fails silently.

Configured entirely from the environment, so the credential lives in one root-only file
(`/etc/dsl-alert-mail.env`, EnvironmentFile of `dsl-alert@.service`) and never in the repo:

    GRAPH_TENANT_ID        the Entra tenant
    GRAPH_CLIENT_ID        the lab's app registration
    GRAPH_SENDER           mailbox to send as, e.g. datasciencelab@hertie-school.org
    GRAPH_CLIENT_CERT_FILE PEM holding the certificate then its unencrypted private key,
                           the same content as the toolkit's GRAPH_CLIENT_CERT secret
    DSL_ALERT_TO           where the alert goes

The credential is a certificate, not a secret: the token request sends a thumbprint that
identifies the certificate and a signature made by the matching key, both derived from the
one PEM, so the two halves cannot drift apart. Entra never sees the private key.

Provisioning steps are in docs/admin/maintenance.md. Body on stdin, not argv: `/proc` on
this box is world-readable, so anything on a command line is visible in `ps`.

Prints status codes and one-line outcomes only. Never a token, and never a response body -
a Graph error body echoes the request back, recipient included.
"""

from __future__ import annotations

import base64
import http.client
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from dataclasses import dataclass
from pathlib import Path

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

_AUTHORITY = "https://login.microsoftonline.com"
_GRAPH = "https://graph.microsoft.com/v1.0"
_SCOPE = "https://graph.microsoft.com/.default"
_ASSERTION_TYPE = "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
# The assertion is single-use and consumed immediately; a short life caps the replay window.
_ASSERTION_TTL = 300

MAIL_ENV = (
    "GRAPH_TENANT_ID",
    "GRAPH_CLIENT_ID",
    "GRAPH_SENDER",
    "GRAPH_CLIENT_CERT_FILE",
    "DSL_ALERT_TO",
)
# Every one of these is interpolated into a URL, a header or a JSON address field.
_SINGLE_LINE = ("GRAPH_TENANT_ID", "GRAPH_CLIENT_ID", "GRAPH_SENDER", "DSL_ALERT_TO")

# Graph answers a throttled or briefly-unhealthy request with one of these and, on a 429,
# a Retry-After. One retry only: this is an alert about an outage, not a mail merge, and a
# second failure is itself worth reporting.
_RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
_MAX_SEND_ATTEMPTS = 2
_RETRY_AFTER_DEFAULT = 5.0  # when the header is absent or unreadable
_RETRY_AFTER_CAP = 60.0  # a header we cannot vet must not park the unit
_TIMEOUT = 20


@dataclass
class Config:
    tenant_id: str
    client_id: str
    sender: str
    cert_file: str
    to: str


def log(msg: str) -> None:
    print(msg, flush=True)


def mask_email(addr: str) -> str:
    """`a***@domain` - enough to tell two recipients apart in the journal, not enough to
    identify either. The journal of a failed unit is posted to Teams."""
    local, _, domain = addr.partition("@")
    return f"{local[:1]}***@{domain}" if domain else f"{local[:1]}***"


def config_from_env() -> Config | None:
    """Build the config from the environment, or None if it is unusable.

    Names the variables at fault rather than saying "not configured": the values are a
    root-only file nobody can read back from a journal line, so a blanket message is
    undebuggable. A partly-filled env is a misconfiguration, not an absence - the caller
    only runs this once DSL_ALERT_TO is set."""
    found = {k: (os.environ.get(k) or "").strip() for k in MAIL_ENV}
    missing = [k for k, v in found.items() if not v]
    if missing:
        log(f"mail alert not configured - unset or blank: {', '.join(missing)}")
        return None
    ragged = [k for k in _SINGLE_LINE if any(c.isspace() for c in found[k])]
    if ragged:
        log(f"mail alert misconfigured - whitespace inside {', '.join(ragged)}")
        return None
    return Config(
        tenant_id=found["GRAPH_TENANT_ID"],
        client_id=found["GRAPH_CLIENT_ID"],
        sender=found["GRAPH_SENDER"],
        cert_file=found["GRAPH_CLIENT_CERT_FILE"],
        to=found["DSL_ALERT_TO"],
    )


def _b64url(raw: bytes) -> str:
    """Unpadded base64url - what JWS uses for every segment."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _load_cert_and_key(cert_file: str) -> tuple[x509.Certificate, rsa.RSAPrivateKey]:
    """Parse the PEM file into (certificate, private key).

    Raises RuntimeError, not the library's own errors: a malformed credential should read
    as one actionable journal line, not a cryptography traceback out of an alerter."""
    try:
        raw = Path(cert_file).read_bytes()
    except OSError as exc:
        raise RuntimeError(f"GRAPH_CLIENT_CERT_FILE unreadable: {exc}") from exc
    try:
        cert = x509.load_pem_x509_certificate(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"{cert_file} has no readable PEM certificate ({exc}). It must hold the "
            f"certificate AND its private key, as `cat cert.cer key.pem` produces."
        ) from exc
    try:
        key = serialization.load_pem_private_key(raw, password=None)
    except (ValueError, TypeError) as exc:
        # TypeError is what cryptography raises for an ENCRYPTED key given no password -
        # a passphrase can never work here, since no one can type one into a systemd unit.
        raise RuntimeError(
            f"{cert_file} has no usable PEM private key ({exc}). The key must be in the "
            f"same file and must not be passphrase-protected."
        ) from exc
    if not isinstance(key, rsa.RSAPrivateKey):
        raise RuntimeError(  # noqa: TRY004
            f"{cert_file} holds a {type(key).__name__} private key; Entra app certificate "
            f"credentials must be RSA."
        )
    return cert, key


def _client_assertion(cfg: Config) -> str:
    """A JWT signed by the app's private key, standing in for a client secret.

    Entra looks the public half up by the `x5t` thumbprint in the header, then checks the
    signature against it. `x5t` is SHA-1 because the protocol says so - it is a certificate
    IDENTIFIER, not a security control; the signature itself is RS256 (SHA-256)."""
    cert, key = _load_cert_and_key(cfg.cert_file)
    now = int(time.time())
    header = {
        "alg": "RS256",
        "typ": "JWT",
        "x5t": _b64url(cert.fingerprint(hashes.SHA1())),  # identifier only, see docstring
    }
    claims = {
        "aud": f"{_AUTHORITY}/{cfg.tenant_id}/oauth2/v2.0/token",
        "iss": cfg.client_id,
        "sub": cfg.client_id,
        "jti": str(uuid.uuid4()),
        "nbf": now,
        "exp": now + _ASSERTION_TTL,
    }
    signing_input = ".".join(
        _b64url(json.dumps(part, separators=(",", ":")).encode()) for part in (header, claims)
    )
    signature = key.sign(signing_input.encode(), padding.PKCS1v15(), hashes.SHA256())
    return f"{signing_input}.{_b64url(signature)}"


def _response_headers(raw) -> dict[str, str]:
    """A response's headers as a lower-cased dict (HTTP header names are case-insensitive,
    and `Retry-After` arrives spelled however the server felt like spelling it)."""
    try:
        return {k.lower(): v for k, v in raw.items()}
    except AttributeError:
        return {}


def _post(url: str, data: bytes, headers: dict[str, str]) -> tuple[int, bytes, dict]:
    """POST and return (status, body, response headers); network and HTTP errors come back
    as a status, so no caller has to handle an exception to see a failure."""
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as resp:
            return resp.status, resp.read(), _response_headers(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read(), _response_headers(exc.headers)
    except urllib.error.URLError as exc:
        return 0, str(exc.reason).encode(), {}
    except (http.client.HTTPException, ValueError, TimeoutError) as exc:
        return 0, str(exc).encode(), {}


def retry_after_seconds(headers: dict[str, str]) -> float:
    """How long `Retry-After` asks us to wait, in seconds - capped, and defaulted when the
    header is missing or is the HTTP-date form we do not parse."""
    raw = (headers.get("retry-after") or "").strip()
    try:
        wait = float(raw)
    except ValueError:
        return _RETRY_AFTER_DEFAULT
    return min(max(wait, 0.0), _RETRY_AFTER_CAP)


def graph_token(cfg: Config) -> str | None:
    """A client-credentials access token for Graph, or None on failure."""
    url = f"{_AUTHORITY}/{cfg.tenant_id}/oauth2/v2.0/token"
    body = urllib.parse.urlencode(
        {
            "client_id": cfg.client_id,
            "client_assertion_type": _ASSERTION_TYPE,
            "client_assertion": _client_assertion(cfg),
            "scope": _SCOPE,
            "grant_type": "client_credentials",
        }
    ).encode()
    status, raw, _headers = _post(url, body, {"Content-Type": "application/x-www-form-urlencoded"})
    if status != 200:
        # Status only: an Entra error body quotes the assertion back.
        log(f"Graph token request failed ({status})")
        return None
    try:
        token = json.loads(raw).get("access_token")
    except ValueError:
        token = None
    if not token:
        log("Graph token response carried no access_token")
        return None
    return token


def send_mail(cfg: Config, token: str, subject: str, body: str) -> bool:
    """Send one plain-text message as `sender`. Returns True on 200/202."""
    url = f"{_GRAPH}/users/{urllib.parse.quote(cfg.sender)}/sendMail"
    payload = json.dumps(
        {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": cfg.to}}],
            },
            # Nothing reads the shared mailbox's Sent Items, and an outage can mean one
            # alert per tick.
            "saveToSentItems": False,
        }
    ).encode()
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    for attempt in range(1, _MAX_SEND_ATTEMPTS + 1):
        status, _raw, response_headers = _post(url, payload, headers)
        if status in (200, 202):
            log(f"alert mailed to {mask_email(cfg.to)} ({status})")
            return True
        if status in _RETRY_STATUSES and attempt < _MAX_SEND_ATTEMPTS:
            # A throttle or a brief 5xx is Graph asking to be asked again, not a bad
            # recipient. One more try, then report it.
            wait = retry_after_seconds(response_headers)
            log(f"send got {status}, retrying once in {wait:g}s")
            time.sleep(wait)
            continue
        # Status only: a Graph error body echoes the message, recipient included.
        log(f"send to {mask_email(cfg.to)} failed ({status})")
        return False
    return False


def main(argv: list[str]) -> int:
    if not argv:
        log("usage: dsl-alert-mail.py <subject> [body]   (body otherwise read from stdin)")
        return 1
    subject = argv[0]
    body = argv[1] if len(argv) > 1 else sys.stdin.read()

    cfg = config_from_env()
    if cfg is None:
        return 1
    try:
        token = graph_token(cfg)
    except RuntimeError as exc:
        log(f"mail alert failed: {exc}")
        return 1
    if token is None:
        return 1
    return 0 if send_mail(cfg, token, subject, body) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
