"""Payment link models (fintech ``CreatePaymentLinkRequest`` / ``PaymentLinkResponse``)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from danipa.models._base import _ApiModel, _OpenEnum, _ResponseModel


class PaymentLinkStatus(_OpenEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    EXPIRED = "EXPIRED"
    UNKNOWN = "UNKNOWN"
    """Any status this SDK version does not know yet."""


class CreatePaymentLinkRequest(_ApiModel):
    """Body of ``POST /v1/merchants/me/payment-links``.

    ``currency`` is optional: when omitted the server uses the merchant's
    billing currency. ``is_amount_fixed`` defaults to ``True`` server-side; set
    it to ``False`` with ``min_amount``/``max_amount`` for pay-what-you-want.
    """

    title: str
    description: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    is_amount_fixed: bool | None = None
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    redirect_url: str | None = None
    expires_at: datetime | None = None
    customer_id: str | None = None


class PaymentLink(_ResponseModel):
    id: str
    customer_id: str | None = None
    short_code: str | None = None
    url: str | None = None
    title: str | None = None
    description: str | None = None
    amount: Decimal | None = None
    currency: str | None = None
    is_amount_fixed: bool = True
    min_amount: Decimal | None = None
    max_amount: Decimal | None = None
    status: PaymentLinkStatus | None = None
    redirect_url: str | None = None
    expires_at: datetime | None = None
    total_collected: Decimal | None = None
    payment_count: int = 0
    created_at: datetime | None = None
    merchant_name: str | None = None
    merchant_logo_url: str | None = None
    merchant_brand_color: str | None = None
    merchant_storefront_url: str | None = None
