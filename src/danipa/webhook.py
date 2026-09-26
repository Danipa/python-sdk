"""Danipa webhook signature verification.

Every delivery carries four headers (``MerchantWebhookService``)::

    X-Danipa-Signature: sha256=<lowercase hex HMAC-SHA256>
    X-Danipa-Timestamp: <epoch seconds>
    X-Danipa-Event:     <event type, e.g. payment.completed>
    X-Danipa-Delivery:  <delivery id>

Algorithm: ``signature = "sha256=" + hex(HMAC-SHA256(secret, f"{timestamp}." + body))``
over the RAW request bytes. Verify before parsing: re-serialising parsed JSON
changes the bytes and breaks the signature.

Cross-SDK parity: every Danipa SDK (Node, Java, Python, PHP) MUST produce
identical signatures for the vectors in ``sdks/fixtures/webhook-hmac.json``.
Drift in this file is a release-blocker.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import time
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from danipa.errors import WebhookVerificationError

REPLAY_WINDOW_SECONDS = 300
"""Default maximum age (either direction) of a webhook timestamp: 5 minutes."""

SIGNATURE_HEADER = "X-Danipa-Signature"
TIMESTAMP_HEADER = "X-Danipa-Timestamp"
EVENT_HEADER = "X-Danipa-Event"
DELIVERY_HEADER = "X-Danipa-Delivery"

Payload = bytes | bytearray | memoryview | str
Secrets = str | Sequence[str]


def _as_bytes(payload: Payload) -> bytes:
    if isinstance(payload, str):
        return payload.encode("utf-8")
    return bytes(payload)


def _secret_list(secret: Secrets) -> list[str]:
    if isinstance(secret, str):
        return [secret] if secret else []
    return [s for s in secret if s]


def compute_signature(payload: Payload, secret: str, timestamp_epoch_secs: int) -> str:
    """Return ``sha256=<hex>`` for ``payload`` signed at ``timestamp_epoch_secs``.

    ``payload`` may be the raw body bytes or a ``str`` (encoded as UTF-8).
    """
    signed_content = f"{timestamp_epoch_secs}.".encode() + _as_bytes(payload)
    digest = hmac.new(secret.encode("utf-8"), signed_content, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


def verify(
    payload: Payload,
    signature: str,
    timestamp: str,
    secret: Secrets,
    *,
    tolerance: int = REPLAY_WINDOW_SECONDS,
) -> bool:
    """Verify a webhook signature.

    Parameters
    ----------
    payload:
        The raw request body, as bytes (preferred) or a string. May be empty.
    signature:
        The ``X-Danipa-Signature`` header.
    timestamp:
        The ``X-Danipa-Timestamp`` header (epoch seconds).
    secret:
        The endpoint signing secret, or a list of secrets while rotating: the
        delivery is accepted if ANY of them matches.
    tolerance:
        Maximum age of the timestamp in seconds, either direction. Default 300.

    Returns
    -------
    bool
        ``True`` only if the timestamp is within ``tolerance`` and the signature
        matches one of the secrets; ``False`` for every failure.
    """
    secrets = _secret_list(secret)
    if not signature or not timestamp or not secrets:
        return False
    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False
    if abs(int(time.time()) - ts) > tolerance:
        return False

    body = _as_bytes(payload)
    presented = signature.encode("utf-8")
    matched = False
    for candidate in secrets:
        expected = compute_signature(body, candidate, ts).encode("utf-8")
        # compare every secret (no early exit) so timing does not reveal which one matched
        matched = hmac.compare_digest(expected, presented) or matched
    return matched


@dataclass(frozen=True, slots=True)
class WebhookEvent:
    """A verified webhook delivery."""

    type: str | None
    """Event type, from ``X-Danipa-Event`` (e.g. ``payment.completed``)."""

    delivery_id: str | None
    """Delivery id, from ``X-Danipa-Delivery``. Use it to de-duplicate redeliveries."""

    timestamp: int
    """Signing time, from ``X-Danipa-Timestamp`` (epoch seconds)."""

    data: Any
    """The parsed JSON body (``None`` when empty). Fractional numbers are ``Decimal``."""

    raw: bytes
    """The exact bytes that were verified."""


def _header(headers: Mapping[str, str], name: str) -> str | None:
    wanted = name.lower()
    for key, value in headers.items():
        if key.lower() == wanted:
            return value
    return None


def construct_event(
    payload: Payload,
    headers: Mapping[str, str],
    secrets: Secrets,
    *,
    tolerance: int = REPLAY_WINDOW_SECONDS,
) -> WebhookEvent:
    """Verify a delivery and return it as a :class:`WebhookEvent`.

    ``headers`` is any mapping of the request headers (matched case-insensitively),
    e.g. ``request.headers`` from Flask, Django or Starlette.

    Raises
    ------
    WebhookVerificationError
        When a signing header is missing, the timestamp is outside ``tolerance``,
        no secret matches, or the verified body is not valid JSON.
    """
    signature = _header(headers, SIGNATURE_HEADER)
    timestamp = _header(headers, TIMESTAMP_HEADER)
    if not signature or not timestamp:
        raise WebhookVerificationError(
            f"Danipa webhook: missing {SIGNATURE_HEADER} or {TIMESTAMP_HEADER} header"
        )
    body = _as_bytes(payload)
    if not verify(body, signature, timestamp, secrets, tolerance=tolerance):
        raise WebhookVerificationError(
            "Danipa webhook: signature verification failed "
            "(wrong secret, tampered body, or timestamp outside tolerance)"
        )

    data: Any = None
    if body.strip():
        try:
            data = json.loads(body.decode("utf-8"), parse_float=Decimal)
        except (UnicodeDecodeError, ValueError) as exc:
            raise WebhookVerificationError(
                "Danipa webhook: signature is valid but the body is not valid JSON"
            ) from exc

    return WebhookEvent(
        type=_header(headers, EVENT_HEADER),
        delivery_id=_header(headers, DELIVERY_HEADER),
        timestamp=int(timestamp),
        data=data,
        raw=body,
    )
