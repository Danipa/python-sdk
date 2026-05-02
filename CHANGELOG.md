# Changelog

All notable changes to the Danipa Python SDK are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
