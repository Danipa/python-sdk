"""``Danipa`` — main entry point.

Construct once with your API key and reuse the same instance across requests.
Every resource shares the underlying HTTP client (auth, retry, timeout).

Sandbox vs production is inferred from the API key prefix:

* ``dk_test_…`` (or any non-``dk_live_…`` value) → ``https://api.sandbox.danipa.com``
* ``dk_live_…`` → ``https://api.danipa.com``

Pass an explicit ``base_url`` to override.

Example
-------
.. code-block:: python

    import os
    from danipa import Danipa, RequestOptions
    from danipa.models import CreateCollectionRequest, Payer

    with Danipa(api_key=os.environ["DANIPA_API_KEY"]) as danipa:
        collection = danipa.collections.create(
            CreateCollectionRequest(
                amount="125.00",
                currency="GHS",
                payer=Payer(phone="+233244112233", name="Ama K."),
            ),
            options=RequestOptions(idempotency_key="order-1234"),
        )
"""

from __future__ import annotations

import httpx

from danipa.http import _HttpClient
from danipa.resources import (
    CollectionsResource,
    DisbursementsResource,
    InvoicesResource,
    PaymentLinksResource,
    WalletsResource,
)


class Danipa:
    """The Danipa SDK entry point. Holds one shared HTTP client."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._http = _HttpClient(
            api_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=max_retries,
            transport=transport,
        )
        self.collections = CollectionsResource(self._http)
        self.disbursements = DisbursementsResource(self._http)
        self.wallets = WalletsResource(self._http)
        self.payment_links = PaymentLinksResource(self._http)
        self.invoices = InvoicesResource(self._http)

    def close(self) -> None:
        """Close the underlying HTTP client. Safe to call more than once."""
        self._http.close()

    def __enter__(self) -> Danipa:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()
