# Changelog

All notable changes to the Danipa Python SDK are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.3.0] — 2026-10-25

### Upgrade notes (read first)

- **Authentication now works. Upgrade from every earlier release.** The previous published build (PyPI `danipa` 0.1.0) sent the API key as `Authorization: Bearer …`, which the API has never accepted, so every call failed with 401. 0.3.0 sends the key as `X-API-Key` only and never sends an `Authorization` header (sending both is rejected). Verified against sandbox on 2026-10-25 (Part of #7463).
- **Production is not live yet.** A `dk_live_…` key, or an explicit live environment, with no explicit `base_url` now makes `Danipa(...)` / `AsyncDanipa(...)` throw `DanipaConfigurationError` ("production is not live yet — use a dk_test_ key against sandbox"). This replaces a DNS error on the first call, and nothing is sent. `dk_test_…` keys still go to `https://api.sandbox.danipa.com/ms`. The live default stays `https://api.danipa.com/ms`, and a later 0.x release removes this guard when production launches. An explicit `base_url` is never blocked.
- Routes the earlier build called that never existed on the server are gone; see **Removed** below.

The version jumps from 0.1.0 to 0.3.0 so all four Danipa SDKs share one version line.

### 0.3.0 readiness: the full API-key surface (Part of #5573)

The SDK now covers every route an API key can call (the fintech `ApiKeyAuthenticationFilter` route table) and nothing else, and a `dk_test_` key works against sandbox straight after `pip install`.

#### Added

- `payment_links.list(page=, size=)` → `Page[PaymentLink]`, `payment_links.update(id, UpdatePaymentLinkRequest)` → `PaymentLink`, `payment_links.delete(id)` → `DeletePaymentLinkResult` (`deleted=True` on 204; `deleted=False, action="deactivated"` when the link has payments).
- `invoices.list(status=, q=, page=, size=)` → `Page[Invoice]`, `invoices.get(id)`, `invoices.send(id)`, `invoices.void(id)` → `Invoice`.
- `balances.list()` → `list[Balance]` (`GET /v1/merchants/me/wallet/balances`; `Balance`: `id`, `currency`, `available_balance`, `pending_balance`, `status`).
- `Page[T]` (`content`, `total_elements`, `total_pages`, `number` (zero-based), `size`, `has_next`); parses both the flat Spring `Page` JSON the server writes today and the nested `page` shape.
- `Merchant.gst_hst_number` and `Merchant.qst_number` (Canadian GST/HST and QST registration numbers, nullable; #5608).
- `invoices.list(status=)` is validated against the server's `InvoiceStatus` (`DRAFT, SENT, PAID, OVERDUE, VOIDED`, case-insensitive, sent upper-case); anything else raises `ValueError` before sending, since the server answers an unknown value with a 500. Unknown statuses in responses still parse as `InvoiceStatus.UNKNOWN`.
- `environment="sandbox" | "live"` option on `Danipa` / `AsyncDanipa`.
- `DanipaConfigurationError` (a `DanipaError` and a `ValueError`).
- Same methods on `AsyncDanipa`. Ids accept `str` or `uuid.UUID`; a value that is not a UUID raises `ValueError` before sending (the server would otherwise answer a misleading `403 API_KEY_SCOPE_DENIED`). `page` must be >= 0 and `size` 1 to 200, checked client-side the same way.
- `tests/test_route_contract.py`: the SDK's route set must equal the server's API-key route table (and, in the monorepo, the table parsed from the fintech source), so drift fails CI.
- `examples/smoke_sandbox.py`: live sandbox walk of every method (not run in CI).

#### Changed

- **Environment from the key prefix is now strict (breaking).** `dk_test_…` → `https://api.sandbox.danipa.com/ms`, `dk_live_…` → `https://api.danipa.com/ms`, as before. A key with any other prefix used to fall back silently to sandbox; it now raises `DanipaConfigurationError` at construction unless you pass `base_url` or `environment`. An explicit `base_url` still always wins (then `environment`, then the prefix).
- `payment_links.create` and `invoices.create` are now reachable with an API key (`payments:write`); the "403 until #5573" caveat is gone.

#### Removed

- Nothing callable: the SDK already had no method on a non-key route. The lenient "anything else → sandbox" host fallback is removed (see Changed).

### SDK phase 1

SDK phase 1 (Part of #5573): the SDK now speaks the wire contract the fintech API actually enforces. Still 0.x: the breaking changes below ship without a major bump. Not released yet.

### Removed (breaking)

- `danipa.collections`, `danipa.disbursements` and `danipa.wallets`, with their models (`CreateCollectionRequest`, `Collection`, `CollectionStatus`, `CreateDisbursementRequest`, `Disbursement`, `DisbursementStatus`, `WalletBalance`, `Money`, `Payer`, `Recipient`). They called `/v1/collections`, `/v1/disbursements` and `/v1/wallets/balance`, which never existed on the server, so every call failed. They come back when real API-key routes exist (#5573).

### Changed (breaking)

- Auth: the API key is sent as `X-API-Key`, not `Authorization: Bearer`. `Authorization` is never sent (the server answers `403 AMBIGUOUS_CREDENTIALS` when both are present), even if an injected `httpx` client carries one.
- Idempotency: the header is `Idempotency-Key` (was `X-Idempotency-Key`). Every POST/PUT/PATCH/DELETE now carries one: a UUIDv4 is generated when you pass none, and the same key is reused on every retry of that call. Keys over 255 characters raise `ValueError` before anything is sent.
- Retries: `max_retries` now counts RETRIES, not attempts (default 2, so 3 attempts as before; `0` disables and is now allowed). Retried on connect/read errors and 408, 429, 502, 503, 504 only; 500, 501 and other 4xx are no longer retried. `Retry-After` (seconds) is honoured up to 60 s; otherwise exponential backoff with full jitter (base 0.5 s, cap 8 s).
- `payment_links.create` and `invoices.create` models rebuilt from the server DTOs. `CreatePaymentLinkRequest` requires `title` and takes optional `amount`, `currency`, `is_amount_fixed`, `min_amount`, `max_amount`, `redirect_url`, `expires_at`, `customer_id`. `CreateInvoiceRequest` requires `customer_name` and `line_items` (`InvoiceLineItemRequest`: `description`, `quantity`, `unit_price`, optional `tax_rate_pct`) and takes optional `customer_email`, `customer_phone`, `customer_id`, `tax_amount`, `currency`, `due_date`, `notes`. Responses are the full `PaymentLinkResponse` / `InvoiceResponse`. These routes answer `403 API_KEY_SCOPE_DENIED` to API keys until the API-key surface in #5573 lands.
- Money fields are `decimal.Decimal` (parsed from JSON numbers without a float round-trip, sent as strings), dates are `date` / `datetime`.
- `InvoiceStatus` is an enum `DRAFT, SENT, PAID, OVERDUE, VOIDED` plus `UNKNOWN` for any value this version does not know (was a closed `Literal` with a non-existent `CANCELLED`). `PaymentLinkStatus` works the same way (`ACTIVE, INACTIVE, EXPIRED, UNKNOWN`).
- Errors: `DanipaApiError` is now subclassed by status (`ValidationError` 400/422, `AuthenticationError` 401, `PermissionDeniedError` 403, `NotFoundError` 404, `ConflictError` / `IdempotencyError` 409, `RateLimitError` 429, `ServerError` 5xx), parses both the `ApiStatus` envelope and the flat `{code, description}` filter body, and carries `request_id`, `field_errors`, `retry_after`, `retryable`, `trace_id`, `message_key`, `idempotency_key` and `idempotent_replay`. Its constructor is keyword-only. `str(err)` includes the status and code. Network failures are `DanipaConnectionError` / `DanipaTimeoutError` (both still `DanipaNetworkError`).
- A 2xx response whose body cannot be parsed raises `ResponseParseError`, not a network error: the call may have succeeded.
- User-Agent is `danipa-python/<installed package version> python/<runtime version>` (was `danipa-python-sdk/<version>`).
- `webhook.verify` accepts an empty payload (the cross-SDK fixture has one).

### Added

- `danipa.merchants.me()`: `GET /v1/merchants/me`, returning `Merchant` (the fintech `MerchantResponse`). Today this is the only route an API key can reach (needs the `account:read` scope).
- `AsyncDanipa` on `httpx.AsyncClient`, with the same request building and retry policy as `Danipa` (`async with`, `await client.aclose()`).
- `timeout` accepts an `httpx.Timeout`; `http_client=` takes your own `httpx.Client` / `httpx.AsyncClient` (not closed by the SDK). `RequestOptions` gains per-call `max_retries`.
- `model.response_meta` on every returned model: status, headers, `request_id`, the `idempotency_key` sent, and `idempotent_replay` (`X-Idempotent-Replay: true`).
- Webhooks: `verify` and `compute_signature` accept raw `bytes` as well as `str` and sign the raw bytes; `tolerance=` (default 300 s); a list of secrets for rotation; `construct_event(payload, headers, secrets)` verifies and returns a `WebhookEvent` (`type` from `X-Danipa-Event`, `delivery_id` from `X-Danipa-Delivery`, `timestamp`, parsed `data`, `raw`), raising `WebhookVerificationError` on failure.
- The cross-SDK webhook fixture is vendored at `tests/fixtures/webhook-hmac.json` so the public mirror runs it; CI fails if it drifts from `sdks/fixtures/`.
- Python 3.14 classifier and CI matrix entry.

### Packaging

- Release pipeline: PyPI / TestPyPI uploads now run from the public `Danipa/python-sdk` mirror (`.github/workflows/publish.yml`), so PyPI's Trusted Publishing names a public, verifiable source. No change to the package itself. (#5572)
- `hatchling>=1.27`; removed the deprecated `License ::` classifier (the SPDX `license = "MIT"` expression covers it).

## [0.1.0] — 2026-05-02 — first PyPI release

First public release of the Danipa Python SDK. Surface matches the Node + Java SDKs 1:1.

### Added

- `Danipa` client with builder-style `Danipa(api_key, *, base_url=None, timeout=30.0, max_retries=3, transport=None)`. Context-manager close.
- Base URL inference from API key prefix: `dk_live_*` → `https://api.danipa.com/ms`; anything else → `https://api.sandbox.danipa.com/ms`. Lenient default matches Node.
- 5 resource facades — `collections`, `disbursements`, `wallets`, `payment_links`, `invoices`. Method surface matches the Node SDK 1:1.
- `_HttpClient` over `httpx.Client`: bearer auth, `X-Idempotency-Key` on POST when supplied, retry on 5xx + transport errors with `200 ms × 2^(attempt - 1)` backoff capped at 2 s + 0–50 ms jitter; 4xx never retries.
- Pydantic v2 DTOs (`Money`, `Payer`, `Recipient`, plus per-resource models) — snake_case Python attrs ↔ camelCase JSON wire via `to_camel` alias generator.
- Exception hierarchy: `DanipaError` base, `DanipaApiError(status, code, message, correlation_id, raw)`, `DanipaNetworkError(message, cause)`. Two classes only, matching Node.
- `verify_webhook(payload, signature, timestamp, secret) -> bool` — agrees bit-for-bit with Node + Java + PHP on every vector in `sdks/fixtures/webhook-hmac.json`. 300 s replay window, `hmac.compare_digest` constant-time check.
- 34 pytest tests, 98 % coverage, `mypy --strict` and `ruff` clean.
- Tag-driven release pipeline: subtree-split push to `Danipa/python-sdk` (public mirror), then PyPI / TestPyPI publish via OIDC Trusted Publishing.

## [0.1.0rc0] — 2026-05-02 — TestPyPI dry run

Release-candidate build. Verified the publish pipeline end-to-end on TestPyPI: tag → subtree-split mirror push to `Danipa/python-sdk@v0.1.0rc0` → OIDC publish → `pip install danipa==0.1.0rc0` round-trip OK.

[Unreleased]: https://github.com/Danipa/python-sdk/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Danipa/python-sdk/releases/tag/v0.1.0
[0.1.0rc0]: https://github.com/Danipa/python-sdk/releases/tag/v0.1.0rc0
