"""Hosted payment links resource."""

from __future__ import annotations

from danipa.http import RequestOptions, _HttpClient, _RequestSpec
from danipa.models.payment_links import CreatePaymentLinkRequest, PaymentLink


class PaymentLinksResource:
    def __init__(self, http: _HttpClient) -> None:
        self._http = http

    def create(
        self,
        request: CreatePaymentLinkRequest,
        *,
        options: RequestOptions | None = None,
    ) -> PaymentLink:
        """Create a hosted payment link the merchant can share by URL."""
        body = self._http.request(
            _RequestSpec(
                method="POST",
                path="/v1/merchants/me/payment-links",
                body=request.model_dump(by_alias=True, exclude_none=True),
                options=options,
            )
        )
        return PaymentLink.model_validate(body)
