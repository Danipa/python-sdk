"""Invoice request/response models."""

from __future__ import annotations

from typing import Literal

from danipa.models._base import _ApiModel
from danipa.models.common import CurrencyCode

InvoiceStatus = Literal["DRAFT", "SENT", "PAID", "OVERDUE", "CANCELLED"]


class InvoiceLineItem(_ApiModel):
    description: str
    quantity: int
    unit_price: str


class CreateInvoiceRequest(_ApiModel):
    customer_email: str
    currency: CurrencyCode
    due_date: str
    line_items: list[InvoiceLineItem]
    notes: str | None = None


class Invoice(_ApiModel):
    id: str
    merchant_id: str
    amount: str
    currency: CurrencyCode
    due_date: str
    status: InvoiceStatus
    customer_email: str
    line_items: list[InvoiceLineItem]
    created_at: str
