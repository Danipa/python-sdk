"""Danipa webhook signature verification.

Verifies that incoming webhook payloads are authentic by checking the
HMAC-SHA256 signature in the ``X-Danipa-Signature`` header.

Cross-SDK parity: every Danipa SDK (Node, Java, Python, PHP) MUST produce
identical signatures for the vectors in ``sdks/fixtures/webhook-hmac.json``.
Drift in this file is a release-blocker.

Algorithm
---------
``signedContent = f"{timestamp}.{payload}"`` (UTF-8)
``signature = "sha256=" + lowercase-hex HMAC-SHA256(secret, signedContent)``
"""

from __future__ import annotations

import hashlib
import hmac
import time

REPLAY_WINDOW_SECONDS = 300
"""Maximum allowed age for a webhook timestamp (5 minutes)."""


def verify(
    payload: str,
    signature: str,
    timestamp: str,
    secret: str,
) -> bool:
    """Verify a webhook signature.

    Parameters
    ----------
    payload:
        The raw JSON request body (string, not parsed).
    signature:
        The ``X-Danipa-Signature`` header (e.g. ``sha256=abcdef...``).
    timestamp:
        The ``X-Danipa-Timestamp`` header (epoch seconds, as a string).
    secret:
        The endpoint signing secret (starts with ``whsec_``).

    Returns
    -------
    bool
        ``True`` if the signature is valid and the timestamp is within
        the replay window; ``False`` for any failure including missing
        inputs, malformed timestamp, expired timestamp, or signature
        mismatch.
    """
    if not payload or not signature or not timestamp or not secret:
        return False

    try:
        ts = int(timestamp)
    except (TypeError, ValueError):
        return False

    now = int(time.time())
    if abs(now - ts) > REPLAY_WINDOW_SECONDS:
        return False

    expected = compute_signature(payload, secret, ts)
    return hmac.compare_digest(expected.encode("utf-8"), signature.encode("utf-8"))


def compute_signature(payload: str, secret: str, timestamp_epoch_secs: int) -> str:
    """Compute the expected signature for a payload.

    Returns
    -------
    str
        The signature in the form ``sha256=<hex>``.
    """
    signed_content = f"{timestamp_epoch_secs}.{payload}".encode()
    digest = hmac.new(secret.encode("utf-8"), signed_content, hashlib.sha256).hexdigest()
    return f"sha256={digest}"
