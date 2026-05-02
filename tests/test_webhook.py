"""Webhook signature verification — cross-SDK fixture parity.

Every Danipa SDK (Node, Java, Python, PHP) must produce identical signatures
for every vector in ``sdks/fixtures/webhook-hmac.json``. Drift here means a
backend webhook will validate in one SDK but reject in another — treat any
test failure as a release-blocker.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Any
from unittest.mock import patch

import pytest

from danipa import REPLAY_WINDOW_SECONDS, verify_webhook
from danipa.webhook import compute_signature


@pytest.fixture
def fixed_clock() -> Iterator[None]:
    """Pin time.time() to 1700000000 so fixture timestamps land inside the replay window."""
    with patch("danipa.webhook.time.time", return_value=1700000000):
        yield


def test_compute_signature_matches_every_fixture_vector(
    webhook_hmac_fixture: dict[str, Any],
) -> None:
    """compute_signature must produce the exact bytes recorded in the fixture."""
    for vector in webhook_hmac_fixture["vectors"]:
        actual = compute_signature(vector["payload"], vector["secret"], vector["timestamp"])
        assert actual == vector["expectedSignature"], (
            f"vector {vector['name']!r}: expected {vector['expectedSignature']!r}, got {actual!r}"
        )


def test_verify_accepts_every_non_empty_fixture_vector(
    webhook_hmac_fixture: dict[str, Any],
) -> None:
    """verify() must accept the recorded signature for every non-empty vector inside the replay window.

    The ``empty-payload`` vector exists for ``compute_signature`` parity only;
    ``verify()`` rejects empty payloads as a safety check (matches Node + Java).
    Each vector pins its own timestamp; ``time.time()`` is patched per-vector so the
    replay-window check passes regardless of when the test runs.
    """
    for vector in webhook_hmac_fixture["vectors"]:
        if vector["payload"] == "":
            continue
        with patch("danipa.webhook.time.time", return_value=vector["timestamp"]):
            assert verify_webhook(
                vector["payload"],
                vector["expectedSignature"],
                str(vector["timestamp"]),
                vector["secret"],
            ), f"vector {vector['name']!r} failed to verify"


def test_verify_rejects_tampered_signature(fixed_clock: None) -> None:
    payload = '{"test":true}'
    secret = "whsec_fixed_test_secret"
    ts = 1700000000
    bad = "sha256=" + "0" * 64
    assert verify_webhook(payload, bad, str(ts), secret) is False


def test_verify_rejects_tampered_payload(fixed_clock: None) -> None:
    secret = "whsec_fixed_test_secret"
    ts = 1700000000
    sig = compute_signature('{"test":true}', secret, ts)
    assert verify_webhook('{"test":false}', sig, str(ts), secret) is False


def test_verify_rejects_expired_timestamp() -> None:
    payload = '{"test":true}'
    secret = "whsec_fixed_test_secret"
    ts = 1700000000
    sig = compute_signature(payload, secret, ts)
    # 'now' is ts + replay_window + 1 → outside the window
    with patch("danipa.webhook.time.time", return_value=ts + REPLAY_WINDOW_SECONDS + 1):
        assert verify_webhook(payload, sig, str(ts), secret) is False


def test_verify_rejects_future_timestamp_outside_window() -> None:
    payload = '{"test":true}'
    secret = "whsec_fixed_test_secret"
    ts = 1700000000
    sig = compute_signature(payload, secret, ts)
    with patch("danipa.webhook.time.time", return_value=ts - REPLAY_WINDOW_SECONDS - 1):
        assert verify_webhook(payload, sig, str(ts), secret) is False


@pytest.mark.parametrize(
    ("payload", "signature", "timestamp", "secret"),
    [
        ("", "sha256=abc", "1700000000", "whsec_x"),
        ('{"x":1}', "", "1700000000", "whsec_x"),
        ('{"x":1}', "sha256=abc", "", "whsec_x"),
        ('{"x":1}', "sha256=abc", "1700000000", ""),
    ],
    ids=["empty-payload", "empty-signature", "empty-timestamp", "empty-secret"],
)
def test_verify_rejects_empty_inputs(
    payload: str, signature: str, timestamp: str, secret: str
) -> None:
    assert verify_webhook(payload, signature, timestamp, secret) is False


def test_verify_rejects_non_numeric_timestamp(fixed_clock: None) -> None:
    payload = '{"test":true}'
    secret = "whsec_fixed_test_secret"
    sig = compute_signature(payload, secret, 1700000000)
    assert verify_webhook(payload, sig, "not-a-number", secret) is False


def test_compute_signature_format() -> None:
    sig = compute_signature("{}", "whsec_x", 1700000000)
    assert sig.startswith("sha256=")
    assert len(sig) == len("sha256=") + 64  # SHA-256 = 32 bytes = 64 hex chars
