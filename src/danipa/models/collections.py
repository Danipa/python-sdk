"""Collection (pull-from-payer) request/response models."""

from __future__ import annotations

from typing import Literal

from danipa.models._base import _ApiModel
from danipa.models.common import CurrencyCode, Payer

CollectionStatus = Literal["PENDING", "COMPLETED", "FAILED"]


class CreateCollectionRequest(_ApiModel):
    amount: str
    currency: CurrencyCode
    payer: Payer
    description: str | None = None
    reference: str | None = None
    payment_link_id: str | None = None


class Collection(_ApiModel):
    id: str
    merchant_id: str
    amount: str
    currency: CurrencyCode
    status: CollectionStatus
    payer: Payer
    payment_link_id: str | None = None
    created_at: str
    completed_at: str | None = None
