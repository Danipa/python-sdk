"""Every API-key route the SDK exposes: verb, path, headers, body, parsing, errors.

One block per method, sync and async, all through the recording ``FakeServer``
transport. Shapes follow the fintech controllers/DTOs on origin/develop
(``PaymentLinkController``, ``InvoiceController``, ``MerchantWalletController``).
"""

from __future__ import annotations

import asyncio
import uuid
from decimal import Decimal
from typing import Any

import pytest

from danipa import (
    AsyncDanipa,
    ConflictError,
    Danipa,
    NotFoundError,
    PermissionDeniedError,
    RequestOptions,
    ResponseParseError,
    ValidationError,
)
from danipa.models import (
    Balance,
    CreateInvoiceRequest,
    CreatePaymentLinkRequest,
    Invoice,
    InvoiceLineItemRequest,
    InvoiceStatus,
    PaymentLink,
    PaymentLinkStatus,
    UpdatePaymentLinkRequest,
)
from tests.conftest import (
    INVOICE_BODY,
    PAYMENT_LINK_BODY,
    FakeServer,
    json_response,
    raw_response,
)

LINK_ID = "3f0e2c1a-6b7d-4e8f-9a0b-1c2d3e4f5a6b"
INVOICE_ID = "7a1b2c3d-4e5f-4061-8728-394a5b6c7d8e"


def _client(server: FakeServer) -> Danipa:
    return Danipa(api_key="dk_test_secret", transport=server.transport, max_retries=0)


def _aclient(server: FakeServer) -> AsyncDanipa:
    return AsyncDanipa(api_key="dk_test_secret", transport=server.transport, max_retries=0)


def _spring_page(items: list[dict[str, Any]], *, number: int = 0, size: int = 20) -> dict[str, Any]:
    """The Spring Data ``PageImpl`` JSON the server writes today (DIRECT mode)."""
    return {
        "content": items,
        "pageable": {"pageNumber": number, "pageSize": size, "offset": 0},
        "totalElements": 41,
        "totalPages": 3,
        "last": False,
        "first": True,
        "size": size,
        "number": number,
        "numberOfElements": len(items),
        "sort": {"sorted": False, "empty": True, "unsorted": True},
        "empty": not items,
    }


def _assert_common_headers(server: FakeServer, *, mutating: bool) -> None:
    request = server.last
    assert request.headers["x-api-key"] == "dk_test_secret"
    assert "authorization" not in request.headers
    if mutating:
        assert request.headers.get("idempotency-key")
    else:
        assert "idempotency-key" not in request.headers


def _path(server: FakeServer) -> str:
    return server.last.url.path


def _scope_denied() -> Any:
    return json_response(403, {"code": "API_KEY_SCOPE_DENIED", "description": "scope missing"})


# ---------------------------------------------------------------------------
# payment_links.list
# ---------------------------------------------------------------------------


def test_payment_links_list_sends_paging_and_parses_spring_page() -> None:
    server = FakeServer(json_response(200, _spring_page([PAYMENT_LINK_BODY], number=1, size=5)))
    with _client(server) as danipa:
        page = danipa.payment_links.list(page=1, size=5)
    assert server.last.method == "GET"
    assert _path(server) == "/ms/v1/merchants/me/payment-links"
    assert dict(server.last.url.params) == {"page": "1", "size": "5"}
    assert server.last.content == b""
    _assert_common_headers(server, mutating=False)
    assert page.total_elements == 41
    assert page.total_pages == 3
    assert page.number == 1
    assert page.size == 5
    assert page.has_next is True
    assert isinstance(page.content[0], PaymentLink)
    assert page.content[0].amount == Decimal("125.10")
    assert page.content[0].status is PaymentLinkStatus.ACTIVE
    assert page.response_meta is not None
    assert page.response_meta.status == 200


def test_payment_links_list_omits_unset_paging() -> None:
    server = FakeServer(json_response(200, _spring_page([])))
    with _client(server) as danipa:
        page = danipa.payment_links.list()
    assert server.last.url.query == b""
    assert page.content == []
    assert page.has_next is True  # totalPages=3, number=0


def test_page_accepts_nested_page_metadata_shape() -> None:
    body = {
        "content": [PAYMENT_LINK_BODY],
        "page": {"size": 20, "number": 2, "totalElements": 41, "totalPages": 3},
    }
    server = FakeServer(json_response(200, body))
    with _client(server) as danipa:
        page = danipa.payment_links.list()
    assert (page.number, page.size, page.total_elements, page.total_pages) == (2, 20, 41, 3)
    assert page.has_next is False


def test_nested_page_metadata_never_overrides_flat_fields_and_tolerates_gaps() -> None:
    body = {"content": [], "size": 7, "page": {"size": 99, "number": 0}}
    server = FakeServer(json_response(200, body))
    with _client(server) as danipa:
        page = danipa.payment_links.list()
    assert page.size == 7
    assert (page.total_elements, page.total_pages) == (0, 0)
    assert page.has_next is False


def test_payment_links_list_scope_denied_is_typed() -> None:
    server = FakeServer(_scope_denied())
    with _client(server) as danipa, pytest.raises(PermissionDeniedError) as info:
        danipa.payment_links.list()
    assert info.value.code == "API_KEY_SCOPE_DENIED"
    assert info.value.status == 403


def test_payment_links_list_non_page_body_is_parse_error() -> None:
    server = FakeServer(json_response(200, {"content": "nope"}))
    with _client(server) as danipa, pytest.raises(ResponseParseError):
        danipa.payment_links.list()


# ---------------------------------------------------------------------------
# payment_links.create (body shape is covered in test_client.py)
# ---------------------------------------------------------------------------


def test_payment_links_create_verb_path_and_parse() -> None:
    server = FakeServer(json_response(201, PAYMENT_LINK_BODY))
    with _client(server) as danipa:
        link = danipa.payment_links.create(CreatePaymentLinkRequest(title="Deposit"))
    assert server.last.method == "POST"
    assert _path(server) == "/ms/v1/merchants/me/payment-links"
    assert server.json_body() == {"title": "Deposit"}
    assert server.last.headers["content-type"] == "application/json"
    _assert_common_headers(server, mutating=True)
    assert link.id == "pl_1"
    assert link.response_meta is not None
    assert link.response_meta.status == 201


def test_payment_links_create_validation_error() -> None:
    server = FakeServer(
        json_response(
            400,
            {
                "errors": [{"code": "VALIDATION_FAILED", "description": "bad"}],
                "fieldErrors": [{"field": "title", "code": "NotBlank", "message": "required"}],
            },
        )
    )
    with _client(server) as danipa, pytest.raises(ValidationError) as info:
        danipa.payment_links.create(CreatePaymentLinkRequest(title=" "))
    assert info.value.field_errors[0].field == "title"


# ---------------------------------------------------------------------------
# payment_links.update
# ---------------------------------------------------------------------------


def test_payment_links_update_puts_partial_camelcase_body() -> None:
    updated = {**PAYMENT_LINK_BODY, "title": "Deposit (updated)", "isAmountFixed": False}
    server = FakeServer(json_response(200, updated))
    request = UpdatePaymentLinkRequest(
        title="Deposit (updated)",
        is_amount_fixed=False,
        min_amount=Decimal("5.00"),
        max_amount=Decimal("500.00"),
    )
    with _client(server) as danipa:
        link = danipa.payment_links.update(uuid.UUID(LINK_ID), request)
    assert server.last.method == "PUT"
    assert _path(server) == f"/ms/v1/merchants/me/payment-links/{LINK_ID}"
    assert server.json_body() == {
        "title": "Deposit (updated)",
        "isAmountFixed": False,
        "minAmount": "5.00",
        "maxAmount": "500.00",
    }
    _assert_common_headers(server, mutating=True)
    assert link.title == "Deposit (updated)"
    assert link.is_amount_fixed is False


def test_update_request_has_no_currency_or_customer() -> None:
    # The server's UpdatePaymentLinkRequest cannot change currency or customer.
    assert "currency" not in UpdatePaymentLinkRequest.model_fields
    assert "customer_id" not in UpdatePaymentLinkRequest.model_fields


def test_payment_links_update_not_found() -> None:
    server = FakeServer(json_response(404, {"code": "PAYMENT_LINK_NOT_FOUND", "description": "x"}))
    with _client(server) as danipa, pytest.raises(NotFoundError) as info:
        danipa.payment_links.update(LINK_ID, UpdatePaymentLinkRequest(title="t"))
    assert info.value.code == "PAYMENT_LINK_NOT_FOUND"


@pytest.mark.parametrize("bad_id", ["", "pl_1", "../invoices", "123", LINK_ID + "/send"])
def test_non_uuid_ids_are_rejected_before_sending(bad_id: str) -> None:
    server = FakeServer(json_response(200, INVOICE_BODY))
    with _client(server) as danipa:
        with pytest.raises(ValueError, match="must be a UUID"):
            danipa.invoices.get(bad_id)
        with pytest.raises(ValueError, match="must be a UUID"):
            danipa.payment_links.delete(bad_id)
        with pytest.raises(ValueError, match="must be a UUID"):
            danipa.invoices.void(bad_id)
    assert server.requests == []


def test_uuid_ids_are_sent_in_canonical_form() -> None:
    server = FakeServer(json_response(200, INVOICE_BODY))
    with _client(server) as danipa:
        danipa.invoices.get(LINK_ID.upper())
        danipa.invoices.get("{" + LINK_ID + "}")
    assert [r.url.path for r in server.requests] == [f"/ms/v1/merchants/me/invoices/{LINK_ID}"] * 2


def test_non_string_id_is_rejected() -> None:
    server = FakeServer(json_response(200, INVOICE_BODY))
    with _client(server) as danipa, pytest.raises(ValueError, match="must be a UUID"):
        danipa.invoices.get(42)  # type: ignore[arg-type]
    assert server.requests == []


@pytest.mark.parametrize(("page", "size"), [(-1, None), (None, 0), (None, 201), (0, -5)])
def test_paging_out_of_bounds_is_rejected_before_sending(page: int | None, size: int | None) -> None:
    server = FakeServer(json_response(200, _spring_page([])))
    with _client(server) as danipa:
        with pytest.raises(ValueError, match=r"page must be|size must be"):
            danipa.payment_links.list(page=page, size=size)
        with pytest.raises(ValueError, match=r"page must be|size must be"):
            danipa.invoices.list(page=page, size=size)
    assert server.requests == []


def test_paging_bounds_are_inclusive() -> None:
    server = FakeServer(json_response(200, _spring_page([])))
    with _client(server) as danipa:
        danipa.payment_links.list(page=0, size=1)
        danipa.invoices.list(page=0, size=200)
    assert dict(server.requests[1].url.params) == {"page": "0", "size": "200"}


# ---------------------------------------------------------------------------
# payment_links.delete
# ---------------------------------------------------------------------------


def test_payment_links_delete_204_means_deleted() -> None:
    server = FakeServer(raw_response(204, ""))
    with _client(server) as danipa:
        result = danipa.payment_links.delete(LINK_ID)
    assert server.last.method == "DELETE"
    assert _path(server) == f"/ms/v1/merchants/me/payment-links/{LINK_ID}"
    assert server.last.content == b""
    _assert_common_headers(server, mutating=True)
    assert "x-step-up-token" not in server.last.headers
    assert result.deleted is True
    assert result.action == "deleted"
    assert result.response_meta is not None
    assert result.response_meta.status == 204


def test_payment_links_delete_200_means_deactivated() -> None:
    body = {
        "action": "deactivated",
        "message": "Payment link has transactions and was deactivated instead of deleted.",
    }
    server = FakeServer(json_response(200, body))
    with _client(server) as danipa:
        result = danipa.payment_links.delete(LINK_ID)
    assert result.deleted is False
    assert result.action == "deactivated"
    assert result.message is not None


def test_payment_links_delete_scope_denied() -> None:
    server = FakeServer(_scope_denied())
    with _client(server) as danipa, pytest.raises(PermissionDeniedError):
        danipa.payment_links.delete(LINK_ID)


# ---------------------------------------------------------------------------
# invoices.create / list / get / send / void
# ---------------------------------------------------------------------------


def test_invoices_create_verb_path_body_and_parse() -> None:
    server = FakeServer(json_response(201, {**INVOICE_BODY, "status": "DRAFT"}))
    request = CreateInvoiceRequest(
        customer_name="Ama K.",
        line_items=[InvoiceLineItemRequest(description="Catering", quantity=1, unit_price=Decimal("9.99"))],
    )
    with _client(server) as danipa:
        invoice = danipa.invoices.create(request, options=RequestOptions(idempotency_key="inv-42"))
    assert server.last.method == "POST"
    assert _path(server) == "/ms/v1/merchants/me/invoices"
    assert server.last.headers["idempotency-key"] == "inv-42"
    assert server.json_body() == {
        "customerName": "Ama K.",
        "lineItems": [{"description": "Catering", "quantity": 1, "unitPrice": "9.99"}],
    }
    assert invoice.status is InvoiceStatus.DRAFT


def test_invoices_list_sends_filters_and_parses_page() -> None:
    server = FakeServer(json_response(200, _spring_page([INVOICE_BODY])))
    with _client(server) as danipa:
        page = danipa.invoices.list(status=InvoiceStatus.SENT, q="INV-00", page=0, size=50)
    assert server.last.method == "GET"
    assert _path(server) == "/ms/v1/merchants/me/invoices"
    assert dict(server.last.url.params) == {"status": "SENT", "q": "INV-00", "page": "0", "size": "50"}
    _assert_common_headers(server, mutating=False)
    assert isinstance(page.content[0], Invoice)
    assert page.content[0].total == Decimal("33.90")


def test_invoices_list_accepts_plain_string_status_and_omits_unset() -> None:
    server = FakeServer(json_response(200, _spring_page([])))
    with _client(server) as danipa:
        danipa.invoices.list(status="overdue")
    assert dict(server.last.url.params) == {"status": "OVERDUE"}


@pytest.mark.parametrize("bad", ["CANCELLED", "", "paid ", InvoiceStatus.UNKNOWN, "UNKNOWN"])
def test_invoices_list_rejects_unknown_status_filter_before_sending(bad: Any) -> None:
    server = FakeServer(json_response(200, _spring_page([])))
    with _client(server) as danipa, pytest.raises(ValueError, match="status filter must be one of"):
        danipa.invoices.list(status=bad)
    assert server.requests == []


@pytest.mark.parametrize("status", ["DRAFT", "SENT", "PAID", "OVERDUE", "VOIDED"])
def test_invoices_list_accepts_every_server_status(status: str) -> None:
    server = FakeServer(json_response(200, _spring_page([])))
    with _client(server) as danipa:
        danipa.invoices.list(status=InvoiceStatus(status))
    assert dict(server.last.url.params) == {"status": status}


def test_unknown_status_in_responses_parses_as_unknown() -> None:
    body = _spring_page([{**INVOICE_BODY, "status": "PARTIALLY_PAID"}])
    server = FakeServer(json_response(200, body))
    with _client(server) as danipa:
        page = danipa.invoices.list()
    assert page.content[0].status is InvoiceStatus.UNKNOWN


def test_invoices_get() -> None:
    server = FakeServer(json_response(200, INVOICE_BODY))
    with _client(server) as danipa:
        invoice = danipa.invoices.get(INVOICE_ID)
    assert server.last.method == "GET"
    assert _path(server) == f"/ms/v1/merchants/me/invoices/{INVOICE_ID}"
    _assert_common_headers(server, mutating=False)
    assert invoice.invoice_number == "INV-0001"


def test_invoices_get_reads_tax_held_when_present_and_none_when_absent() -> None:
    # #7615: a draft held for a tax-blocked subscription period carries "taxHeld": true (its tax
    # shows as 0 until it is sent); the server omits the field otherwise.
    held = FakeServer(json_response(200, {**INVOICE_BODY, "status": "DRAFT", "taxHeld": True}))
    with _client(held) as danipa:
        assert danipa.invoices.get(INVOICE_ID).tax_held is True
    plain = FakeServer(json_response(200, INVOICE_BODY))
    with _client(plain) as danipa:
        assert danipa.invoices.get(INVOICE_ID).tax_held is None


def test_invoices_get_other_environment_is_not_found() -> None:
    server = FakeServer(json_response(404, {"code": "INVOICE_NOT_FOUND", "description": "x"}))
    with _client(server) as danipa, pytest.raises(NotFoundError):
        danipa.invoices.get(INVOICE_ID)


def test_invoices_send() -> None:
    sent = {**INVOICE_BODY, "status": "SENT", "paymentLinkUrl": "https://pay.danipa.com/l/x"}
    server = FakeServer(json_response(200, sent))
    with _client(server) as danipa:
        invoice = danipa.invoices.send(INVOICE_ID)
    assert server.last.method == "POST"
    assert _path(server) == f"/ms/v1/merchants/me/invoices/{INVOICE_ID}/send"
    assert server.last.content == b""
    assert "content-type" not in server.last.headers
    _assert_common_headers(server, mutating=True)
    assert invoice.status is InvoiceStatus.SENT
    assert invoice.payment_link_url == "https://pay.danipa.com/l/x"


def test_invoices_send_not_draft_is_validation_error() -> None:
    server = FakeServer(json_response(422, {"code": "INVOICE_NOT_EDITABLE", "description": "x"}))
    with _client(server) as danipa, pytest.raises(ValidationError) as info:
        danipa.invoices.send(INVOICE_ID)
    assert info.value.code == "INVOICE_NOT_EDITABLE"


def test_invoices_void() -> None:
    voided = {**INVOICE_BODY, "status": "VOIDED", "voidedAt": "2026-02-02T00:00:00Z"}
    server = FakeServer(json_response(200, voided))
    with _client(server) as danipa:
        invoice = danipa.invoices.void(uuid.UUID(INVOICE_ID))
    assert server.last.method == "POST"
    assert _path(server) == f"/ms/v1/merchants/me/invoices/{INVOICE_ID}/void"
    _assert_common_headers(server, mutating=True)
    assert invoice.status is InvoiceStatus.VOIDED
    assert invoice.voided_at is not None


def test_invoices_void_paid_is_conflict() -> None:
    server = FakeServer(json_response(409, {"code": "INVOICE_ALREADY_PAID", "description": "x"}))
    with _client(server) as danipa, pytest.raises(ConflictError):
        danipa.invoices.void(INVOICE_ID)


# ---------------------------------------------------------------------------
# balances.list
# ---------------------------------------------------------------------------

BALANCES_BODY = [
    {"id": "wa_1", "currency": "CAD", "availableBalance": 1250.55, "pendingBalance": 0, "status": "ACTIVE"},
    {"id": "wa_2", "currency": "GHS", "availableBalance": 0.10, "pendingBalance": 12.5, "status": "ACTIVE"},
]


def test_balances_list() -> None:
    server = FakeServer(json_response(200, BALANCES_BODY))
    with _client(server) as danipa:
        balances = danipa.balances.list()
    assert server.last.method == "GET"
    assert _path(server) == "/ms/v1/merchants/me/wallet/balances"
    _assert_common_headers(server, mutating=False)
    assert [b.currency for b in balances] == ["CAD", "GHS"]
    assert all(isinstance(b, Balance) for b in balances)
    assert balances[0].available_balance == Decimal("1250.55")
    assert balances[1].available_balance == Decimal("0.10")
    assert balances[1].pending_balance == Decimal("12.5")
    assert balances[0].response_meta is not None


def test_balances_list_empty_until_settled() -> None:
    server = FakeServer(json_response(200, []))
    with _client(server) as danipa:
        assert danipa.balances.list() == []


def test_balances_list_non_array_is_parse_error() -> None:
    server = FakeServer(json_response(200, {"balances": []}))
    with _client(server) as danipa, pytest.raises(ResponseParseError, match="not a JSON array"):
        danipa.balances.list()


def test_balances_list_scope_denied() -> None:
    server = FakeServer(_scope_denied())
    with _client(server) as danipa, pytest.raises(PermissionDeniedError):
        danipa.balances.list()


# ---------------------------------------------------------------------------
# Async parity: every async method hits the same verb + path and parses.
# ---------------------------------------------------------------------------


def test_async_surface_end_to_end() -> None:
    server = FakeServer(
        json_response(200, _spring_page([PAYMENT_LINK_BODY])),  # payment_links.list
        json_response(201, PAYMENT_LINK_BODY),  # payment_links.create
        json_response(200, PAYMENT_LINK_BODY),  # payment_links.update
        raw_response(204, ""),  # payment_links.delete
        json_response(201, INVOICE_BODY),  # invoices.create
        json_response(200, _spring_page([INVOICE_BODY])),  # invoices.list
        json_response(200, INVOICE_BODY),  # invoices.get
        json_response(200, INVOICE_BODY),  # invoices.send
        json_response(200, {**INVOICE_BODY, "status": "VOIDED"}),  # invoices.void
        json_response(200, BALANCES_BODY),  # balances.list
        json_response(200, {"action": "deactivated"}),  # payment_links.delete (200)
    )
    invoice_request = CreateInvoiceRequest(
        customer_name="Ama K.",
        line_items=[InvoiceLineItemRequest(description="x", quantity=1, unit_price=Decimal("1.00"))],
    )

    async def run() -> None:
        async with _aclient(server) as danipa:
            page = await danipa.payment_links.list(page=0, size=10)
            assert page.content[0].id == "pl_1"
            await danipa.payment_links.create(CreatePaymentLinkRequest(title="t"))
            await danipa.payment_links.update(LINK_ID, UpdatePaymentLinkRequest(title="t2"))
            assert (await danipa.payment_links.delete(LINK_ID)).deleted is True
            await danipa.invoices.create(invoice_request)
            inv_page = await danipa.invoices.list(status="SENT", q="a", page=1, size=2)
            assert inv_page.total_elements == 41
            await danipa.invoices.get(INVOICE_ID)
            await danipa.invoices.send(INVOICE_ID)
            voided = await danipa.invoices.void(INVOICE_ID)
            assert voided.status is InvoiceStatus.VOIDED
            balances = await danipa.balances.list()
            assert balances[0].currency == "CAD"
            assert (await danipa.payment_links.delete(LINK_ID)).deleted is False

    asyncio.run(run())
    seen = [(r.method, r.url.path) for r in server.requests]
    links = "/ms/v1/merchants/me/payment-links"
    invoices = "/ms/v1/merchants/me/invoices"
    assert seen == [
        ("GET", links),
        ("POST", links),
        ("PUT", f"{links}/{LINK_ID}"),
        ("DELETE", f"{links}/{LINK_ID}"),
        ("POST", invoices),
        ("GET", invoices),
        ("GET", f"{invoices}/{INVOICE_ID}"),
        ("POST", f"{invoices}/{INVOICE_ID}/send"),
        ("POST", f"{invoices}/{INVOICE_ID}/void"),
        ("GET", "/ms/v1/merchants/me/wallet/balances"),
        ("DELETE", f"{links}/{LINK_ID}"),
    ]
    for request in server.requests:
        assert request.headers["x-api-key"] == "dk_test_secret"
        assert "authorization" not in request.headers
        assert ("idempotency-key" in request.headers) == (request.method != "GET")


def test_async_error_is_typed() -> None:
    server = FakeServer(_scope_denied())

    async def run() -> None:
        async with _aclient(server) as danipa:
            with pytest.raises(PermissionDeniedError):
                await danipa.balances.list()

    asyncio.run(run())
