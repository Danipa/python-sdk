"""Merchants resource: ``GET /v1/merchants/me``."""

from __future__ import annotations

from danipa.http import RequestOptions, _AsyncHttp, _RequestSpec, _SyncHttp
from danipa.models.merchants import Merchant
from danipa.resources._shared import to_model


def _me_spec(options: RequestOptions | None) -> _RequestSpec:
    return _RequestSpec(method="GET", path="/v1/merchants/me", options=options)


class MerchantsResource:
    def __init__(self, http: _SyncHttp) -> None:
        self._http = http

    def me(self, *, options: RequestOptions | None = None) -> Merchant:
        """Return the merchant the API key belongs to (needs the ``account:read`` scope)."""
        body, meta = self._http.request(_me_spec(options))
        return to_model(Merchant, body, meta)


class AsyncMerchantsResource:
    def __init__(self, http: _AsyncHttp) -> None:
        self._http = http

    async def me(self, *, options: RequestOptions | None = None) -> Merchant:
        """Return the merchant the API key belongs to (needs the ``account:read`` scope)."""
        body, meta = await self._http.request(_me_spec(options))
        return to_model(Merchant, body, meta)
