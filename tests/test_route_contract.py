"""Contract: the SDK's route set IS the server's API-key route table.

``EXPECTED_ROUTES`` mirrors ``ApiKeyAuthenticationFilter.API_KEY_ROUTES`` on
the fintech service (#5573). Three checks keep them locked together:

1. every public SDK method is exercised here, and the (verb, path) set they hit
   equals ``EXPECTED_ROUTES`` exactly, so a method that calls a route a key
   cannot reach (it would always 403) fails CI, and so does a missing one;
2. a new public resource method not registered below fails CI;
3. inside the monorepo, ``EXPECTED_ROUTES`` is compared with the filter's Java
   source, so a server-side route change fails the SDK's CI too. (The public
   mirror has no server source; that check is skipped there.)
"""

from __future__ import annotations

import asyncio
import inspect
import re
from collections.abc import Awaitable, Callable
from decimal import Decimal
from pathlib import Path
from typing import Any

import httpx
import pytest

from danipa import AsyncDanipa, Danipa
from danipa.models import (
    CreateInvoiceRequest,
    CreatePaymentLinkRequest,
    InvoiceLineItemRequest,
    UpdatePaymentLinkRequest,
)
from tests.conftest import INVOICE_BODY, MERCHANT_BODY, PAYMENT_LINK_BODY

ID = "{id}"
EXPECTED_ROUTES: frozenset[tuple[str, str]] = frozenset(
    {
        ("GET", "/v1/merchants/me"),
        ("POST", "/v1/merchants/me/payment-links"),
        ("GET", "/v1/merchants/me/payment-links"),
        ("PUT", "/v1/merchants/me/payment-links/{id}"),
        ("DELETE", "/v1/merchants/me/payment-links/{id}"),
        ("POST", "/v1/merchants/me/invoices"),
        ("GET", "/v1/merchants/me/invoices"),
        ("GET", "/v1/merchants/me/invoices/{id}"),
        ("POST", "/v1/merchants/me/invoices/{id}/send"),
        ("POST", "/v1/merchants/me/invoices/{id}/void"),
        ("GET", "/v1/merchants/me/wallet/balances"),
    }
)

UUID_VALUE = "0b7f6c2e-1d3a-4e5b-8c9d-0a1b2c3d4e5f"
PAGE_BODY: dict[str, Any] = {"content": [], "totalElements": 0, "totalPages": 0, "number": 0, "size": 20}

_LINK = CreatePaymentLinkRequest(title="t")
_UPDATE = UpdatePaymentLinkRequest(title="t")
_INVOICE = CreateInvoiceRequest(
    customer_name="c",
    line_items=[InvoiceLineItemRequest(description="d", quantity=1, unit_price=Decimal("1.00"))],
)

# (resource attribute, method name) -> how to call it
SYNC_CALLS: dict[tuple[str, str], Callable[[Danipa], object]] = {
    ("merchants", "me"): lambda d: d.merchants.me(),
    ("payment_links", "create"): lambda d: d.payment_links.create(_LINK),
    ("payment_links", "list"): lambda d: d.payment_links.list(),
    ("payment_links", "update"): lambda d: d.payment_links.update(UUID_VALUE, _UPDATE),
    ("payment_links", "delete"): lambda d: d.payment_links.delete(UUID_VALUE),
    ("invoices", "create"): lambda d: d.invoices.create(_INVOICE),
    ("invoices", "list"): lambda d: d.invoices.list(),
    ("invoices", "get"): lambda d: d.invoices.get(UUID_VALUE),
    ("invoices", "send"): lambda d: d.invoices.send(UUID_VALUE),
    ("invoices", "void"): lambda d: d.invoices.void(UUID_VALUE),
    ("balances", "list"): lambda d: d.balances.list(),
}

ASYNC_CALLS: dict[tuple[str, str], Callable[[AsyncDanipa], Awaitable[object]]] = {
    ("merchants", "me"): lambda d: d.merchants.me(),
    ("payment_links", "create"): lambda d: d.payment_links.create(_LINK),
    ("payment_links", "list"): lambda d: d.payment_links.list(),
    ("payment_links", "update"): lambda d: d.payment_links.update(UUID_VALUE, _UPDATE),
    ("payment_links", "delete"): lambda d: d.payment_links.delete(UUID_VALUE),
    ("invoices", "create"): lambda d: d.invoices.create(_INVOICE),
    ("invoices", "list"): lambda d: d.invoices.list(),
    ("invoices", "get"): lambda d: d.invoices.get(UUID_VALUE),
    ("invoices", "send"): lambda d: d.invoices.send(UUID_VALUE),
    ("invoices", "void"): lambda d: d.invoices.void(UUID_VALUE),
    ("balances", "list"): lambda d: d.balances.list(),
}

RESOURCES = ("merchants", "payment_links", "invoices", "balances")


class _Router:
    """Answers any route with a body of the right shape and records (verb, template)."""

    def __init__(self) -> None:
        self.hits: list[tuple[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/ms")
        template = path.replace(UUID_VALUE, ID)
        self.hits.append((request.method, template))
        if template.endswith("/wallet/balances"):
            return httpx.Response(200, json=[])
        if request.method == "GET" and template in {
            "/v1/merchants/me/payment-links",
            "/v1/merchants/me/invoices",
        }:
            return httpx.Response(200, json=PAGE_BODY)
        if template == "/v1/merchants/me":
            return httpx.Response(200, json=MERCHANT_BODY)
        if request.method == "DELETE":
            return httpx.Response(204)
        if "payment-links" in template:
            return httpx.Response(200, json=PAYMENT_LINK_BODY)
        return httpx.Response(200, json=INVOICE_BODY)


def _public_methods(resource: object) -> set[str]:
    return {
        name
        for name, member in inspect.getmembers(type(resource), inspect.isfunction)
        if not name.startswith("_")
    }


def test_sync_route_set_equals_the_api_key_route_table() -> None:
    router = _Router()
    with Danipa(api_key="dk_test_contract", transport=httpx.MockTransport(router)) as danipa:
        for call in SYNC_CALLS.values():
            call(danipa)
    assert set(router.hits) == EXPECTED_ROUTES
    assert len(router.hits) == len(EXPECTED_ROUTES)  # one route per method, no strays


def test_async_route_set_equals_the_api_key_route_table() -> None:
    router = _Router()

    async def run() -> None:
        async with AsyncDanipa(
            api_key="dk_test_contract", transport=httpx.MockTransport(router)
        ) as danipa:
            for call in ASYNC_CALLS.values():
                await call(danipa)

    asyncio.run(run())
    assert set(router.hits) == EXPECTED_ROUTES
    assert len(router.hits) == len(EXPECTED_ROUTES)


def test_every_public_method_is_registered_in_the_contract() -> None:
    danipa = Danipa(api_key="dk_test_contract")
    adanipa = AsyncDanipa(api_key="dk_test_contract")
    try:
        sync_methods = {(r, m) for r in RESOURCES for m in _public_methods(getattr(danipa, r))}
        async_methods = {(r, m) for r in RESOURCES for m in _public_methods(getattr(adanipa, r))}
    finally:
        danipa.close()
        asyncio.run(adanipa.aclose())
    assert sync_methods == set(SYNC_CALLS)
    assert async_methods == set(ASYNC_CALLS)
    # no resource attribute beyond the known four
    resource_attrs = {
        name
        for name, value in vars(danipa).items()
        if not name.startswith("_") and type(value).__module__.startswith("danipa.resources")
    }
    assert resource_attrs == set(RESOURCES)


def test_contract_router_records_unknown_routes() -> None:
    # Guard the guard: a route outside the table would be recorded, not swallowed.
    router = _Router()
    router(httpx.Request("GET", "https://x/ms/v1/merchants/me/invoices/stats"))
    assert router.hits == [("GET", "/v1/merchants/me/invoices/stats")]
    assert ("GET", "/v1/merchants/me/invoices/stats") not in EXPECTED_ROUTES


FILTER_SOURCE = (
    Path(__file__).resolve().parents[3]
    / "services/danipa-fintech-service/danipa-fintech-app/src/main/java/com/danipa/fintech"
    / "config/ApiKeyAuthenticationFilter.java"
)

_ROUTE = re.compile(
    r'new ApiKeyRoute\(\s*"(?P<verb>[A-Z]+)",\s*"(?P<path>[^"]+)"'
    r'(?P<uuid>\s*\+\s*UUID_SEGMENT(?:\s*\+\s*"(?P<tail>[^"]*)")?)?'
)


def _server_routes(source: str) -> set[tuple[str, str]]:
    routes: set[tuple[str, str]] = set()
    for match in _ROUTE.finditer(source):
        path = match["path"]
        if match["uuid"]:
            path += ID + (match["tail"] or "")
        routes.add((match["verb"], path))
    return routes


def test_route_parser_understands_the_filter_syntax() -> None:
    sample = """
        new ApiKeyRoute("GET", "/v1/merchants/me", ApiKeyScope.ACCOUNT_READ),
        new ApiKeyRoute("PUT", "/v1/merchants/me/payment-links/" + UUID_SEGMENT, ApiKeyScope.X),
        new ApiKeyRoute("POST", "/v1/merchants/me/invoices/" + UUID_SEGMENT + "/send", S.Y),
    """
    assert _server_routes(sample) == {
        ("GET", "/v1/merchants/me"),
        ("PUT", "/v1/merchants/me/payment-links/{id}"),
        ("POST", "/v1/merchants/me/invoices/{id}/send"),
    }


@pytest.mark.skipif(not FILTER_SOURCE.is_file(), reason="server source not present (public mirror)")
def test_expected_routes_match_the_server_filter() -> None:  # pragma: no cover - monorepo only
    source = FILTER_SOURCE.read_text(encoding="utf-8")
    assert _server_routes(source) == EXPECTED_ROUTES
