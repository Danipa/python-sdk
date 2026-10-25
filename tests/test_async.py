"""AsyncDanipa: same wire contract and retry policy as the sync client.

Driven with ``asyncio.run`` so no async pytest plugin is needed.
"""

from __future__ import annotations

import asyncio
import re
from decimal import Decimal
from typing import Any

import httpx
import pytest

from danipa import (
    AsyncDanipa,
    DanipaConnectionError,
    PermissionDeniedError,
    RequestOptions,
    ResponseParseError,
    ServerError,
)
from danipa.models import (
    CreateInvoiceRequest,
    CreatePaymentLinkRequest,
    InvoiceLineItemRequest,
    InvoiceStatus,
)
from tests.conftest import (
    INVOICE_BODY,
    MERCHANT_BODY,
    PAYMENT_LINK_BODY,
    FakeServer,
    SleepRecorder,
    json_response,
    raw_response,
)

UUID4 = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")


def _client(server: FakeServer, **kwargs: Any) -> AsyncDanipa:
    return AsyncDanipa(api_key="dk_test_secret", transport=server.transport, **kwargs)


def _link() -> CreatePaymentLinkRequest:
    return CreatePaymentLinkRequest(title="Deposit", amount=Decimal("125.00"))


def test_async_me_sends_api_key_not_authorization() -> None:
    server = FakeServer(json_response(200, MERCHANT_BODY))

    async def run() -> str | None:
        async with _client(server) as danipa:
            assert danipa.base_url.endswith("api.sandbox.danipa.com/ms")
            merchant = await danipa.merchants.me()
            return merchant.billing_currency

    assert asyncio.run(run()) == "CAD"
    assert server.last.headers["x-api-key"] == "dk_test_secret"
    assert "authorization" not in server.last.headers
    assert server.last.headers["user-agent"].startswith("danipa-python/")


def test_async_retries_with_stable_key_and_honours_retry_after(sleeps: SleepRecorder) -> None:
    server = FakeServer(
        json_response(429, {"code": "RATE_LIMIT_EXCEEDED"}, {"Retry-After": "3"}),
        httpx.ConnectError("reset"),
        json_response(201, PAYMENT_LINK_BODY),
    )

    async def run() -> None:
        async with _client(server) as danipa:
            await danipa.payment_links.create(_link())

    asyncio.run(run())
    assert len(server.requests) == 3
    keys = {r.headers["idempotency-key"] for r in server.requests}
    assert len(keys) == 1
    assert UUID4.match(keys.pop())
    assert sleeps.delays[0] == 3.0
    assert 0.0 <= sleeps.delays[1] <= 1.0


def test_async_500_is_not_retried(sleeps: SleepRecorder) -> None:
    server = FakeServer(json_response(500, {"errors": [{"code": "BOOM"}]}))

    async def run() -> None:
        async with _client(server) as danipa:
            await danipa.merchants.me()

    with pytest.raises(ServerError) as exc:
        asyncio.run(run())
    assert exc.value.code == "BOOM"
    assert len(server.requests) == 1
    assert sleeps.delays == []


def test_async_flat_403_maps_to_permission_denied() -> None:
    server = FakeServer(json_response(403, {"code": "API_KEY_SCOPE_DENIED", "description": "no"}))

    async def run() -> None:
        async with _client(server) as danipa:
            await danipa.invoices.create(
                CreateInvoiceRequest(
                    customer_name="Ama",
                    line_items=[
                        InvoiceLineItemRequest(description="x", quantity=1, unit_price=Decimal("1"))
                    ],
                ),
                options=RequestOptions(idempotency_key="inv-1"),
            )

    with pytest.raises(PermissionDeniedError) as exc:
        asyncio.run(run())
    assert exc.value.idempotency_key == "inv-1"
    assert server.last.headers["idempotency-key"] == "inv-1"


def test_async_invoice_voided_and_money() -> None:
    server = FakeServer(json_response(201, {**INVOICE_BODY, "status": "VOIDED"}))

    async def run() -> tuple[InvoiceStatus | None, Decimal | None]:
        async with _client(server) as danipa:
            inv = await danipa.invoices.create(
                CreateInvoiceRequest(
                    customer_name="Ama",
                    line_items=[
                        InvoiceLineItemRequest(description="x", quantity=1, unit_price=Decimal("1"))
                    ],
                )
            )
            return inv.status, inv.tax_amount

    status, tax = asyncio.run(run())
    assert status is InvoiceStatus.VOIDED
    assert tax == Decimal("3.9")


def test_async_parse_error_is_not_network_error() -> None:
    server = FakeServer(raw_response(200, "not json"))

    async def run() -> None:
        async with _client(server) as danipa:
            await danipa.merchants.me()

    with pytest.raises(ResponseParseError):
        asyncio.run(run())
    assert len(server.requests) == 1


def test_async_connection_error_after_budget(sleeps: SleepRecorder) -> None:
    server = FakeServer(httpx.ConnectError("refused"))

    async def run() -> None:
        async with _client(server, max_retries=1) as danipa:
            await danipa.merchants.me()

    with pytest.raises(DanipaConnectionError):
        asyncio.run(run())
    assert len(server.requests) == 2


def test_async_injected_client_is_used_stripped_and_not_closed() -> None:
    server = FakeServer(json_response(200, MERCHANT_BODY))

    async def run() -> bool:
        injected = httpx.AsyncClient(
            transport=server.transport, headers={"Authorization": "Bearer x"}
        )
        danipa = AsyncDanipa(api_key="dk_test_k", http_client=injected)
        await danipa.merchants.me()
        await danipa.aclose()
        closed = injected.is_closed
        await injected.aclose()
        return closed

    assert asyncio.run(run()) is False
    assert server.last.url.host == "api.sandbox.danipa.com"
    assert "authorization" not in server.last.headers


def test_async_owned_client_is_closed() -> None:
    async def run() -> bool:
        danipa = AsyncDanipa(api_key="dk_test_x")
        await danipa.aclose()
        return danipa._http._client.is_closed

    assert asyncio.run(run()) is True
