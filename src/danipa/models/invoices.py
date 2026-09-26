"""Invoice models (fintech ``CreateInvoiceRequest`` / ``InvoiceResponse``)."""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal

from pydantic import Field

from danipa.models._base import _ApiModel, _OpenEnum, _ResponseModel


class InvoiceStatus(_OpenEnum):
    DRAFT = "DRAFT"
    SENT = "SENT"
    PAID = "PAID"
    OVERDUE = "OVERDUE"
    VOIDED = "VOIDED"
    UNKNOWN = "UNKNOWN"
    """Any status this SDK version does not know yet."""


class InvoiceLineItemRequest(_ApiModel):
    description: str
    quantity: int
    unit_price: Decimal
    tax_rate_pct: Decimal | None = None
    """Per-line tax rate in percent (``5`` means 5 %). Omit to use the merchant default."""


class CreateInvoiceRequest(_ApiModel):
    """Body of ``POST /v1/merchants/me/invoices``.

    ``currency`` and ``due_date`` are optional; an omitted currency resolves to
    the merchant's billing currency server-side.
    """

    customer_name: str
    line_items: list[InvoiceLineItemRequest] = Field(min_length=1)
    customer_email: str | None = None
    customer_phone: str | None = None
    customer_id: str | None = None
    tax_amount: Decimal | None = None
    currency: str | None = None
    due_date: date | None = None
    notes: str | None = None


class InvoiceLineItem(_ApiModel):
    description: str | None = None
    quantity: int = 0
    unit_price: Decimal | None = None
    line_total: Decimal | None = None
    tax_rate_pct: Decimal | None = None


class TaxLine(_ApiModel):
    """One tax leg of a breakdown, e.g. ``GST 5%``. ``rate_pct`` is a percentage."""

    label: str | None = None
    rate_pct: Decimal | None = None
    amount: Decimal | None = None


class Invoice(_ResponseModel):
    id: str
    invoice_number: str | None = None
    customer_id: str | None = None
    customer_name: str | None = None
    customer_email: str | None = None
    customer_phone: str | None = None
    line_items: list[InvoiceLineItem] = Field(default_factory=list)
    subtotal: Decimal | None = None
    tax_amount: Decimal | None = None
    tax_breakdown: list[TaxLine] | None = None
    total: Decimal | None = None
    currency: str | None = None
    status: InvoiceStatus | None = None
    due_date: date | None = None
    paid_at: datetime | None = None
    sent_at: datetime | None = None
    voided_at: datetime | None = None
    payment_method: str | None = None
    payment_note: str | None = None
    payment_link_url: str | None = None
    notes: str | None = None
    created_at: datetime | None = None
