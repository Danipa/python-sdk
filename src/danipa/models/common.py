"""Shared request/response primitives — currencies, parties, money."""

from __future__ import annotations

from danipa.models._base import _ApiModel

CurrencyCode = str
"""ISO-4217 currency code. Loose-typed so new corridors don't require an SDK release."""


class Money(_ApiModel):
    amount: str
    """Decimal amount as a string. Strings preserve precision across JSON parsers."""

    currency: CurrencyCode


class Payer(_ApiModel):
    phone: str | None = None
    email: str | None = None
    name: str | None = None


class Recipient(_ApiModel):
    phone: str | None = None
    account_number: str | None = None
    bank_code: str | None = None
    name: str | None = None
