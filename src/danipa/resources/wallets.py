"""Wallets resource — balance lookup."""

from __future__ import annotations

from danipa.http import RequestOptions, _HttpClient, _RequestSpec
from danipa.models.common import CurrencyCode
from danipa.models.wallets import WalletBalance


class WalletsResource:
    def __init__(self, http: _HttpClient) -> None:
        self._http = http

    def get_balance(
        self,
        *,
        currency: CurrencyCode | None = None,
        options: RequestOptions | None = None,
    ) -> WalletBalance:
        """Fetch the current wallet balance.

        ``currency`` is optional — when omitted the backend returns the
        merchant's default-currency wallet.
        """
        body = self._http.request(
            _RequestSpec(
                method="GET",
                path="/v1/wallets/balance",
                query={"currency": currency} if currency is not None else None,
                options=options,
            )
        )
        return WalletBalance.model_validate(body)
