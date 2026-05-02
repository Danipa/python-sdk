"""Disbursement (push-to-payee) request/response models."""

from __future__ import annotations

from typing import Literal

from danipa.models._base import _ApiModel
from danipa.models.common import CurrencyCode, Recipient

DisbursementStatus = Literal["PENDING", "COMPLETED", "FAILED"]


class CreateDisbursementRequest(_ApiModel):
    amount: str
    currency: CurrencyCode
    recipient: Recipient
    description: str | None = None
    reference: str | None = None


class Disbursement(_ApiModel):
    id: str
    merchant_id: str
    amount: str
    currency: CurrencyCode
    status: DisbursementStatus
    recipient: Recipient
    created_at: str
    completed_at: str | None = None
