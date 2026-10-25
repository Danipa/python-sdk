# Danipa Python SDK

[![PyPI](https://img.shields.io/pypi/v/danipa.svg)](https://pypi.org/project/danipa/)
[![Python](https://img.shields.io/pypi/pyversions/danipa.svg)](https://pypi.org/project/danipa/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

Official Python SDK for the [Danipa](https://docs.danipa.com) fintech API: a sync and an `asyncio` client, typed errors, safe automatic retries, and webhook signature verification.

> **Status: 0.x, pre-release.** The SDK covers the whole API-key surface of the Danipa API: your merchant profile, payment links, invoices and operating balances (see [Resources](#resources)). It calls nothing an API key cannot reach. See the [changelog](./CHANGELOG.md) for breaking changes.

## Install

```bash
pip install danipa
```

Requires **Python 3.10+** (tested on 3.10 to 3.14).

## Quick start

```python
import os
from danipa import Danipa

# A dk_test_… key talks to sandbox out of the box; no other setup is needed.
with Danipa(api_key=os.environ["DANIPA_API_KEY"]) as danipa:
    merchant = danipa.merchants.me()
    print(merchant.business_name, merchant.billing_currency, merchant.kyb_status)
    for balance in danipa.balances.list():
        print(balance.currency, balance.available_balance)
```

The key is sent as `X-API-Key`. The SDK never sends `Authorization` (the server rejects a request carrying both with `403 AMBIGUOUS_CREDENTIALS`).

### Environments

The host comes from the key prefix, the same marker the server uses:

| Key | Host |
|---|---|
| `dk_test_…` | `https://api.sandbox.danipa.com/ms` (sandbox) |
| `dk_live_…` | `https://api.danipa.com/ms`. **Production is not live yet:** building the client raises `DanipaConfigurationError` ("production is not live yet — use a dk_test_ key against sandbox") unless you pass an explicit `base_url`. Nothing is sent. |
| anything else | `DanipaConfigurationError` when you build the client. The SDK never guesses. |

An explicit choice always wins: `Danipa(api_key=..., base_url="http://localhost:8080/ms")`, or `Danipa(api_key=..., environment="sandbox")` (`"sandbox"` or `"live"`). `base_url` beats `environment`.

### Async

```python
import asyncio
from danipa import AsyncDanipa

async def main() -> None:
    async with AsyncDanipa(api_key="dk_test_...") as danipa:
        merchant = await danipa.merchants.me()
        print(merchant.id)

asyncio.run(main())
```

`AsyncDanipa` runs on `httpx.AsyncClient` and shares the request building and retry policy with `Danipa`.

## Resources

Every route an API key can call, and nothing else. Each needs the scope shown; a key without it gets `403 API_KEY_SCOPE_DENIED` (`PermissionDeniedError`). A key only ever sees data of its own environment.

| Method | Route | Scope |
|---|---|---|
| `merchants.me()` → `Merchant` | `GET /v1/merchants/me` | `account:read` |
| `payment_links.create(request)` → `PaymentLink` | `POST /v1/merchants/me/payment-links` | `payments:write` |
| `payment_links.list(page=, size=)` → `Page[PaymentLink]` | `GET /v1/merchants/me/payment-links` | `payments:read` |
| `payment_links.update(id, request)` → `PaymentLink` | `PUT /v1/merchants/me/payment-links/{id}` | `payments:write` |
| `payment_links.delete(id)` → `DeletePaymentLinkResult` | `DELETE /v1/merchants/me/payment-links/{id}` | `payments:write` |
| `invoices.create(request)` → `Invoice` | `POST /v1/merchants/me/invoices` | `payments:write` |
| `invoices.list(status=, q=, page=, size=)` → `Page[Invoice]` | `GET /v1/merchants/me/invoices` | `payments:read` |
| `invoices.get(id)` → `Invoice` | `GET /v1/merchants/me/invoices/{id}` | `payments:read` |
| `invoices.send(id)` → `Invoice` | `POST /v1/merchants/me/invoices/{id}/send` | `payments:write` |
| `invoices.void(id)` → `Invoice` | `POST /v1/merchants/me/invoices/{id}/void` | `payments:write` |
| `balances.list()` → `list[Balance]` | `GET /v1/merchants/me/wallet/balances` | `payments:read` |

Ids must be UUIDs (`str` or `uuid.UUID`); anything else raises `ValueError` before a request is sent. `page` is zero-based; `size` is 1 to 200.

There is no "get one payment link" route for API keys: use `payment_links.list()`. Editing a draft invoice, the invoice PDF, invoice stats, recording an offline payment and bulk import are dashboard-only.

```python
from decimal import Decimal
from danipa.models import (
    CreateInvoiceRequest, CreatePaymentLinkRequest, InvoiceLineItemRequest,
    InvoiceStatus, UpdatePaymentLinkRequest,
)

# Payment links
link = danipa.payment_links.create(
    CreatePaymentLinkRequest(title="Deposit", amount=Decimal("125.00"))  # currency defaults to the merchant's
)
print(link.url)
danipa.payment_links.update(link.id, UpdatePaymentLinkRequest(title="Deposit (50%)"))
page = danipa.payment_links.list(page=0, size=50)       # page is zero-based; size 1 to 200
print(page.total_elements, [l.title for l in page.content], page.has_next)
result = danipa.payment_links.delete(link.id)
print(result.deleted)  # False when the link had payments: it is deactivated instead

# Invoices: create (DRAFT) → send (SENT, gets a payment link) → void
invoice = danipa.invoices.create(
    CreateInvoiceRequest(
        customer_name="Ama K.",
        customer_email="ama@example.com",
        line_items=[InvoiceLineItemRequest(description="Catering", quantity=3, unit_price=Decimal("10.00"))],
    )
)
invoice = danipa.invoices.send(invoice.id)
print(invoice.status, invoice.payment_link_url)  # InvoiceStatus.SENT
overdue = danipa.invoices.list(status=InvoiceStatus.OVERDUE, q="INV-")
danipa.invoices.void(invoice.id)

# Balances: one per currency held, empty until something settles
for balance in danipa.balances.list():
    print(balance.currency, balance.available_balance, balance.pending_balance)
```

An unknown future status parses as `InvoiceStatus.UNKNOWN` / `PaymentLinkStatus.UNKNOWN` instead of failing.

Money fields are `decimal.Decimal`. The server writes money as JSON numbers; the SDK parses them straight to `Decimal` (no float rounding) and sends money as decimal strings.

## Errors

```python
from danipa import (
    DanipaError, DanipaApiError, PermissionDeniedError, RateLimitError,
    ValidationError, DanipaNetworkError, ResponseParseError,
)

try:
    danipa.merchants.me()
except ValidationError as exc:          # 400 / 422
    for f in exc.field_errors:
        print(f.field, f.message)
except PermissionDeniedError as exc:    # 403, e.g. API_KEY_SCOPE_DENIED
    print(exc.code)
except RateLimitError as exc:           # 429 after retries
    print("retry after", exc.retry_after)
except DanipaApiError as exc:           # any other non-2xx
    print(exc)                          # "[HTTP 404 NOT_FOUND] ... (request_id=...)"
except ResponseParseError as exc:       # 2xx but unreadable body: the call may have succeeded
    print(exc.idempotency_key)
except DanipaNetworkError as exc:       # no response (DanipaConnectionError / DanipaTimeoutError)
    print(exc.cause, exc.idempotency_key)
```

| Class | When |
|---|---|
| `ValidationError` | 400 / 422, with `field_errors` |
| `AuthenticationError` | 401 |
| `PermissionDeniedError` | 403 |
| `NotFoundError` | 404 |
| `ConflictError` / `IdempotencyError` | 409 (`IdempotencyError` for `IDEMPOTENCY_*` codes) |
| `RateLimitError` | 429, with `retry_after` |
| `ServerError` | 5xx |
| `DanipaConnectionError`, `DanipaTimeoutError` | no response |
| `ResponseParseError` | 2xx whose body could not be parsed |
| `DanipaConfigurationError` | the client cannot be built as configured (e.g. a key with an unknown prefix); raised before anything is sent |

Every `DanipaApiError` carries `status`, `code`, `message`, `request_id` (from `X-Correlation-Id` / `X-Request-Id`, else the body's `correlationId` / `traceId`), `raw` (the parsed body), `headers`, `idempotency_key` and `idempotent_replay`. Both server error shapes are understood: the `ApiStatus` envelope and the flat `{code, description}` body.

## Idempotency, retries, timeouts

- **Idempotency.** Every POST/PUT/PATCH/DELETE carries an `Idempotency-Key`. Pass your own with `options=RequestOptions(idempotency_key="order-1234")` (max 255 characters), or let the SDK generate a UUIDv4. The same key is reused on every retry of that call. The key used and whether the server replayed a cached answer (`X-Idempotent-Replay: true`) are on `result.response_meta` (and on errors).
- **Retries.** Safe by construction: reads always, writes only because they always carry a key. Retried on connection errors, timeouts, and 408, 429, 502, 503, 504, never on 500, 501 or other 4xx. `Retry-After` is honoured (capped at 60 s); otherwise exponential backoff with full jitter (base 0.5 s, cap 8 s). `max_retries` is the number of retries (default 2; `0` disables).
- **Timeouts.** `timeout=` takes seconds or an `httpx.Timeout` (default 30 s).
- **Per call.** `RequestOptions(idempotency_key=..., timeout=..., max_retries=...)`.
- **Your own HTTP client.** `Danipa(api_key=..., http_client=httpx.Client(...))` / `AsyncDanipa(..., http_client=httpx.AsyncClient(...))` for proxies, mTLS or event hooks. The SDK does not close a client it did not create, and ignores any `Authorization` header or `auth` on it.

## Webhooks

Each delivery carries `X-Danipa-Signature`, `X-Danipa-Timestamp`, `X-Danipa-Event` and `X-Danipa-Delivery`. Verify the **raw body bytes** before parsing: re-serialising parsed JSON changes the bytes.

```python
from danipa import WebhookVerificationError, construct_event

try:
    event = construct_event(raw_body, request.headers, ["whsec_current", "whsec_previous"])
except WebhookVerificationError:
    ...  # respond 400
print(event.type, event.delivery_id, event.data)
```

- `construct_event(payload, headers, secrets, *, tolerance=300)` verifies, then returns a `WebhookEvent` (`type`, `delivery_id`, `timestamp`, `data`, `raw`). Headers are matched case-insensitively.
- `verify(payload, signature, timestamp, secret, *, tolerance=300) -> bool` (alias `verify_webhook`) if you only need a yes/no.
- `payload` may be `bytes` or `str`; `secret(s)` may be one string or a list (rotation: any match passes); `tolerance` is the allowed clock skew in seconds.

Cross-SDK parity: every Danipa SDK (Node, Java, Python, PHP) produces identical signatures for the vectors in `sdks/fixtures/webhook-hmac.json`. Drift is a release-blocker.

**FastAPI**

```python
from fastapi import FastAPI, HTTPException, Request
from danipa import WebhookVerificationError, construct_event

app = FastAPI()

@app.post("/webhooks/danipa")
async def webhook(request: Request) -> dict[str, bool]:
    try:
        event = construct_event(await request.body(), request.headers, SECRET)
    except WebhookVerificationError:
        raise HTTPException(status_code=400, detail="invalid signature")
    ...
    return {"ok": True}
```

**Flask**

```python
from flask import Flask, abort, request
from danipa import WebhookVerificationError, construct_event

app = Flask(__name__)

@app.post("/webhooks/danipa")
def webhook():
    try:
        event = construct_event(request.get_data(), request.headers, SECRET)
    except WebhookVerificationError:
        abort(400)
    ...
```

## Development

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e '.[dev]'
ruff check .
mypy --strict src/danipa tests
pytest            # coverage gate: 80 %
```

`tests/test_route_contract.py` pins the SDK's route set to the server's API-key route table: a method that calls a route a key cannot reach, or a missing one, fails CI. Inside the monorepo it also reads the route table from the fintech source.

Live check against sandbox (not run in CI; prints only step names and OK / FAIL, never the key or response bodies):

```bash
DANIPA_API_KEY=dk_test_... python examples/smoke_sandbox.py
```

## Links

- Source: <https://github.com/Danipa/python-sdk>
- Issues: <https://github.com/Danipa/python-sdk/issues>
- API docs: <https://docs.danipa.com>
- Changelog: [`CHANGELOG.md`](./CHANGELOG.md)

## License

MIT, see [`LICENSE`](./LICENSE).
