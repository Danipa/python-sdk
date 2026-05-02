"""Wallet balance response model."""

from __future__ import annotations

from danipa.models._base import _ApiModel
from danipa.models.common import CurrencyCode


class WalletBalance(_ApiModel):
    merchant_id: str
    currency: CurrencyCode
    available: str
    pending: str
    as_of: str
