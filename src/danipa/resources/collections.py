"""Collections (pull-from-payer) resource."""

from __future__ import annotations

from urllib.parse import quote

from danipa.http import RequestOptions, _HttpClient, _RequestSpec
from danipa.models.collections import Collection, CreateCollectionRequest


class CollectionsResource:
    def __init__(self, http: _HttpClient) -> None:
        self._http = http

    def create(
        self,
        request: CreateCollectionRequest,
        *,
        options: RequestOptions | None = None,
    ) -> Collection:
        """Initiate a pull-from-payer collection.

        Returns a :class:`Collection` in ``PENDING`` state — listen for
        ``collection.completed`` / ``collection.failed`` webhooks for the
        terminal state, or poll :meth:`get`.
        """
        body = self._http.request(
            _RequestSpec(
                method="POST",
                path="/v1/collections",
                body=request.model_dump(by_alias=True, exclude_none=True),
                options=options,
            )
        )
        return Collection.model_validate(body)

    def get(self, id: str, *, options: RequestOptions | None = None) -> Collection:
        body = self._http.request(
            _RequestSpec(
                method="GET",
                path=f"/v1/collections/{quote(id, safe='')}",
                options=options,
            )
        )
        return Collection.model_validate(body)
