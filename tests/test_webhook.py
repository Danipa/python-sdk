"""Webhook verification: cross-SDK fixture parity, raw bytes, rotation, construct_event.

Every Danipa SDK (Node, Java, Python, PHP) must produce identical signatures
for every vector in ``sdks/fixtures/webhook-hmac.json``. Drift here means a
webhook validates in one SDK but is rejected in another: a release-blocker.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from decimal import Decimal
from typing import Any
from unittest.mock import patch

import pytest

from danipa import (
    REPLAY_WINDOW_SECONDS,
    WebhookVerificationError,
    compute_signature,
    construct_event,
    verify_webhook,
)
from tests.conftest import FIXTURE_PATH, MONOREPO_FIXTURE_PATH

SECRET = "whsec_fixed_test_secret"
TS = 1700000000
BODY = b'{"event":"payment.completed","amount":125.10}'


@pytest.fixture
def fixed_clock() -> Iterator[None]:
    with patch("danipa.webhook.time.time", return_value=TS):
        yield


def _headers(body: bytes = BODY, secret: str = SECRET, ts: int = TS) -> dict[str, str]:
    return {
        "X-Danipa-Signature": compute_signature(body, secret, ts),
        "X-Danipa-Timestamp": str(ts),
        "X-Danipa-Event": "payment.completed",
        "X-Danipa-Delivery": "dlv_123",
    }


# ---------------------------------------------------------------------------
# Fixture parity
# ---------------------------------------------------------------------------


def test_vendored_fixture_matches_monorepo_source() -> None:
    if not MONOREPO_FIXTURE_PATH.exists():
        pytest.skip("not running inside the monorepo (public mirror)")
    assert FIXTURE_PATH.read_bytes() == MONOREPO_FIXTURE_PATH.read_bytes()


def test_compute_signature_matches_every_vector(webhook_hmac_fixture: dict[str, Any]) -> None:
    for vector in webhook_hmac_fixture["vectors"]:
        for payload in (vector["payload"], vector["payload"].encode("utf-8")):
            actual = compute_signature(payload, vector["secret"], vector["timestamp"])
            assert actual == vector["expectedSignature"], vector["name"]


def test_verify_accepts_every_vector_including_empty_payload(
    webhook_hmac_fixture: dict[str, Any],
) -> None:
    names = []
    for vector in webhook_hmac_fixture["vectors"]:
        with patch("danipa.webhook.time.time", return_value=vector["timestamp"]):
            for payload in (vector["payload"], vector["payload"].encode("utf-8")):
                assert verify_webhook(
                    payload,
                    vector["expectedSignature"],
                    str(vector["timestamp"]),
                    vector["secret"],
                ), vector["name"]
        names.append(vector["name"])
    assert "empty-payload" in names


# ---------------------------------------------------------------------------
# verify()
# ---------------------------------------------------------------------------


def test_bytes_are_signed_raw_not_re_encoded(fixed_clock: None) -> None:
    raw = "{\"x\":\"€\"}".encode()
    sig = compute_signature(raw, SECRET, TS)
    assert verify_webhook(raw, sig, str(TS), SECRET)
    assert verify_webhook(bytearray(raw), sig, str(TS), SECRET)
    assert verify_webhook(memoryview(raw), sig, str(TS), SECRET)
    assert verify_webhook(raw.decode("utf-8"), sig, str(TS), SECRET)


def test_rejects_tampered_signature_and_payload(fixed_clock: None) -> None:
    sig = compute_signature(BODY, SECRET, TS)
    assert verify_webhook(BODY, "sha256=" + "0" * 64, str(TS), SECRET) is False
    assert verify_webhook(BODY + b" ", sig, str(TS), SECRET) is False


def test_default_tolerance_is_300s() -> None:
    sig = compute_signature(BODY, SECRET, TS)
    with patch("danipa.webhook.time.time", return_value=TS + REPLAY_WINDOW_SECONDS):
        assert verify_webhook(BODY, sig, str(TS), SECRET) is True
    with patch("danipa.webhook.time.time", return_value=TS + REPLAY_WINDOW_SECONDS + 1):
        assert verify_webhook(BODY, sig, str(TS), SECRET) is False
    with patch("danipa.webhook.time.time", return_value=TS - REPLAY_WINDOW_SECONDS - 1):
        assert verify_webhook(BODY, sig, str(TS), SECRET) is False


def test_tolerance_is_configurable() -> None:
    sig = compute_signature(BODY, SECRET, TS)
    with patch("danipa.webhook.time.time", return_value=TS + 600):
        assert verify_webhook(BODY, sig, str(TS), SECRET) is False
        assert verify_webhook(BODY, sig, str(TS), SECRET, tolerance=900) is True
    with patch("danipa.webhook.time.time", return_value=TS + 31):
        assert verify_webhook(BODY, sig, str(TS), SECRET, tolerance=30) is False


def test_secret_rotation_accepts_any_listed_secret(fixed_clock: None) -> None:
    sig_new = compute_signature(BODY, "whsec_new", TS)
    sig_old = compute_signature(BODY, "whsec_old", TS)
    secrets = ["whsec_new", "whsec_old"]
    assert verify_webhook(BODY, sig_new, str(TS), secrets)
    assert verify_webhook(BODY, sig_old, str(TS), secrets)
    assert verify_webhook(BODY, sig_old, str(TS), ("whsec_new",)) is False


@pytest.mark.parametrize(
    ("signature", "timestamp", "secret"),
    [
        ("", str(TS), SECRET),
        ("sha256=abc", "", SECRET),
        ("sha256=abc", str(TS), ""),
        ("sha256=abc", str(TS), []),
        ("sha256=abc", str(TS), ["", ""]),
        ("sha256=abc", "not-a-number", SECRET),
    ],
    ids=["no-signature", "no-timestamp", "empty-secret", "no-secrets", "blank-secrets", "bad-ts"],
)
def test_rejects_missing_inputs(
    fixed_clock: None, signature: str, timestamp: str, secret: str | list[str]
) -> None:
    assert verify_webhook(BODY, signature, timestamp, secret) is False


# ---------------------------------------------------------------------------
# construct_event()
# ---------------------------------------------------------------------------


def test_construct_event_returns_typed_event(fixed_clock: None) -> None:
    event = construct_event(BODY, _headers(), SECRET)
    assert event.type == "payment.completed"
    assert event.delivery_id == "dlv_123"
    assert event.timestamp == TS
    assert event.raw == BODY
    assert event.data == {"event": "payment.completed", "amount": Decimal("125.10")}
    assert str(event.data["amount"]) == "125.10"


def test_construct_event_headers_are_case_insensitive(fixed_clock: None) -> None:
    headers = {k.lower(): v for k, v in _headers().items()}
    event = construct_event(BODY.decode("utf-8"), headers, [SECRET])
    assert event.delivery_id == "dlv_123"


def test_construct_event_with_rotated_secrets(fixed_clock: None) -> None:
    event = construct_event(BODY, _headers(secret="whsec_old"), ["whsec_new", "whsec_old"])
    assert event.type == "payment.completed"


def test_construct_event_empty_body_has_no_data(fixed_clock: None) -> None:
    event = construct_event(b"", _headers(body=b""), SECRET)
    assert event.data is None
    assert event.raw == b""


def test_construct_event_optional_headers_absent(fixed_clock: None) -> None:
    headers = _headers()
    del headers["X-Danipa-Event"]
    del headers["X-Danipa-Delivery"]
    event = construct_event(BODY, headers, SECRET)
    assert event.type is None
    assert event.delivery_id is None


@pytest.mark.parametrize("missing", ["X-Danipa-Signature", "X-Danipa-Timestamp"])
def test_construct_event_requires_signing_headers(fixed_clock: None, missing: str) -> None:
    headers = _headers()
    del headers[missing]
    with pytest.raises(WebhookVerificationError, match="missing"):
        construct_event(BODY, headers, SECRET)


def test_construct_event_rejects_bad_signature(fixed_clock: None) -> None:
    with pytest.raises(WebhookVerificationError, match="verification failed"):
        construct_event(BODY, _headers(secret="whsec_other"), SECRET)


def test_construct_event_rejects_stale_timestamp() -> None:
    with (
        patch("danipa.webhook.time.time", return_value=TS + 301),
        pytest.raises(WebhookVerificationError),
    ):
        construct_event(BODY, _headers(), SECRET)
    with patch("danipa.webhook.time.time", return_value=TS + 301):
        assert construct_event(BODY, _headers(), SECRET, tolerance=400).timestamp == TS


@pytest.mark.parametrize("body", [b"{not json", b"\xff\xfe"])
def test_construct_event_rejects_signed_non_json(fixed_clock: None, body: bytes) -> None:
    with pytest.raises(WebhookVerificationError, match="not valid JSON"):
        construct_event(body, _headers(body=body), SECRET)


def test_signature_format() -> None:
    sig = compute_signature("{}", "whsec_x", TS)
    assert sig.startswith("sha256=")
    assert len(sig) == len("sha256=") + 64
    assert json.loads("{}") == {}


# ---------------------------------------------------------------------------
# dedupe_key (#7614): Danipa re-signs every retry with a fresh timestamp, so
# only the body is stable across attempts; event/delivery headers are unsigned.
# ---------------------------------------------------------------------------


def test_dedupe_key_is_stable_across_retries_resigned_with_a_fresh_timestamp(
    fixed_clock: None,
) -> None:
    first = construct_event(BODY, _headers(ts=TS - 120), SECRET)
    retry_headers = _headers(ts=TS)
    retry_headers["X-Danipa-Delivery"] = "dlv_other"
    retry = construct_event(BODY.decode("utf-8"), retry_headers, SECRET)
    assert len(first.dedupe_key) == 64
    assert int(first.dedupe_key, 16) >= 0
    assert first.dedupe_key == first.dedupe_key.lower()
    assert retry.dedupe_key == first.dedupe_key


def test_dedupe_key_differs_for_a_different_body(fixed_clock: None) -> None:
    other = b'{"event":"payment.completed","amount":125.11}'
    a = construct_event(BODY, _headers(), SECRET)
    b = construct_event(other, _headers(body=other), SECRET)
    assert a.dedupe_key != b.dedupe_key


def test_dedupe_key_matches_every_fixture_vector(
    fixed_clock: None, webhook_hmac_fixture: dict[str, Any]
) -> None:
    vectors = webhook_hmac_fixture["dedupeKey"]["vectors"]
    assert vectors
    for vector in vectors:
        body = vector["payload"].encode("utf-8")
        for ts in (TS - 60, TS):
            event = construct_event(body, _headers(body=body, ts=ts), SECRET)
            assert event.dedupe_key == vector["expectedDigest"], (vector["name"], ts)
