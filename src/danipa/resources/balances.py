"""Balances resource: ``GET /v1/merchants/me/wallet/balances``."""

from __future__ import annotations

from danipa.http import RequestOptions, _AsyncHttp, _RequestSpec, _SyncHttp
from danipa.models.balances import Balance
from danipa.resources._shared import to_model_list


def _list_spec(options: RequestOptions | None) -> _RequestSpec:
    return _RequestSpec(method="GET", path="/v1/merchants/me/wallet/balances", options=options)


class BalancesResource:
    def __init__(self, http: _SyncHttp) -> None:
        self._http = http

    def list(self, *, options: RequestOptions | None = None) -> list[Balance]:
        """The merchant's operating balances, one per currency held (``payments:read``).

        Only the key's own environment. Empty until something has settled.
        """
        body, meta = self._http.request(_list_spec(options))
        return to_model_list(Balance, body, meta)


class AsyncBalancesResource:
    def __init__(self, http: _AsyncHttp) -> None:
        self._http = http

    async def list(self, *, options: RequestOptions | None = None) -> list[Balance]:
        """The merchant's operating balances, one per currency held (``payments:read``)."""
        body, meta = await self._http.request(_list_spec(options))
        return to_model_list(Balance, body, meta)
