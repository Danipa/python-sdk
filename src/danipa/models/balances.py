"""``GET /v1/merchants/me/wallet/balances`` item (fintech ``WalletAccountResponse``)."""

from __future__ import annotations

from decimal import Decimal

from danipa.models._base import _ResponseModel


class Balance(_ResponseModel):
    """The merchant's operating balance in one currency.

    Business money only (keyed on the merchant, never the owner's personal
    wallet), in the API key's own environment. ``status`` is an open string.
    """

    id: str
    currency: str | None = None
    available_balance: Decimal | None = None
    pending_balance: Decimal | None = None
    status: str | None = None
