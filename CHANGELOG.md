# Changelog

All notable changes to the Danipa Python SDK are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- **Stage 1 scaffolding** — `pyproject.toml` (hatchling, Python 3.10+, httpx + Pydantic v2), package skeleton, `_version.py` pinned at 0.1.0, conftest loader for the cross-SDK HMAC fixture, README + CHANGELOG.

### Pending (Stages 2–6)

- `Danipa` client + builder, base-URL inference from `dk_live_*` / `dk_test_*` prefix
- `_HttpClient` with bearer auth, idempotency-key forwarding, 200 ms × 2^n retry on 5xx (cap 2 s, +0–50 ms jitter)
- 5 resource facades (`collections`, `disbursements`, `wallets`, `payment_links`, `invoices`)
- Pydantic v2 DTOs with snake_case ↔ camelCase mapping
- `DanipaError`, `DanipaApiError`, `DanipaNetworkError`
- `verify_webhook(...)` agreeing bit-for-bit with Node + Java on `sdks/fixtures/webhook-hmac.json`
- ≥ 80 % coverage gate, `mypy --strict` and `ruff` clean
- Tag-driven publish to PyPI via Trusted Publishing (OIDC)

[Unreleased]: https://github.com/paboagye/danipa-digital-platform/compare/sdk-python-v0.1.0...HEAD
