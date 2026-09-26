"""Payment links resource: ``POST /v1/merchants/me/payment-links``.

.. note::
   API keys cannot reach this route yet: today it answers
   ``403 API_KEY_SCOPE_DENIED`` (raised as :class:`danipa.PermissionDeniedError`).
   It opens to API keys with the API-key surface tracked in #5573.
"""

from __future__ import annotations

from danipa.http import RequestOptions, _AsyncHttp, _RequestSpec, _SyncHttp
from danipa.models.payment_links import CreatePaymentLinkRequest, PaymentLink
from danipa.resources._shared import to_model


def _create_spec(request: CreatePaymentLinkRequest, options: RequestOptions | None) -> _RequestSpec:
    return _RequestSpec(
        method="POST",
        path="/v1/merchants/me/payment-links",
        body=request._wire(),
        options=options,
    )


class PaymentLinksResource:
    def __init__(self, http: _SyncHttp) -> None:
        self._http = http

    def create(
        self,
        request: CreatePaymentLinkRequest,
        *,
        options: RequestOptions | None = None,
    ) -> PaymentLink:
        """Create a hosted payment link. Needs the API-key surface from #5573."""
        body, meta = self._http.request(_create_spec(request, options))
        return to_model(PaymentLink, body, meta)


class AsyncPaymentLinksResource:
    def __init__(self, http: _AsyncHttp) -> None:
        self._http = http

    async def create(
        self,
        request: CreatePaymentLinkRequest,
        *,
        options: RequestOptions | None = None,
    ) -> PaymentLink:
        """Create a hosted payment link. Needs the API-key surface from #5573."""
        body, meta = await self._http.request(_create_spec(request, options))
        return to_model(PaymentLink, body, meta)
