# Danipa Python SDK

[![PyPI](https://img.shields.io/pypi/v/danipa.svg)](https://pypi.org/project/danipa/)
[![Python](https://img.shields.io/pypi/pyversions/danipa.svg)](https://pypi.org/project/danipa/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

Official Python SDK for the [Danipa](https://docs.danipa.com) fintech API: a sync and an `asyncio` client, typed errors, safe automatic retries, and webhook signature verification.

> **Status: 0.x, pre-release.** The API-key surface is small today: `merchants.me()` is the only route an API key can reach. `payment_links.create` and `invoices.create` are modelled on the server DTOs but answer `403 API_KEY_SCOPE_DENIED` to API keys until the API-key surface tracked in [#5573](https://github.com/Danipa/danipa-digital-platform/issues/5573) lands. See the [changelog](./CHANGELOG.md) for breaking changes.

## Install

```bash
pip install danipa
```

Requires **Python 3.10+** (tested on 3.10 to 3.14).

## Quick start

```python
import os
from danipa import Danipa

# The host is inferred from the key prefix:
#   dk_test_… → https://api.sandbox.danipa.com/ms
#   dk_live_… → https://api.danipa.com/ms   (production is not live yet)
with Danipa(api_key=os.environ["DANIPA_API_KEY"]) as danipa:
    merchant = danipa.merchants.me()
    print(merchant.business_name, merchant.billing_currency, merchant.kyb_status)
```

The key is sent as `X-API-Key`. The SDK never sends `Authorization` (the server rejects a request carrying both with `403 AMBIGUOUS_CREDENTIALS`).

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

| Resource | Methods | Route | API key today |
|---|---|---|---|
| `danipa.merchants` | `me()` | `GET /v1/merchants/me` | yes (`account:read` scope) |
| `danipa.payment_links` | `create(request)` | `POST /v1/merchants/me/payment-links` | not yet, #5573 |
| `danipa.invoices` | `create(request)` | `POST /v1/merchants/me/invoices` | not yet, #5573 |

```python
from decimal import Decimal
from danipa.models import CreateInvoiceRequest, CreatePaymentLinkRequest, InvoiceLineItemRequest

link = danipa.payment_links.create(
    CreatePaymentLinkRequest(title="Deposit", amount=Decimal("125.00"))  # currency defaults to the merchant's
)

invoice = danipa.invoices.create(
    CreateInvoiceRequest(
        customer_name="Ama K.",
        line_items=[InvoiceLineItemRequest(description="Catering", quantity=3, unit_price=Decimal("10.00"))],
    )
)
print(invoice.status)  # InvoiceStatus.SENT; an unknown future status parses as InvoiceStatus.UNKNOWN
```

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

## Links

- Source: <https://github.com/Danipa/python-sdk>
- Issues: <https://github.com/Danipa/python-sdk/issues>
- API docs: <https://docs.danipa.com>
- Changelog: [`CHANGELOG.md`](./CHANGELOG.md)

## License

MIT, see [`LICENSE`](./LICENSE).
