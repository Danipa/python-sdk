"""Shared pytest fixtures.

The cross-SDK HMAC fixture lives at ``sdks/fixtures/webhook-hmac.json`` and is
consumed by Node, Java, and (Stage 3) Python and PHP. Tests must agree
bit-for-bit with the other SDKs on every vector.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

_FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "webhook-hmac.json"


@pytest.fixture(scope="session")
def webhook_hmac_fixture() -> dict[str, Any]:
    """Load the cross-SDK HMAC test vectors. Release-blocker on any drift."""
    with _FIXTURE_PATH.open("r", encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)
    return data
