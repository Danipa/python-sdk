"""Shared pytest fixtures.

The cross-SDK HMAC vectors are vendored at ``tests/fixtures/webhook-hmac.json``
so the public mirror (which only contains ``sdks/python/``) can run them. CI
fails if the copy drifts from the source of truth at ``sdks/fixtures/``.
"""

from __future__ import annotations

import json
from collections.abc import Callable, Iterator
from pathlib import Path
from typing import Any
from unittest.mock import patch

import httpx
import pytest

FIXTURE_PATH = Path(__file__).resolve().parent / "fixtures" / "webhook-hmac.json"
MONOREPO_FIXTURE_PATH = Path(__file__).resolve().parents[2] / "fixtures" / "webhook-hmac.json"

Handler = Callable[[httpx.Request], httpx.Response]


@pytest.fixture(scope="session")
def webhook_hmac_fixture() -> dict[str, Any]:
    """Load the cross-SDK HMAC test vectors. Release-blocker on any drift."""
    with FIXTURE_PATH.open("r", encoding="utf-8") as fh:
        data: dict[str, Any] = json.load(fh)
    return data


class FakeServer:
    """A fake transport that records every request that actually hit the wire.

    ``script`` entries are returned in order (the last one repeats). An entry
    that is an exception instance is raised instead, simulating a transport
    failure.
    """

    def __init__(self, *script: httpx.Response | Exception) -> None:
        self.script: list[httpx.Response | Exception] = list(script)
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        request.read()
        self.requests.append(request)
        index = min(len(self.requests) - 1, len(self.script) - 1)
        item = self.script[index]
        if isinstance(item, Exception):
            raise item
        return httpx.Response(
            item.status_code, headers=item.headers, content=item.content, request=request
        )

    @property
    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self)

    @property
    def last(self) -> httpx.Request:
        return self.requests[-1]

    def json_body(self, index: int = -1) -> Any:
        return json.loads(self.requests[index].content)


class SleepRecorder:
    """A fake clock: records requested sleeps instead of sleeping."""

    def __init__(self) -> None:
        self.delays: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.delays.append(seconds)

    async def async_sleep(self, seconds: float) -> None:
        self.delays.append(seconds)


@pytest.fixture
def sleeps() -> Iterator[SleepRecorder]:
    recorder = SleepRecorder()
    with (
        patch("danipa.http.time.sleep", recorder),
        patch("danipa.http.asyncio.sleep", recorder.async_sleep),
    ):
        yield recorder


def json_response(status: int, body: Any, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(status, json=body, headers=headers)


def raw_response(status: int, text: str, headers: dict[str, str] | None = None) -> httpx.Response:
    return httpx.Response(
        status, content=text.encode("utf-8"), headers={"content-type": "application/json", **(headers or {})}
    )


MERCHANT_BODY: dict[str, Any] = {
    "id": "8f1f3a1e-0000-4000-8000-000000000001",
    "businessName": "Kin & Calabash",
    "country": "CA",
    "status": "ACTIVE",
    "kybStatus": "APPROVED",
    "tier": "STARTER",
    "createdAt": "2026-01-01T00:00:00Z",
    "publicCatalogEnabled": True,
    "effectiveDefaultTaxRatePct": 13.00,
    "billingCurrency": "CAD",
}

PAYMENT_LINK_BODY: dict[str, Any] = {
    "id": "pl_1",
    "shortCode": "abc123",
    "url": "https://pay.danipa.com/l/abc123",
    "title": "Deposit",
    "amount": 125.10,
    "currency": "GHS",
    "isAmountFixed": True,
    "status": "ACTIVE",
    "totalCollected": 0,
    "paymentCount": 0,
    "createdAt": "2026-01-01T00:00:00Z",
    "merchantName": "Kin & Calabash",
}

INVOICE_BODY: dict[str, Any] = {
    "id": "inv_1",
    "invoiceNumber": "INV-0001",
    "customerName": "Ama K.",
    "lineItems": [
        {"description": "Catering", "quantity": 3, "unitPrice": 10.00, "lineTotal": 30.00, "taxRatePct": 13}
    ],
    "subtotal": 30.00,
    "taxAmount": 3.90,
    "taxBreakdown": [{"label": "HST 13%", "ratePct": 13.00, "amount": 3.90}],
    "total": 33.90,
    "currency": "CAD",
    "status": "SENT",
    "dueDate": "2026-02-01",
    "createdAt": "2026-01-01T00:00:00Z",
}
