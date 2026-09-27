"""Payment links resource: ``/v1/merchants/me/payment-links``.

Everything an API key can do with payment links (``payments:read`` /
``payments:write`` scopes). There is no get-one route on the API-key surface:
use :meth:`PaymentLinksResource.list`.
"""

from __future__ import annotations

import uuid
from typing import Any

from danipa.http import RequestOptions, ResponseMeta, _AsyncHttp, _RequestSpec, _SyncHttp
from danipa.models.pagination import Page
from danipa.models.payment_links import (
    CreatePaymentLinkRequest,
    DeletePaymentLinkResult,
    PaymentLink,
    UpdatePaymentLinkRequest,
)
from danipa.resources._shared import paging, path_id, to_model

_BASE = "/v1/merchants/me/payment-links"


def _create_spec(request: CreatePaymentLinkRequest, options: RequestOptions | None) -> _RequestSpec:
    return _RequestSpec(method="POST", path=_BASE, body=request._wire(), options=options)


def _list_spec(page: int | None, size: int | None, options: RequestOptions | None) -> _RequestSpec:
    return _RequestSpec(method="GET", path=_BASE, query=paging(page, size), options=options)


def _update_spec(
    link_id: str | uuid.UUID, request: UpdatePaymentLinkRequest, options: RequestOptions | None
) -> _RequestSpec:
    return _RequestSpec(
        method="PUT", path=f"{_BASE}/{path_id(link_id)}", body=request._wire(), options=options
    )


def _delete_spec(link_id: str | uuid.UUID, options: RequestOptions | None) -> _RequestSpec:
    return _RequestSpec(method="DELETE", path=f"{_BASE}/{path_id(link_id)}", options=options)


def _delete_result(body: Any, meta: ResponseMeta) -> DeletePaymentLinkResult:
    if body is None:  # 204: deleted outright
        result = DeletePaymentLinkResult(deleted=True, action="deleted")
        result._response_meta = meta
        return result
    return to_model(DeletePaymentLinkResult, body, meta)


class PaymentLinksResource:
    def __init__(self, http: _SyncHttp) -> None:
        self._http = http

    def create(
        self,
        request: CreatePaymentLinkRequest,
        *,
        options: RequestOptions | None = None,
    ) -> PaymentLink:
        """Create a hosted payment link (``payments:write``), in the key's environment."""
        body, meta = self._http.request(_create_spec(request, options))
        return to_model(PaymentLink, body, meta)

    def list(
        self,
        *,
        page: int | None = None,
        size: int | None = None,
        options: RequestOptions | None = None,
    ) -> Page[PaymentLink]:
        """One page of the key environment's links (``payments:read``).

        ``page`` is zero-based (server default 0); ``size`` is 1 to 200 (default 20).
        """
        body, meta = self._http.request(_list_spec(page, size, options))
        return to_model(Page[PaymentLink], body, meta)

    def update(
        self,
        link_id: str | uuid.UUID,
        request: UpdatePaymentLinkRequest,
        *,
        options: RequestOptions | None = None,
    ) -> PaymentLink:
        """Change a link of the key's environment (``payments:write``)."""
        body, meta = self._http.request(_update_spec(link_id, request, options))
        return to_model(PaymentLink, body, meta)

    def delete(
        self,
        link_id: str | uuid.UUID,
        *,
        options: RequestOptions | None = None,
    ) -> DeletePaymentLinkResult:
        """Delete a link, or deactivate it if it has transactions (``payments:write``)."""
        body, meta = self._http.request(_delete_spec(link_id, options))
        return _delete_result(body, meta)


class AsyncPaymentLinksResource:
    def __init__(self, http: _AsyncHttp) -> None:
        self._http = http

    async def create(
        self,
        request: CreatePaymentLinkRequest,
        *,
        options: RequestOptions | None = None,
    ) -> PaymentLink:
        """Create a hosted payment link (``payments:write``), in the key's environment."""
        body, meta = await self._http.request(_create_spec(request, options))
        return to_model(PaymentLink, body, meta)

    async def list(
        self,
        *,
        page: int | None = None,
        size: int | None = None,
        options: RequestOptions | None = None,
    ) -> Page[PaymentLink]:
        """One page of the key environment's links (``payments:read``)."""
        body, meta = await self._http.request(_list_spec(page, size, options))
        return to_model(Page[PaymentLink], body, meta)

    async def update(
        self,
        link_id: str | uuid.UUID,
        request: UpdatePaymentLinkRequest,
        *,
        options: RequestOptions | None = None,
    ) -> PaymentLink:
        """Change a link of the key's environment (``payments:write``)."""
        body, meta = await self._http.request(_update_spec(link_id, request, options))
        return to_model(PaymentLink, body, meta)

    async def delete(
        self,
        link_id: str | uuid.UUID,
        *,
        options: RequestOptions | None = None,
    ) -> DeletePaymentLinkResult:
        """Delete a link, or deactivate it if it has transactions (``payments:write``)."""
        body, meta = await self._http.request(_delete_spec(link_id, options))
        return _delete_result(body, meta)
