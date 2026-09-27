"""``Danipa`` and ``AsyncDanipa``: the SDK entry points.

Construct once with your API key and reuse the instance; every resource shares
one HTTP client (auth, retries, timeouts).

The host is inferred from the key prefix: ``dk_test_…`` → sandbox
(``https://api.sandbox.danipa.com/ms``), ``dk_live_…`` → production
(``https://api.danipa.com/ms``, not live yet). Any other prefix raises
:class:`danipa.DanipaConfigurationError` at construction. ``base_url`` (or
``environment="sandbox"|"live"``) always overrides the inference.

Example
-------
.. code-block:: python

    import os
    from danipa import Danipa

    with Danipa(api_key=os.environ["DANIPA_API_KEY"]) as danipa:
        merchant = danipa.merchants.me()
        print(merchant.business_name, merchant.billing_currency)
"""

from __future__ import annotations

import httpx

from danipa.http import (
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEOUT,
    Environment,
    TimeoutTypes,
    _AsyncHttp,
    _SyncHttp,
)
from danipa.resources import (
    AsyncBalancesResource,
    AsyncInvoicesResource,
    AsyncMerchantsResource,
    AsyncPaymentLinksResource,
    BalancesResource,
    InvoicesResource,
    MerchantsResource,
    PaymentLinksResource,
)


class Danipa:
    """Blocking client.

    Parameters
    ----------
    api_key:
        A ``dk_test_…`` or ``dk_live_…`` key, sent as ``X-API-Key``.
    base_url:
        Override the host inferred from the key prefix. Wins over ``environment``.
    environment:
        ``"sandbox"`` or ``"live"``: choose the host explicitly instead of from
        the key prefix. Needed only for a key without a ``dk_test_`` /
        ``dk_live_`` prefix.
    timeout:
        Seconds, or an :class:`httpx.Timeout`. Default 30 s.
    max_retries:
        Number of RETRIES after the first attempt (0 disables). Default 2.
    http_client:
        Bring your own :class:`httpx.Client` (proxies, mTLS, event hooks). The SDK
        does not close a client it did not create. Any ``Authorization`` header or
        ``auth`` on it is ignored.
    transport:
        An :class:`httpx.BaseTransport` for the client the SDK creates (tests).
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        environment: Environment | None = None,
        timeout: TimeoutTypes = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._http = _SyncHttp(
            api_key,
            base_url=base_url,
            environment=environment,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
            transport=transport,
        )
        self.merchants = MerchantsResource(self._http)
        self.payment_links = PaymentLinksResource(self._http)
        self.invoices = InvoicesResource(self._http)
        self.balances = BalancesResource(self._http)

    @property
    def base_url(self) -> str:
        return self._http.base_url

    def close(self) -> None:
        """Close the HTTP client if the SDK created it. Safe to call more than once."""
        self._http.close()

    def __enter__(self) -> Danipa:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()


class AsyncDanipa:
    """``asyncio`` client over :class:`httpx.AsyncClient`.

    Same parameters, request building and retry policy as :class:`Danipa`;
    ``http_client`` takes an :class:`httpx.AsyncClient`.
    """

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        environment: Environment | None = None,
        timeout: TimeoutTypes = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._http = _AsyncHttp(
            api_key,
            base_url=base_url,
            environment=environment,
            timeout=timeout,
            max_retries=max_retries,
            http_client=http_client,
            transport=transport,
        )
        self.merchants = AsyncMerchantsResource(self._http)
        self.payment_links = AsyncPaymentLinksResource(self._http)
        self.invoices = AsyncInvoicesResource(self._http)
        self.balances = AsyncBalancesResource(self._http)

    @property
    def base_url(self) -> str:
        return self._http.base_url

    async def aclose(self) -> None:
        """Close the HTTP client if the SDK created it."""
        await self._http.aclose()

    async def __aenter__(self) -> AsyncDanipa:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        await self.aclose()
