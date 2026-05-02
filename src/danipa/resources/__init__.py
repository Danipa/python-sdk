"""Resource facades exposed by :class:`danipa.Danipa`."""

from __future__ import annotations

from danipa.resources.collections import CollectionsResource
from danipa.resources.disbursements import DisbursementsResource
from danipa.resources.invoices import InvoicesResource
from danipa.resources.payment_links import PaymentLinksResource
from danipa.resources.wallets import WalletsResource

__all__ = [
    "CollectionsResource",
    "DisbursementsResource",
    "InvoicesResource",
    "PaymentLinksResource",
    "WalletsResource",
]
