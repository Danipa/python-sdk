# Danipa Python SDK

Official Python SDK for the [Danipa](https://docs.danipa.com) fintech API — collections, disbursements, wallets, payment links, invoices, and webhook signature verification.

> **Status: 0.1.0 in development.** This Stage 1 commit is the package skeleton (build config, layout, version pin). The public API surface (`Danipa`, `RequestOptions`, exception classes, `verify_webhook`) lands in Stage 2. Track progress in [`docs/milestones/SDK_PYTHON_PUBLISH.md`](../../docs/milestones/SDK_PYTHON_PUBLISH.md).

## Install

```bash
pip install danipa
```

Requires **Python 3.10+**.

## Quick start (target API for 0.1.0)

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

## Resources (target for 0.1.0)

| Resource | Methods |
|---|---|
| `danipa.collections` | `create`, `get`, `list` |
| `danipa.disbursements` | `create`, `get`, `list` |
| `danipa.wallets` | `get`, `list` |
| `danipa.payment_links` | `create`, `get`, `list` |
| `danipa.invoices` | `create`, `get`, `list` |

## Webhook signature verification (target for 0.1.0)

```python
from danipa import verify_webhook

if not verify_webhook(payload, signature, timestamp, secret):
    raise PermissionError("invalid signature")
```

Cross-SDK parity: every Danipa SDK (Node, Java, Python, PHP) produces identical signatures for the vectors in [`sdks/fixtures/webhook-hmac.json`](../fixtures/webhook-hmac.json).

## Development

```bash
pip install -e '.[dev]'
pytest
mypy src/danipa
ruff check
```

## Links

- Source: <https://github.com/paboagye/danipa-digital-platform/tree/main/sdks/python>
- Issues: <https://github.com/paboagye/danipa-digital-platform/issues>
- Changelog: [`CHANGELOG.md`](./CHANGELOG.md)
- Milestone: [`docs/milestones/SDK_PYTHON_PUBLISH.md`](../../docs/milestones/SDK_PYTHON_PUBLISH.md)

## License

MIT — see [`LICENSE`](./LICENSE).
