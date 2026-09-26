"""Resource facades exposed by :class:`danipa.Danipa` and :class:`danipa.AsyncDanipa`."""

from __future__ import annotations

from danipa.resources.invoices import AsyncInvoicesResource, InvoicesResource
from danipa.resources.merchants import AsyncMerchantsResource, MerchantsResource
from danipa.resources.payment_links import AsyncPaymentLinksResource, PaymentLinksResource

__all__ = [
    "AsyncInvoicesResource",
    "AsyncMerchantsResource",
    "AsyncPaymentLinksResource",
    "InvoicesResource",
    "MerchantsResource",
    "PaymentLinksResource",
]
