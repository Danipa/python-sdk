"""Invoices resource: ``POST /v1/merchants/me/invoices``.

.. note::
   API keys cannot reach this route yet: today it answers
   ``403 API_KEY_SCOPE_DENIED`` (raised as :class:`danipa.PermissionDeniedError`).
   It opens to API keys with the API-key surface tracked in #5573.
"""

from __future__ import annotations

from danipa.http import RequestOptions, _AsyncHttp, _RequestSpec, _SyncHttp
from danipa.models.invoices import CreateInvoiceRequest, Invoice
from danipa.resources._shared import to_model


def _create_spec(request: CreateInvoiceRequest, options: RequestOptions | None) -> _RequestSpec:
    return _RequestSpec(
        method="POST",
        path="/v1/merchants/me/invoices",
        body=request._wire(),
        options=options,
    )


class InvoicesResource:
    def __init__(self, http: _SyncHttp) -> None:
        self._http = http

    def create(
        self,
        request: CreateInvoiceRequest,
        *,
        options: RequestOptions | None = None,
    ) -> Invoice:
        """Issue an invoice. Needs the API-key surface from #5573."""
        body, meta = self._http.request(_create_spec(request, options))
        return to_model(Invoice, body, meta)


class AsyncInvoicesResource:
    def __init__(self, http: _AsyncHttp) -> None:
        self._http = http

    async def create(
        self,
        request: CreateInvoiceRequest,
        *,
        options: RequestOptions | None = None,
    ) -> Invoice:
        """Issue an invoice. Needs the API-key surface from #5573."""
        body, meta = await self._http.request(_create_spec(request, options))
        return to_model(Invoice, body, meta)
