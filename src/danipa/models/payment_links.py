"""Hosted payment link request/response models."""

from __future__ import annotations

from danipa.models._base import _ApiModel
from danipa.models.common import CurrencyCode


class CreatePaymentLinkRequest(_ApiModel):
    amount: str
    currency: CurrencyCode
    description: str | None = None
    expires_at: str | None = None


class PaymentLink(_ApiModel):
    id: str
    url: str
    amount: str
    currency: CurrencyCode
    description: str | None = None
    expires_at: str | None = None
    created_at: str
