"""Disbursements (push-to-payee) resource."""

from __future__ import annotations

from urllib.parse import quote

from danipa.http import RequestOptions, _HttpClient, _RequestSpec
from danipa.models.disbursements import CreateDisbursementRequest, Disbursement


class DisbursementsResource:
    def __init__(self, http: _HttpClient) -> None:
        self._http = http

    def create(
        self,
        request: CreateDisbursementRequest,
        *,
        options: RequestOptions | None = None,
    ) -> Disbursement:
        """Push a disbursement to a payee (MoMo wallet, bank account).

        Strongly recommended to pass an ``idempotency_key`` via
        :class:`RequestOptions` — disbursement creation is the most
        expensive operation to accidentally duplicate.
        """
        body = self._http.request(
            _RequestSpec(
                method="POST",
                path="/v1/disbursements",
                body=request.model_dump(by_alias=True, exclude_none=True),
                options=options,
            )
        )
        return Disbursement.model_validate(body)

    def get(self, id: str, *, options: RequestOptions | None = None) -> Disbursement:
        body = self._http.request(
            _RequestSpec(
                method="GET",
                path=f"/v1/disbursements/{quote(id, safe='')}",
                options=options,
            )
        )
        return Disbursement.model_validate(body)
