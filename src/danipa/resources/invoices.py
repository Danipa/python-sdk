"""Invoices resource."""

from __future__ import annotations

from danipa.http import RequestOptions, _HttpClient, _RequestSpec
from danipa.models.invoices import CreateInvoiceRequest, Invoice


class InvoicesResource:
    def __init__(self, http: _HttpClient) -> None:
        self._http = http

    def create(
        self,
        request: CreateInvoiceRequest,
        *,
        options: RequestOptions | None = None,
    ) -> Invoice:
        """Issue an invoice. Returns the created :class:`Invoice` in ``SENT`` status."""
        body = self._http.request(
            _RequestSpec(
                method="POST",
                path="/v1/merchants/me/invoices",
                body=request.model_dump(by_alias=True, exclude_none=True),
                options=options,
            )
        )
        return Invoice.model_validate(body)
