"""Sync client: what actually goes on the wire, and how responses map back.

Every test drives the public :class:`danipa.Danipa` surface through a fake
transport (``FakeServer``) that records the real outgoing requests, and a fake
clock (``sleeps``) that records backoff delays instead of sleeping.
"""

from __future__ import annotations

import json
import platform
import re
import uuid
from decimal import Decimal
from importlib import metadata
from typing import Any
from unittest.mock import patch

import httpx
import pydantic
import pytest

from danipa import (
    AuthenticationError,
    ConflictError,
    Danipa,
    DanipaApiError,
    DanipaConnectionError,
    DanipaError,
    DanipaNetworkError,
    DanipaTimeoutError,
    IdempotencyError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    RequestOptions,
    ResponseParseError,
    ServerError,
    ValidationError,
)
from danipa.http import (
    PRODUCTION_BASE_URL,
    SANDBOX_BASE_URL,
    _RequestSpec,
    _SyncHttp,
    infer_base_url,
)
from danipa.models import (
    CreateInvoiceRequest,
    CreatePaymentLinkRequest,
    InvoiceLineItemRequest,
    InvoiceStatus,
    PaymentLinkStatus,
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


def _client(server: FakeServer, **kwargs: Any) -> Danipa:
    return Danipa(api_key="dk_test_secret", transport=server.transport, **kwargs)


def _link_request() -> CreatePaymentLinkRequest:
    return CreatePaymentLinkRequest(title="Deposit", amount=Decimal("125.00"), currency="GHS")


# ---------------------------------------------------------------------------
# Host selection
# ---------------------------------------------------------------------------


def test_infer_base_url_by_prefix() -> None:
    assert infer_base_url("dk_test_abc") == SANDBOX_BASE_URL
    assert infer_base_url("dk_live_abc") == PRODUCTION_BASE_URL


@pytest.mark.parametrize(
    ("api_key", "expected_host"),
    [("dk_test_abc", "api.sandbox.danipa.com")],
)
def test_key_prefix_routes_to_host(api_key: str, expected_host: str) -> None:
    server = FakeServer(json_response(200, MERCHANT_BODY))
    with Danipa(api_key=api_key, transport=server.transport) as danipa:
        danipa.merchants.me()
    assert server.last.url.host == expected_host
    assert server.last.url.path == "/ms/v1/merchants/me"


def test_explicit_base_url_overrides_inference() -> None:
    server = FakeServer(json_response(200, MERCHANT_BODY))
    with _client(server, base_url="https://api.example.test/ms/") as danipa:
        danipa.merchants.me()
        assert danipa.base_url == "https://api.example.test/ms"
    assert str(server.last.url) == "https://api.example.test/ms/v1/merchants/me"


# ---------------------------------------------------------------------------
# Auth + identification headers
# ---------------------------------------------------------------------------


def test_sends_x_api_key_and_never_authorization() -> None:
    server = FakeServer(json_response(200, MERCHANT_BODY))
    with _client(server) as danipa:
        danipa.merchants.me()
    request = server.last
    assert request.headers["x-api-key"] == "dk_test_secret"
    assert "authorization" not in request.headers
    assert request.headers["accept"] == "application/json"
    assert "x-danipa-environment" not in request.headers


def test_injected_client_authorization_and_auth_are_stripped() -> None:
    server = FakeServer(json_response(200, MERCHANT_BODY))
    injected = httpx.Client(
        transport=server.transport,
        headers={"Authorization": "Bearer leaked-jwt"},
        auth=("user", "pass"),
    )
    with Danipa(api_key="dk_test_secret", http_client=injected) as danipa:
        danipa.merchants.me()
    assert "authorization" not in server.last.headers
    assert server.last.headers["x-api-key"] == "dk_test_secret"
    # the SDK does not close a client it did not create
    assert not injected.is_closed
    injected.close()


def test_owned_client_is_closed() -> None:
    danipa = Danipa(api_key="dk_test_x")
    danipa.close()
    danipa.close()  # idempotent
    assert danipa._http._client.is_closed


def test_user_agent_uses_package_metadata_version() -> None:
    server = FakeServer(json_response(200, MERCHANT_BODY))
    with _client(server) as danipa:
        danipa.merchants.me()
    expected = f"danipa-python/{metadata.version('danipa')} python/{platform.python_version()}"
    assert server.last.headers["user-agent"] == expected


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


def test_post_without_key_gets_generated_uuid4() -> None:
    server = FakeServer(json_response(201, PAYMENT_LINK_BODY))
    with _client(server) as danipa:
        link = danipa.payment_links.create(_link_request())
    sent = server.last.headers["idempotency-key"]
    assert UUID4.match(sent)
    assert "x-idempotency-key" not in server.last.headers
    assert link.response_meta is not None
    assert link.response_meta.idempotency_key == sent


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])
def test_no_mutating_request_leaves_without_a_key(method: str) -> None:
    server = FakeServer(json_response(200, {}))
    http = _SyncHttp("dk_test_x", transport=server.transport)
    http.request(_RequestSpec(method=method, path="/v1/anything", body={"a": 1}))
    assert UUID4.match(server.last.headers["idempotency-key"])
    http.close()


def test_get_carries_no_generated_key() -> None:
    server = FakeServer(json_response(200, MERCHANT_BODY))
    with _client(server) as danipa:
        danipa.merchants.me()
    assert "idempotency-key" not in server.last.headers


def test_each_call_gets_a_fresh_key() -> None:
    server = FakeServer(json_response(201, PAYMENT_LINK_BODY))
    with _client(server) as danipa:
        danipa.payment_links.create(_link_request())
        danipa.payment_links.create(_link_request())
    keys = {r.headers["idempotency-key"] for r in server.requests}
    assert len(keys) == 2


def test_key_is_stable_across_retries(sleeps: SleepRecorder) -> None:
    server = FakeServer(
        json_response(503, {}),
        httpx.ConnectError("reset"),
        json_response(201, PAYMENT_LINK_BODY),
    )
    with _client(server) as danipa:
        danipa.payment_links.create(_link_request())
    assert len(server.requests) == 3
    keys = {r.headers["idempotency-key"] for r in server.requests}
    assert len(keys) == 1
    # the body is byte-identical on every attempt too
    assert len({r.content for r in server.requests}) == 1


def test_caller_key_is_sent_verbatim_and_reused(sleeps: SleepRecorder) -> None:
    server = FakeServer(json_response(502, {}), json_response(201, PAYMENT_LINK_BODY))
    with _client(server) as danipa:
        danipa.payment_links.create(
            _link_request(), options=RequestOptions(idempotency_key="order-1234")
        )
    assert [r.headers["idempotency-key"] for r in server.requests] == ["order-1234"] * 2


def test_key_longer_than_255_is_rejected_before_sending() -> None:
    server = FakeServer(json_response(201, PAYMENT_LINK_BODY))
    with _client(server) as danipa, pytest.raises(ValueError, match="255"):
        danipa.payment_links.create(
            _link_request(), options=RequestOptions(idempotency_key="k" * 256)
        )
    assert server.requests == []


def test_key_of_exactly_255_is_allowed() -> None:
    server = FakeServer(json_response(201, PAYMENT_LINK_BODY))
    with _client(server) as danipa:
        danipa.payment_links.create(
            _link_request(), options=RequestOptions(idempotency_key="k" * 255)
        )
    assert server.last.headers["idempotency-key"] == "k" * 255


def test_empty_key_is_rejected() -> None:
    server = FakeServer(json_response(201, PAYMENT_LINK_BODY))
    with _client(server) as danipa, pytest.raises(ValueError, match="empty"):
        danipa.payment_links.create(_link_request(), options=RequestOptions(idempotency_key=""))
    assert server.requests == []


def test_replay_header_is_exposed_on_response() -> None:
    server = FakeServer(json_response(201, PAYMENT_LINK_BODY, {"X-Idempotent-Replay": "true"}))
    with _client(server) as danipa:
        link = danipa.payment_links.create(_link_request())
    assert link.response_meta is not None
    assert link.response_meta.idempotent_replay is True


def test_fresh_response_is_not_marked_replay() -> None:
    server = FakeServer(json_response(201, PAYMENT_LINK_BODY))
    with _client(server) as danipa:
        link = danipa.payment_links.create(_link_request())
    assert link.response_meta is not None
    assert link.response_meta.idempotent_replay is False


# ---------------------------------------------------------------------------
# Retries
# ---------------------------------------------------------------------------


def test_429_retry_after_is_honoured(sleeps: SleepRecorder) -> None:
    server = FakeServer(
        json_response(429, {"code": "RATE_LIMIT_EXCEEDED"}, {"Retry-After": "7"}),
        json_response(200, MERCHANT_BODY),
    )
    with _client(server) as danipa:
        merchant = danipa.merchants.me()
    assert merchant.id == MERCHANT_BODY["id"]
    assert len(server.requests) == 2
    assert sleeps.delays == [7.0]


def test_retry_after_is_capped_at_60s(sleeps: SleepRecorder) -> None:
    server = FakeServer(
        json_response(503, {}, {"Retry-After": "3600"}), json_response(200, MERCHANT_BODY)
    )
    with _client(server) as danipa:
        danipa.merchants.me()
    assert sleeps.delays == [60.0]


@pytest.mark.parametrize("retry_after", ["Wed, 21 Oct 2026 07:28:00 GMT", "-5", "nan"])
def test_unusable_retry_after_falls_back_to_backoff(
    sleeps: SleepRecorder, retry_after: str
) -> None:
    server = FakeServer(
        json_response(503, {}, {"Retry-After": retry_after}), json_response(200, MERCHANT_BODY)
    )
    with _client(server) as danipa:
        danipa.merchants.me()
    assert len(sleeps.delays) == 1
    assert 0.0 <= sleeps.delays[0] <= 0.5


def test_backoff_is_full_jitter_with_base_and_cap(sleeps: SleepRecorder) -> None:
    server = FakeServer(json_response(503, {}))
    ceilings: list[float] = []

    def fake_uniform(low: float, high: float) -> float:
        assert low == 0.0
        ceilings.append(high)
        return high

    with (
        patch("danipa.http.random.uniform", fake_uniform),
        _client(server, max_retries=6) as danipa,
        pytest.raises(ServerError),
    ):
        danipa.merchants.me()
    assert ceilings == [0.5, 1.0, 2.0, 4.0, 8.0, 8.0]
    assert sleeps.delays == ceilings


@pytest.mark.parametrize("status", [408, 429, 502, 503, 504])
def test_transient_statuses_are_retried(sleeps: SleepRecorder, status: int) -> None:
    server = FakeServer(json_response(status, {}), json_response(200, MERCHANT_BODY))
    with _client(server) as danipa:
        danipa.merchants.me()
    assert len(server.requests) == 2


@pytest.mark.parametrize("status", [400, 401, 403, 404, 409, 422, 500, 501])
def test_non_transient_statuses_are_not_retried(sleeps: SleepRecorder, status: int) -> None:
    server = FakeServer(json_response(status, {"code": "X"}), json_response(200, MERCHANT_BODY))
    with _client(server) as danipa, pytest.raises(DanipaApiError):
        danipa.merchants.me()
    assert len(server.requests) == 1
    assert sleeps.delays == []


def test_500_on_post_is_not_retried(sleeps: SleepRecorder) -> None:
    server = FakeServer(json_response(500, {}), json_response(201, PAYMENT_LINK_BODY))
    with _client(server) as danipa, pytest.raises(ServerError) as exc:
        danipa.payment_links.create(_link_request())
    assert len(server.requests) == 1
    assert exc.value.status == 500


def test_default_budget_is_two_retries(sleeps: SleepRecorder) -> None:
    server = FakeServer(json_response(503, {}))
    with _client(server) as danipa, pytest.raises(ServerError) as exc:
        danipa.merchants.me()
    assert len(server.requests) == 3
    assert exc.value.status == 503


def test_max_retries_zero_disables_retries(sleeps: SleepRecorder) -> None:
    server = FakeServer(json_response(503, {}))
    with _client(server, max_retries=0) as danipa, pytest.raises(ServerError):
        danipa.merchants.me()
    assert len(server.requests) == 1


def test_per_call_max_retries_overrides_client(sleeps: SleepRecorder) -> None:
    server = FakeServer(json_response(503, {}))
    with _client(server, max_retries=0) as danipa, pytest.raises(ServerError):
        danipa.merchants.me(options=RequestOptions(max_retries=3))
    assert len(server.requests) == 4


def test_negative_max_retries_is_rejected() -> None:
    with pytest.raises(ValueError, match="max_retries"):
        Danipa(api_key="dk_test_x", max_retries=-1)
    server = FakeServer(json_response(200, MERCHANT_BODY))
    with _client(server) as danipa, pytest.raises(ValueError, match="max_retries"):
        danipa.merchants.me(options=RequestOptions(max_retries=-1))


def test_empty_api_key_is_rejected() -> None:
    with pytest.raises(TypeError, match="api_key"):
        Danipa(api_key="")


# ---------------------------------------------------------------------------
# Transport failures
# ---------------------------------------------------------------------------


def test_connect_error_retried_then_connection_error(sleeps: SleepRecorder) -> None:
    server = FakeServer(httpx.ConnectError("refused"))
    with _client(server) as danipa, pytest.raises(DanipaConnectionError) as exc:
        danipa.payment_links.create(_link_request())
    assert len(server.requests) == 3
    assert isinstance(exc.value.cause, httpx.ConnectError)
    assert exc.value.idempotency_key == server.last.headers["idempotency-key"]
    assert isinstance(exc.value, DanipaNetworkError)
    assert not isinstance(exc.value, DanipaApiError)


def test_timeout_maps_to_timeout_error(sleeps: SleepRecorder) -> None:
    server = FakeServer(httpx.ReadTimeout("slow"))
    with _client(server, max_retries=1) as danipa, pytest.raises(DanipaTimeoutError):
        danipa.merchants.me()
    assert len(server.requests) == 2


def test_connect_error_then_success(sleeps: SleepRecorder) -> None:
    server = FakeServer(httpx.ConnectError("refused"), json_response(200, MERCHANT_BODY))
    with _client(server) as danipa:
        assert danipa.merchants.me().billing_currency == "CAD"


def test_malformed_request_errors_are_not_retried(sleeps: SleepRecorder) -> None:
    server = FakeServer(httpx.UnsupportedProtocol("bad scheme"))
    with _client(server) as danipa, pytest.raises(DanipaConnectionError):
        danipa.merchants.me()
    assert len(server.requests) == 1


# ---------------------------------------------------------------------------
# Timeouts
# ---------------------------------------------------------------------------


def test_httpx_timeout_object_reaches_the_request() -> None:
    server = FakeServer(json_response(200, MERCHANT_BODY))
    timeout = httpx.Timeout(5.0, connect=2.0)
    with _client(server, timeout=timeout) as danipa:
        danipa.merchants.me()
    assert server.last.extensions["timeout"] == timeout.as_dict()


def test_per_call_timeout_overrides_client() -> None:
    server = FakeServer(json_response(200, MERCHANT_BODY))
    with _client(server, timeout=30.0) as danipa:
        danipa.merchants.me(options=RequestOptions(timeout=1.5))
    assert server.last.extensions["timeout"]["read"] == 1.5


# ---------------------------------------------------------------------------
# Error mapping: both server shapes
# ---------------------------------------------------------------------------


def test_api_status_envelope_maps_to_validation_error() -> None:
    body = {
        "timeStamp": 1711814400000,
        "correlationId": "corr-envelope",
        "traceId": "trace-1",
        "statusCode": 422,
        "severity": "ERROR",
        "retryable": False,
        "messageKey": "error.invoice.invalid",
        "errors": [{"code": "INVALID_LINE_ITEM", "description": "unitPrice must be positive"}],
        "fieldErrors": [
            {"field": "lineItems[0].unitPrice", "code": "DecimalMin", "message": "must be >= 0.01"}
        ],
    }
    server = FakeServer(json_response(422, body))
    with _client(server) as danipa, pytest.raises(ValidationError) as exc:
        danipa.merchants.me()
    err = exc.value
    assert (err.status, err.code, err.message) == (
        422,
        "INVALID_LINE_ITEM",
        "unitPrice must be positive",
    )
    assert err.request_id == "corr-envelope"
    assert err.trace_id == "trace-1"
    assert err.correlation_id == "corr-envelope"
    assert err.message_key == "error.invoice.invalid"
    assert err.retryable is False
    assert err.field_errors[0].field == "lineItems[0].unitPrice"
    assert err.field_errors[0].message == "must be >= 0.01"
    assert err.raw == body


def test_flat_filter_shape_maps_to_permission_denied() -> None:
    server = FakeServer(
        json_response(
            403,
            {
                "code": "API_KEY_SCOPE_DENIED",
                "description": "API key access is not permitted for this request",
            },
        )
    )
    with _client(server) as danipa, pytest.raises(PermissionDeniedError) as exc:
        danipa.payment_links.create(_link_request())
    assert exc.value.code == "API_KEY_SCOPE_DENIED"
    assert exc.value.message == "API key access is not permitted for this request"
    assert exc.value.idempotency_key == server.last.headers["idempotency-key"]


@pytest.mark.parametrize(
    ("status", "code", "cls"),
    [
        (400, "IDEMPOTENCY_KEY_TOO_LONG", ValidationError),
        (401, "INVALID_API_KEY", AuthenticationError),
        (403, "AMBIGUOUS_CREDENTIALS", PermissionDeniedError),
        (404, "NOT_FOUND", NotFoundError),
        (409, "IDEMPOTENCY_KEY_COLLISION", IdempotencyError),
        (409, "INVOICE_ALREADY_PAID", ConflictError),
        (429, "RATE_LIMIT_EXCEEDED", RateLimitError),
        (500, "INTERNAL_ERROR", ServerError),
        (413, "PAYLOAD_TOO_LARGE", DanipaApiError),
    ],
)
def test_status_maps_to_typed_error(status: int, code: str, cls: type[DanipaApiError]) -> None:
    server = FakeServer(json_response(status, {"code": code, "description": "nope"}))
    with _client(server, max_retries=0) as danipa, pytest.raises(cls) as exc:
        danipa.merchants.me()
    assert type(exc.value) is cls
    assert exc.value.code == code
    assert isinstance(exc.value, DanipaError)


def test_plain_409_is_not_an_idempotency_error() -> None:
    server = FakeServer(json_response(409, {"code": "INVOICE_ALREADY_PAID"}))
    with _client(server) as danipa, pytest.raises(ConflictError) as exc:
        danipa.merchants.me()
    assert not isinstance(exc.value, IdempotencyError)


def test_rate_limit_error_carries_retry_after() -> None:
    server = FakeServer(
        json_response(429, {"code": "RATE_LIMIT_EXCEEDED"}, {"Retry-After": "60"})
    )
    with _client(server, max_retries=0) as danipa, pytest.raises(RateLimitError) as exc:
        danipa.merchants.me()
    assert exc.value.retry_after == 60.0


def test_retry_after_falls_back_to_envelope_field() -> None:
    server = FakeServer(
        json_response(429, {"errors": [{"code": "SLOW_DOWN"}], "retryAfterSeconds": 12})
    )
    with _client(server, max_retries=0) as danipa, pytest.raises(RateLimitError) as exc:
        danipa.merchants.me()
    assert exc.value.retry_after == 12.0


@pytest.mark.parametrize(
    ("headers", "body", "expected"),
    [
        ({"X-Correlation-Id": "hdr-corr", "X-Request-Id": "hdr-req"}, {"correlationId": "b"}, "hdr-corr"),
        ({"X-Request-Id": "hdr-req"}, {"correlationId": "b"}, "hdr-req"),
        ({}, {"correlationId": "body-corr", "traceId": "t"}, "body-corr"),
        ({}, {"traceId": "body-trace"}, "body-trace"),
        ({}, {}, None),
    ],
)
def test_request_id_precedence(
    headers: dict[str, str], body: dict[str, str], expected: str | None
) -> None:
    server = FakeServer(json_response(404, body, headers))
    with _client(server) as danipa, pytest.raises(NotFoundError) as exc:
        danipa.merchants.me()
    assert exc.value.request_id == expected


def test_str_includes_status_code_and_request_id() -> None:
    server = FakeServer(
        json_response(401, {"code": "INVALID_API_KEY", "description": "Invalid or expired API key"},
                      {"X-Correlation-Id": "corr-9"})
    )
    with _client(server) as danipa, pytest.raises(AuthenticationError) as exc:
        danipa.merchants.me()
    text = str(exc.value)
    assert "401" in text
    assert "INVALID_API_KEY" in text
    assert "Invalid or expired API key" in text
    assert "corr-9" in text
    assert "AuthenticationError" in repr(exc.value)


def test_unparseable_error_body_falls_back_to_status() -> None:
    server = FakeServer(raw_response(400, "<html>bad gateway</html>"))
    with _client(server) as danipa, pytest.raises(ValidationError) as exc:
        danipa.merchants.me()
    assert exc.value.code == "UNKNOWN"
    assert exc.value.message == "HTTP 400"
    assert exc.value.raw == "<html>bad gateway</html>"
    assert "HTTP 400 UNKNOWN" in str(exc.value)


def test_error_replay_header_is_exposed() -> None:
    server = FakeServer(
        json_response(422, {"code": "BAD"}, {"X-Idempotent-Replay": "true"})
    )
    with _client(server) as danipa, pytest.raises(ValidationError) as exc:
        danipa.payment_links.create(_link_request())
    assert exc.value.idempotent_replay is True


# ---------------------------------------------------------------------------
# 2xx parse failures are their own error, never a network error
# ---------------------------------------------------------------------------


def test_2xx_invalid_json_is_response_parse_error() -> None:
    server = FakeServer(raw_response(201, "{not json", {"X-Correlation-Id": "c-1"}))
    with _client(server) as danipa, pytest.raises(ResponseParseError) as exc:
        danipa.payment_links.create(_link_request())
    err = exc.value
    assert not isinstance(err, DanipaNetworkError)
    assert not isinstance(err, DanipaApiError)
    assert err.status == 201
    assert err.body == "{not json"
    assert err.request_id == "c-1"
    assert err.idempotency_key == server.last.headers["idempotency-key"]
    assert len(server.requests) == 1  # never retried: the call may have succeeded


def test_2xx_body_not_matching_model_is_response_parse_error() -> None:
    server = FakeServer(json_response(200, {"businessName": "no id"}))
    with _client(server) as danipa, pytest.raises(ResponseParseError, match="Merchant"):
        danipa.merchants.me()


def test_2xx_empty_body_is_response_parse_error_for_a_model() -> None:
    server = FakeServer(raw_response(200, ""))
    with _client(server) as danipa, pytest.raises(ResponseParseError):
        danipa.merchants.me()


def test_2xx_empty_body_returns_none_from_core() -> None:
    server = FakeServer(httpx.Response(204))
    http = _SyncHttp("dk_test_x", transport=server.transport)
    body, meta = http.request(_RequestSpec(method="DELETE", path="/v1/x"))
    assert body is None
    assert meta.status == 204
    http.close()


# ---------------------------------------------------------------------------
# merchants.me()
# ---------------------------------------------------------------------------


def test_merchants_me_parses_merchant_response() -> None:
    server = FakeServer(json_response(200, MERCHANT_BODY, {"X-Correlation-Id": "c-me"}))
    with _client(server) as danipa:
        merchant = danipa.merchants.me()
    assert server.last.method == "GET"
    assert server.last.url.path == "/ms/v1/merchants/me"
    assert merchant.business_name == "Kin & Calabash"
    assert merchant.kyb_status == "APPROVED"
    assert merchant.public_catalog_enabled is True
    assert merchant.billing_currency == "CAD"
    assert merchant.effective_default_tax_rate_pct == Decimal("13.00")
    assert merchant.default_tax_rate_pct is None  # absent on the wire (NON_NULL)
    assert merchant.created_at is not None and merchant.created_at.year == 2026
    assert merchant.response_meta is not None
    assert merchant.response_meta.request_id == "c-me"
    assert merchant.response_meta.idempotency_key is None


def test_merchant_parses_canadian_tax_registration_numbers() -> None:
    body = {**MERCHANT_BODY, "gstHstNumber": "123456789RT0001", "qstNumber": "1234567890TQ0001"}
    server = FakeServer(json_response(200, body))
    with _client(server) as danipa:
        merchant = danipa.merchants.me()
    assert merchant.gst_hst_number == "123456789RT0001"
    assert merchant.qst_number == "1234567890TQ0001"


def test_merchant_tax_registration_numbers_default_to_none() -> None:
    server = FakeServer(json_response(200, MERCHANT_BODY))
    with _client(server) as danipa:
        merchant = danipa.merchants.me()
    assert merchant.gst_hst_number is None
    assert merchant.qst_number is None


def test_merchant_ignores_unknown_fields() -> None:
    server = FakeServer(json_response(200, {**MERCHANT_BODY, "brandNewField": {"x": 1}}))
    with _client(server) as danipa:
        assert danipa.merchants.me().id == MERCHANT_BODY["id"]


# ---------------------------------------------------------------------------
# Payment links + invoices: models from the server DTOs, money as Decimal
# ---------------------------------------------------------------------------


def test_payment_link_request_body_is_camelcase_with_string_money() -> None:
    server = FakeServer(json_response(201, PAYMENT_LINK_BODY))
    with _client(server) as danipa:
        danipa.payment_links.create(
            CreatePaymentLinkRequest(
                title="Tip jar",
                is_amount_fixed=False,
                min_amount=Decimal("5.00"),
                max_amount=Decimal("500.00"),
                redirect_url="https://example.com/thanks",
                customer_id="4c2a0000-0000-4000-8000-000000000000",
            )
        )
    assert server.last.method == "POST"
    assert server.last.url.path == "/ms/v1/merchants/me/payment-links"
    assert server.last.headers["content-type"] == "application/json"
    assert server.json_body() == {
        "title": "Tip jar",
        "isAmountFixed": False,
        "minAmount": "5.00",
        "maxAmount": "500.00",
        "redirectUrl": "https://example.com/thanks",
        "customerId": "4c2a0000-0000-4000-8000-000000000000",
    }


def test_money_is_parsed_from_json_number_without_float_rounding() -> None:
    body = json.dumps({**PAYMENT_LINK_BODY, "amount": 0}).replace(
        '"amount": 0', '"amount": 125.10'
    )
    body = body.replace('"totalCollected": 0', '"totalCollected": 1234567890123.45')
    server = FakeServer(raw_response(201, body))
    with _client(server) as danipa:
        link = danipa.payment_links.create(_link_request())
    assert link.amount == Decimal("125.10")
    assert str(link.amount) == "125.10"
    assert link.total_collected == Decimal("1234567890123.45")
    assert link.status is PaymentLinkStatus.ACTIVE


def test_money_also_accepts_json_string() -> None:
    server = FakeServer(json_response(201, {**PAYMENT_LINK_BODY, "amount": "99.99"}))
    with _client(server) as danipa:
        assert danipa.payment_links.create(_link_request()).amount == Decimal("99.99")


def test_unknown_payment_link_status_parses_as_unknown() -> None:
    server = FakeServer(json_response(201, {**PAYMENT_LINK_BODY, "status": "PAUSED"}))
    with _client(server) as danipa:
        assert danipa.payment_links.create(_link_request()).status is PaymentLinkStatus.UNKNOWN


def _invoice_request() -> CreateInvoiceRequest:
    return CreateInvoiceRequest(
        customer_name="Ama K.",
        customer_phone="+233244112233",
        line_items=[
            InvoiceLineItemRequest(
                description="Catering", quantity=3, unit_price=Decimal("10.00"),
                tax_rate_pct=Decimal("13"),
            )
        ],
        tax_amount=Decimal("3.90"),
    )


def test_invoice_request_body_matches_server_dto() -> None:
    server = FakeServer(json_response(201, INVOICE_BODY))
    with _client(server) as danipa:
        invoice = danipa.invoices.create(_invoice_request())
    assert server.last.url.path == "/ms/v1/merchants/me/invoices"
    assert server.json_body() == {
        "customerName": "Ama K.",
        "customerPhone": "+233244112233",
        "lineItems": [
            {"description": "Catering", "quantity": 3, "unitPrice": "10.00", "taxRatePct": "13"}
        ],
        "taxAmount": "3.90",
    }
    assert invoice.status is InvoiceStatus.SENT
    assert invoice.total == Decimal("33.9")
    assert invoice.line_items[0].line_total == Decimal("30.0")
    assert invoice.tax_breakdown is not None
    assert invoice.tax_breakdown[0].label == "HST 13%"
    assert str(invoice.due_date) == "2026-02-01"


def test_invoice_request_requires_a_line_item() -> None:
    with pytest.raises(pydantic.ValidationError, match=r"line_items|lineItems"):
        CreateInvoiceRequest(customer_name="x", line_items=[])


@pytest.mark.parametrize(
    ("wire", "expected"),
    [
        ("DRAFT", InvoiceStatus.DRAFT),
        ("PAID", InvoiceStatus.PAID),
        ("OVERDUE", InvoiceStatus.OVERDUE),
        ("VOIDED", InvoiceStatus.VOIDED),
        ("ARCHIVED", InvoiceStatus.UNKNOWN),
    ],
)
def test_invoice_status_parses_known_and_unknown(wire: str, expected: InvoiceStatus) -> None:
    server = FakeServer(json_response(201, {**INVOICE_BODY, "status": wire}))
    with _client(server) as danipa:
        assert danipa.invoices.create(_invoice_request()).status is expected


def test_generated_key_is_a_valid_uuid() -> None:
    server = FakeServer(json_response(201, INVOICE_BODY))
    with _client(server) as danipa:
        danipa.invoices.create(_invoice_request())
    assert uuid.UUID(server.last.headers["idempotency-key"]).version == 4


def test_raw_decimal_body_is_sent_as_string() -> None:
    server = FakeServer(json_response(200, {}))
    http = _SyncHttp("dk_test_x", transport=server.transport)
    http.request(_RequestSpec(method="POST", path="v1/x", body={"amount": Decimal("1.50")}))
    assert server.last.url.path == "/ms/v1/x"
    assert server.json_body() == {"amount": "1.50"}
    with pytest.raises(TypeError, match="not JSON serializable"):
        http.request(_RequestSpec(method="POST", path="/v1/x", body={"x": object()}))
    http.close()


def test_non_transport_request_errors_are_not_retried(sleeps: SleepRecorder) -> None:
    server = FakeServer(httpx.DecodingError("bad gzip"))
    with _client(server) as danipa, pytest.raises(DanipaConnectionError):
        danipa.merchants.me()
    assert len(server.requests) == 1


def test_query_params_drop_none() -> None:
    server = FakeServer(json_response(200, {}))
    http = _SyncHttp("dk_test_x", transport=server.transport)
    http.request(_RequestSpec(method="GET", path="/v1/x", query={"a": "1", "b": None}))
    assert dict(server.last.url.params) == {"a": "1"}
    http.close()


def test_field_errors_skip_malformed_entries() -> None:
    server = FakeServer(
        json_response(400, {"errors": ["oops"], "fieldErrors": ["bad", {"field": "title"}]})
    )
    with _client(server) as danipa, pytest.raises(ValidationError) as exc:
        danipa.merchants.me()
    assert exc.value.code == "UNKNOWN"
    assert [f.field for f in exc.value.field_errors] == ["title"]
