# Danipa Python SDK

[![PyPI](https://img.shields.io/pypi/v/danipa.svg)](https://pypi.org/project/danipa/)
[![Python](https://img.shields.io/pypi/pyversions/danipa.svg)](https://pypi.org/project/danipa/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](./LICENSE)

Official Python SDK for the [Danipa](https://docs.danipa.com) fintech API — collections, disbursements, wallets, payment links, invoices, and webhook signature verification.

## Install

```bash
pip install danipa
```

Requires **Python 3.10+**.

## Quick start

```python
import os
from danipa import Danipa, RequestOptions
from danipa.models import CreateCollectionRequest, Payer

# Sandbox vs production is inferred from the API key prefix:
#   dk_test_… → https://api.sandbox.danipa.com
#   dk_live_… → https://api.danipa.com
with Danipa(api_key=os.environ["DANIPA_API_KEY"]) as danipa:
    collection = danipa.collections.create(
        CreateCollectionRequest(
            amount="125.00",
            currency="GHS",
            payer=Payer(phone="+233244112233", name="Ama K."),
        ),
        options=RequestOptions(idempotency_key="order-1234"),
    )
```

## Resources

| Resource | Methods |
|---|---|
| `danipa.collections` | `create`, `get` |
| `danipa.disbursements` | `create`, `get` |
| `danipa.wallets` | `get_balance` |
| `danipa.payment_links` | `create` |
| `danipa.invoices` | `create` |

## Errors

```python
from danipa import DanipaApiError, DanipaNetworkError

try:
    danipa.collections.create(...)
except DanipaApiError as exc:
    # Backend returned a non-2xx response
    print(exc.status, exc.code, exc.correlation_id, exc.raw)
except DanipaNetworkError as exc:
    # Transport failure (DNS, TLS, timeout). exc.cause is the underlying httpx error.
    ...
```

`DanipaApiError` and `DanipaNetworkError` both inherit from `DanipaError` — catch the base class once and narrow if you need the details.

## Idempotency, retries, timeouts

- Pass `options=RequestOptions(idempotency_key=...)` on every mutating call. Backend dedupes on `(merchantId, key)` so retries (server- or client-side) won't double-charge.
- Default retry policy: 3 attempts on 5xx and transport failures, with `200 ms × 2^(attempt - 1)` exponential backoff capped at 2 s, plus 0–50 ms jitter. **4xx responses never retry** — they indicate a client-side fix is needed.
- Override per client: `Danipa(api_key=..., timeout=30.0, max_retries=3)`. Override per call: `RequestOptions(timeout=10.0)`.

## Webhook signature verification

```python
from danipa import verify_webhook

if not verify_webhook(payload, signature, timestamp, secret):
    raise PermissionError("invalid signature")
```

Cross-SDK parity: every Danipa SDK (Node, Java, Python, PHP) produces identical signatures for the same `(payload, secret, timestamp)` triple. Drift is treated as a release-blocker.

### Framework examples

**FastAPI**

```python
from fastapi import FastAPI, Header, HTTPException, Request
from danipa import verify_webhook

app = FastAPI()

@app.post("/webhooks/danipa")
async def webhook(
    request: Request,
    x_danipa_signature: str = Header(...),
    x_danipa_timestamp: str = Header(...),
):
    body = (await request.body()).decode("utf-8")
    if not verify_webhook(body, x_danipa_signature, x_danipa_timestamp, SECRET):
        raise HTTPException(status_code=401, detail="invalid signature")
    ...
```

**Flask**

```python
from flask import Flask, request, abort
from danipa import verify_webhook

app = Flask(__name__)

@app.post("/webhooks/danipa")
def webhook():
    if not verify_webhook(
        request.get_data(as_text=True),
        request.headers.get("X-Danipa-Signature", ""),
        request.headers.get("X-Danipa-Timestamp", ""),
        SECRET,
    ):
        abort(401)
    ...
```

## Development

```bash
pip install -e '.[dev]'
ruff check
mypy --strict src/danipa tests
pytest
```

## Links

- Source: <https://github.com/Danipa/python-sdk>
- Issues: <https://github.com/Danipa/python-sdk/issues>
- API docs: <https://docs.danipa.com>
- Changelog: [`CHANGELOG.md`](./CHANGELOG.md)

## License

MIT — see [`LICENSE`](./LICENSE).
