"""Invoices resource: ``/v1/merchants/me/invoices``.

Everything an API key can do with invoices (``payments:read`` /
``payments:write`` scopes): create, list, get, send, void. Editing a draft,
the PDF, stats, recording an offline payment and bulk import are dashboard-only
and not on the API-key surface.
"""

from __future__ import annotations

import uuid

from danipa.http import RequestOptions, _AsyncHttp, _RequestSpec, _SyncHttp
from danipa.models.invoices import CreateInvoiceRequest, Invoice, InvoiceStatus
from danipa.models.pagination import Page
from danipa.resources._shared import paging, path_id, to_model

_BASE = "/v1/merchants/me/invoices"


def _create_spec(request: CreateInvoiceRequest, options: RequestOptions | None) -> _RequestSpec:
    return _RequestSpec(method="POST", path=_BASE, body=request._wire(), options=options)


_FILTERABLE_STATUSES = frozenset(m.value for m in InvoiceStatus if m is not InvoiceStatus.UNKNOWN)


def _status_filter(status: InvoiceStatus | str | None) -> str | None:
    """Validate the ``status`` filter against the server's ``InvoiceStatus`` enum.

    The server parses it with ``InvoiceStatus.valueOf(status.toUpperCase())``, so an
    unknown value would come back as a 500; reject it here before sending.
    """
    if status is None:
        return None
    value = (status.value if isinstance(status, InvoiceStatus) else str(status)).upper()
    if value not in _FILTERABLE_STATUSES:
        raise ValueError(
            f"Danipa SDK: invoice status filter must be one of "
            f"{', '.join(sorted(_FILTERABLE_STATUSES))}; got {status!r}"
        )
    return value


def _list_spec(
    status: InvoiceStatus | str | None,
    q: str | None,
    page: int | None,
    size: int | None,
    options: RequestOptions | None,
) -> _RequestSpec:
    status_value = _status_filter(status)
    return _RequestSpec(
        method="GET",
        path=_BASE,
        query={"status": status_value, "q": q, **paging(page, size)},
        options=options,
    )


def _get_spec(invoice_id: str | uuid.UUID, options: RequestOptions | None) -> _RequestSpec:
    return _RequestSpec(method="GET", path=f"{_BASE}/{path_id(invoice_id)}", options=options)


def _action_spec(
    invoice_id: str | uuid.UUID, action: str, options: RequestOptions | None
) -> _RequestSpec:
    return _RequestSpec(
        method="POST", path=f"{_BASE}/{path_id(invoice_id)}/{action}", options=options
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
        """Create a DRAFT invoice in the key's environment (``payments:write``)."""
        body, meta = self._http.request(_create_spec(request, options))
        return to_model(Invoice, body, meta)

    def list(
        self,
        *,
        status: InvoiceStatus | str | None = None,
        q: str | None = None,
        page: int | None = None,
        size: int | None = None,
        options: RequestOptions | None = None,
    ) -> Page[Invoice]:
        """One page of the key environment's invoices (``payments:read``).

        ``status`` filters by status; ``q`` matches an invoice-number prefix or a
        customer-name substring (case-insensitive). ``page`` is zero-based;
        ``size`` is 1 to 200 (default 20).
        """
        body, meta = self._http.request(_list_spec(status, q, page, size, options))
        return to_model(Page[Invoice], body, meta)

    def get(self, invoice_id: str | uuid.UUID, *, options: RequestOptions | None = None) -> Invoice:
        """One invoice (``payments:read``). An invoice of the other environment is a 404."""
        body, meta = self._http.request(_get_spec(invoice_id, options))
        return to_model(Invoice, body, meta)

    def send(
        self, invoice_id: str | uuid.UUID, *, options: RequestOptions | None = None
    ) -> Invoice:
        """DRAFT → SENT; creates the invoice's payment link (``payments:write``)."""
        body, meta = self._http.request(_action_spec(invoice_id, "send", options))
        return to_model(Invoice, body, meta)

    def void(
        self, invoice_id: str | uuid.UUID, *, options: RequestOptions | None = None
    ) -> Invoice:
        """Void an unpaid invoice and deactivate its payment link (``payments:write``)."""
        body, meta = self._http.request(_action_spec(invoice_id, "void", options))
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
        """Create a DRAFT invoice in the key's environment (``payments:write``)."""
        body, meta = await self._http.request(_create_spec(request, options))
        return to_model(Invoice, body, meta)

    async def list(
        self,
        *,
        status: InvoiceStatus | str | None = None,
        q: str | None = None,
        page: int | None = None,
        size: int | None = None,
        options: RequestOptions | None = None,
    ) -> Page[Invoice]:
        """One page of the key environment's invoices (``payments:read``)."""
        body, meta = await self._http.request(_list_spec(status, q, page, size, options))
        return to_model(Page[Invoice], body, meta)

    async def get(
        self, invoice_id: str | uuid.UUID, *, options: RequestOptions | None = None
    ) -> Invoice:
        """One invoice (``payments:read``). An invoice of the other environment is a 404."""
        body, meta = await self._http.request(_get_spec(invoice_id, options))
        return to_model(Invoice, body, meta)

    async def send(
        self, invoice_id: str | uuid.UUID, *, options: RequestOptions | None = None
    ) -> Invoice:
        """DRAFT → SENT; creates the invoice's payment link (``payments:write``)."""
        body, meta = await self._http.request(_action_spec(invoice_id, "send", options))
        return to_model(Invoice, body, meta)

    async def void(
        self, invoice_id: str | uuid.UUID, *, options: RequestOptions | None = None
    ) -> Invoice:
        """Void an unpaid invoice and deactivate its payment link (``payments:write``)."""
        body, meta = await self._http.request(_action_spec(invoice_id, "void", options))
        return to_model(Invoice, body, meta)
