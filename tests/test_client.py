"""Client-level tests — base URL, auth, retry, idempotency, error mapping.

Mirrors ``sdks/node/test/client.test.ts`` 1:1. Patches ``time.sleep`` in
``danipa.http`` to keep the suite fast (the retry math is unit-tested
separately).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from unittest.mock import patch

import httpx
import pytest
import respx

from danipa import (
    Danipa,
    DanipaApiError,
    DanipaNetworkError,
    RequestOptions,
)
from danipa.http import PRODUCTION_BASE_URL, SANDBOX_BASE_URL, infer_base_url
from danipa.models import (
    CreateCollectionRequest,
    CreateDisbursementRequest,
    CreateInvoiceRequest,
    CreatePaymentLinkRequest,
    InvoiceLineItem,
    Payer,
    Recipient,
)


@pytest.fixture(autouse=True)
def _no_sleep() -> Iterator[None]:
    """Skip the real backoff sleeps so retry tests run in milliseconds."""
    with patch("danipa.http.time.sleep"):
        yield


def _wallet_balance_body() -> dict[str, object]:
    return {
        "merchantId": "m_1",
        "currency": "GHS",
        "available": "0",
        "pending": "0",
        "asOf": "2026-01-01T00:00:00Z",
    }


def _collection_body() -> dict[str, object]:
    return {
        "id": "col_1",
        "merchantId": "m_1",
        "amount": "50",
        "currency": "GHS",
        "status": "PENDING",
        "payer": {"phone": "+233244000000"},
        "paymentLinkId": None,
        "createdAt": "2026-01-01T00:00:00Z",
        "completedAt": None,
    }


# ---------------------------------------------------------------------------
# Base URL inference
# ---------------------------------------------------------------------------

def test_infer_base_url_dk_test_returns_sandbox() -> None:
    assert infer_base_url("dk_test_abc") == SANDBOX_BASE_URL


def test_infer_base_url_dk_live_returns_production() -> None:
    assert infer_base_url("dk_live_abc") == PRODUCTION_BASE_URL


def test_infer_base_url_unknown_prefix_falls_back_to_sandbox() -> None:
    """Match Node's lenient default — never throw on unknown prefix."""
    assert infer_base_url("dk_unknown_abc") == SANDBOX_BASE_URL


@respx.mock
def test_dk_test_key_routes_to_sandbox() -> None:
    route = respx.get(f"{SANDBOX_BASE_URL}/v1/wallets/balance").mock(
        return_value=httpx.Response(200, json=_wallet_balance_body())
    )
    with Danipa(api_key="dk_test_abc") as danipa:
        danipa.wallets.get_balance()
    assert route.called


@respx.mock
def test_dk_live_key_routes_to_production() -> None:
    route = respx.get(f"{PRODUCTION_BASE_URL}/v1/wallets/balance").mock(
        return_value=httpx.Response(200, json=_wallet_balance_body())
    )
    with Danipa(api_key="dk_live_abc") as danipa:
        danipa.wallets.get_balance()
    assert route.called


@respx.mock
def test_explicit_base_url_overrides_inference() -> None:
    route = respx.get("https://api.example.test/v9/v1/wallets/balance").mock(
        return_value=httpx.Response(200, json=_wallet_balance_body())
    )
    with Danipa(api_key="dk_test_abc", base_url="https://api.example.test/v9") as danipa:
        danipa.wallets.get_balance()
    assert route.called


# ---------------------------------------------------------------------------
# Headers — auth, idempotency, content-type, user-agent
# ---------------------------------------------------------------------------

@respx.mock
def test_attaches_bearer_auth_on_every_request() -> None:
    route = respx.get(f"{SANDBOX_BASE_URL}/v1/wallets/balance").mock(
        return_value=httpx.Response(200, json=_wallet_balance_body())
    )
    with Danipa(api_key="dk_test_secret_key") as danipa:
        danipa.wallets.get_balance()
    request = route.calls[0].request
    assert request.headers["authorization"] == "Bearer dk_test_secret_key"
    assert request.headers["accept"] == "application/json"
    assert request.headers["user-agent"].startswith("danipa-python-sdk/")


@respx.mock
def test_forwards_x_idempotency_key_when_supplied() -> None:
    route = respx.post(f"{SANDBOX_BASE_URL}/v1/collections").mock(
        return_value=httpx.Response(200, json=_collection_body())
    )
    with Danipa(api_key="dk_test_x") as danipa:
        danipa.collections.create(
            CreateCollectionRequest(
                amount="50", currency="GHS", payer=Payer(phone="+233244000000")
            ),
            options=RequestOptions(idempotency_key="order-123"),
        )
    request = route.calls[0].request
    assert request.headers["x-idempotency-key"] == "order-123"
    assert request.headers["content-type"] == "application/json"


@respx.mock
def test_no_idempotency_header_when_options_omitted() -> None:
    route = respx.post(f"{SANDBOX_BASE_URL}/v1/collections").mock(
        return_value=httpx.Response(200, json=_collection_body())
    )
    with Danipa(api_key="dk_test_x") as danipa:
        danipa.collections.create(
            CreateCollectionRequest(
                amount="50", currency="GHS", payer=Payer(phone="+233244000000")
            )
        )
    assert "x-idempotency-key" not in route.calls[0].request.headers


@respx.mock
def test_request_body_is_camelcase_json() -> None:
    route = respx.post(f"{SANDBOX_BASE_URL}/v1/collections").mock(
        return_value=httpx.Response(200, json=_collection_body())
    )
    with Danipa(api_key="dk_test_x") as danipa:
        danipa.collections.create(
            CreateCollectionRequest(
                amount="50",
                currency="GHS",
                payer=Payer(phone="+233244000000", name="Ama"),
                payment_link_id="pl_1",
            )
        )
    sent = json.loads(route.calls[0].request.content)
    assert sent == {
        "amount": "50",
        "currency": "GHS",
        "payer": {"phone": "+233244000000", "name": "Ama"},
        "paymentLinkId": "pl_1",
    }


# ---------------------------------------------------------------------------
# Error mapping — 4xx, 5xx, network
# ---------------------------------------------------------------------------

@respx.mock
def test_4xx_raises_api_error_no_retry() -> None:
    route = respx.post(f"{SANDBOX_BASE_URL}/v1/collections").mock(
        return_value=httpx.Response(
            422,
            json={
                "correlationId": "corr-1",
                "errors": [
                    {
                        "code": "INSUFFICIENT_FUNDS",
                        "description": "Wallet balance below request amount.",
                    }
                ],
            },
        )
    )
    with Danipa(api_key="dk_test_x") as danipa, pytest.raises(DanipaApiError) as exc:
        danipa.collections.create(
            CreateCollectionRequest(amount="50", currency="GHS", payer=Payer())
        )
    err = exc.value
    assert err.status == 422
    assert err.code == "INSUFFICIENT_FUNDS"
    assert err.correlation_id == "corr-1"
    assert "Wallet balance" in str(err)
    assert route.call_count == 1


@respx.mock
def test_5xx_retries_and_surfaces_api_error() -> None:
    route = respx.get(f"{SANDBOX_BASE_URL}/v1/wallets/balance").mock(
        return_value=httpx.Response(503, text="upstream down")
    )
    with (
        Danipa(api_key="dk_test_x", max_retries=3) as danipa,
        pytest.raises(DanipaApiError) as exc,
    ):
        danipa.wallets.get_balance()
    assert exc.value.status == 503
    assert route.call_count == 3


@respx.mock
def test_5xx_eventual_success_returns_body() -> None:
    route = respx.get(f"{SANDBOX_BASE_URL}/v1/wallets/balance").mock(
        side_effect=[
            httpx.Response(503),
            httpx.Response(503),
            httpx.Response(200, json=_wallet_balance_body()),
        ]
    )
    with Danipa(api_key="dk_test_x", max_retries=3) as danipa:
        balance = danipa.wallets.get_balance()
    assert balance.merchant_id == "m_1"
    assert route.call_count == 3


@respx.mock
def test_network_error_retries_then_wraps_in_network_error() -> None:
    route = respx.get(f"{SANDBOX_BASE_URL}/v1/wallets/balance").mock(
        side_effect=httpx.ConnectError("failed to connect")
    )
    with (
        Danipa(api_key="dk_test_x", max_retries=2) as danipa,
        pytest.raises(DanipaNetworkError) as exc,
    ):
        danipa.wallets.get_balance()
    assert isinstance(exc.value.cause, httpx.ConnectError)
    assert route.call_count == 2


@respx.mock
def test_api_error_with_unparseable_body_falls_back_to_status() -> None:
    respx.get(f"{SANDBOX_BASE_URL}/v1/wallets/balance").mock(
        return_value=httpx.Response(400, text="not-json")
    )
    with Danipa(api_key="dk_test_x") as danipa, pytest.raises(DanipaApiError) as exc:
        danipa.wallets.get_balance()
    assert exc.value.status == 400
    assert exc.value.code == "UNKNOWN"
    assert "HTTP 400" in str(exc.value)


# ---------------------------------------------------------------------------
# Constructor validation
# ---------------------------------------------------------------------------

def test_empty_api_key_raises() -> None:
    with pytest.raises(TypeError, match="api_key"):
        Danipa(api_key="")


def test_zero_max_retries_raises() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        Danipa(api_key="dk_test_x", max_retries=0)


# ---------------------------------------------------------------------------
# Resource happy paths (P-3.3)
# ---------------------------------------------------------------------------

@respx.mock
def test_collections_get_by_id() -> None:
    route = respx.get(f"{SANDBOX_BASE_URL}/v1/collections/col_abc").mock(
        return_value=httpx.Response(200, json=_collection_body())
    )
    with Danipa(api_key="dk_test_x") as danipa:
        col = danipa.collections.get("col_abc")
    assert col.id == "col_1"
    assert col.status == "PENDING"
    assert route.called


@respx.mock
def test_disbursements_create_then_get() -> None:
    body = {
        "id": "dis_1",
        "merchantId": "m",
        "amount": "10",
        "currency": "GHS",
        "status": "PENDING",
        "recipient": {"phone": "+233200000000"},
        "createdAt": "2026-01-01T00:00:00Z",
        "completedAt": None,
    }
    create = respx.post(f"{SANDBOX_BASE_URL}/v1/disbursements").mock(
        return_value=httpx.Response(200, json=body)
    )
    fetch = respx.get(f"{SANDBOX_BASE_URL}/v1/disbursements/dis_1").mock(
        return_value=httpx.Response(200, json=body)
    )
    with Danipa(api_key="dk_test_x") as danipa:
        out = danipa.disbursements.create(
            CreateDisbursementRequest(
                amount="10", currency="GHS", recipient=Recipient(phone="+233200000000")
            )
        )
        again = danipa.disbursements.get("dis_1")
    assert out.id == "dis_1" == again.id
    assert create.called and fetch.called


@respx.mock
def test_wallets_get_balance_with_currency_query() -> None:
    route = respx.get(f"{SANDBOX_BASE_URL}/v1/wallets/balance").mock(
        return_value=httpx.Response(200, json=_wallet_balance_body())
    )
    with Danipa(api_key="dk_test_x") as danipa:
        danipa.wallets.get_balance(currency="GHS")
    request = route.calls[0].request
    assert request.url.params["currency"] == "GHS"


@respx.mock
def test_payment_links_create() -> None:
    route = respx.post(f"{SANDBOX_BASE_URL}/v1/merchants/me/payment-links").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "pl_1",
                "url": "https://pay.danipa.com/pl_1",
                "amount": "100",
                "currency": "GHS",
                "description": None,
                "expiresAt": None,
                "createdAt": "2026-01-01T00:00:00Z",
            },
        )
    )
    with Danipa(api_key="dk_test_x") as danipa:
        link = danipa.payment_links.create(
            CreatePaymentLinkRequest(amount="100", currency="GHS")
        )
    assert link.url.startswith("https://")
    assert route.called


@respx.mock
def test_invoices_create() -> None:
    route = respx.post(f"{SANDBOX_BASE_URL}/v1/merchants/me/invoices").mock(
        return_value=httpx.Response(
            200,
            json={
                "id": "inv_1",
                "merchantId": "m",
                "amount": "30",
                "currency": "GHS",
                "dueDate": "2026-02-01",
                "status": "SENT",
                "customerEmail": "c@example.com",
                "lineItems": [{"description": "x", "quantity": 3, "unitPrice": "10"}],
                "createdAt": "2026-01-01T00:00:00Z",
            },
        )
    )
    with Danipa(api_key="dk_test_x") as danipa:
        inv = danipa.invoices.create(
            CreateInvoiceRequest(
                customer_email="c@example.com",
                currency="GHS",
                due_date="2026-02-01",
                line_items=[
                    InvoiceLineItem(description="x", quantity=3, unit_price="10")
                ],
            )
        )
    assert inv.status == "SENT"
    assert inv.line_items[0].unit_price == "10"
    assert route.called
