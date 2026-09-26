"""``GET /v1/merchants/me`` response model (fintech ``MerchantResponse``)."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from danipa.models._base import _ResponseModel


class Merchant(_ResponseModel):
    """The merchant the API key belongs to.

    ``status``, ``kyb_status`` and ``tier`` are open strings: the server may add
    values without an SDK release. The server omits null keys, so every
    optional field defaults to ``None``.
    """

    id: str
    business_name: str | None = None
    business_type: str | None = None
    registration_number: str | None = None
    country: str | None = None
    status: str | None = None
    kyb_status: str | None = None
    tier: str | None = None
    tos_accepted_at: datetime | None = None
    tos_version: str | None = None
    current_tos_version: str | None = None
    created_at: datetime | None = None
    address_line1: str | None = None
    address_line2: str | None = None
    city: str | None = None
    region: str | None = None
    postal_code: str | None = None
    contact_email: str | None = None
    contact_phone: str | None = None
    website: str | None = None
    whatsapp: str | None = None
    slug: str | None = None
    public_catalog_enabled: bool = False
    tax_id: str | None = None
    tax_id_type: str | None = None
    default_tax_rate_pct: Decimal | None = None
    effective_default_tax_rate_pct: Decimal | None = None
    billing_currency: str | None = None
    """The one currency this merchant transacts in (GH→GHS, US→USD, CA→CAD)."""
    storefront_theme: str | None = None
    storefront_template: str | None = None
    checkout_mode: str | None = None
    external_checkout_url: str | None = None
