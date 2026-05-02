"""Internal HTTP client used by every resource module.

Retries: 5xx responses + transport errors only. 4xx never retries — they
indicate a client-side fix is needed and a retry would just burn the user's
rate limit.

Idempotency: every mutating call should pass ``idempotency_key`` so retries
(server- or client-side) don't double-charge. The header is forwarded
verbatim — backend dedupes on ``(merchantId, key)``.
"""

from __future__ import annotations

import json as _json
import random
import time
from dataclasses import dataclass
from typing import Any

import httpx

from danipa._version import __version__
from danipa.errors import DanipaApiError, DanipaNetworkError

SANDBOX_BASE_URL = "https://api.sandbox.danipa.com/ms"
PRODUCTION_BASE_URL = "https://api.danipa.com/ms"


def infer_base_url(api_key: str) -> str:
    """Infer sandbox vs production from the API key prefix.

    ``dk_live_*`` → production; anything else (including ``dk_test_*``) →
    sandbox. Callers can override by passing an explicit ``base_url``.
    """
    if api_key.startswith("dk_live_"):
        return PRODUCTION_BASE_URL
    return SANDBOX_BASE_URL


@dataclass(frozen=True, slots=True)
class RequestOptions:
    """Per-call overrides forwarded by resource methods to :class:`_HttpClient`."""

    idempotency_key: str | None = None
    """Sent as ``X-Idempotency-Key`` on POST. Strongly recommended for mutating calls."""

    timeout: float | None = None
    """Per-call timeout override, in seconds."""


@dataclass(frozen=True, slots=True)
class _RequestSpec:
    method: str
    path: str
    query: dict[str, Any] | None = None
    body: Any = None
    options: RequestOptions | None = None


class _HttpClient:
    """Thin wrapper over :class:`httpx.Client` — auth, retry, idempotency."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        timeout: float = 30.0,
        max_retries: int = 3,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise TypeError("Danipa SDK: api_key is required")
        if max_retries < 1:
            raise ValueError("Danipa SDK: max_retries must be >= 1")

        self._api_key = api_key
        self._base_url = (base_url or infer_base_url(api_key)).rstrip("/")
        self._timeout = timeout
        self._max_retries = max_retries
        self._client = httpx.Client(
            timeout=timeout,
            transport=transport,
            headers={
                "Authorization": f"Bearer {api_key}",
                "Accept": "application/json",
                "User-Agent": f"danipa-python-sdk/{__version__}",
            },
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> _HttpClient:
        return self

    def __exit__(self, *_exc: object) -> None:
        self.close()

    def request(self, spec: _RequestSpec) -> Any:
        url = self._build_url(spec.path)
        params = {k: v for k, v in (spec.query or {}).items() if v is not None} or None
        opts = spec.options
        per_call_timeout = opts.timeout if opts and opts.timeout is not None else self._timeout

        headers: dict[str, str] = {}
        if spec.body is not None:
            headers["Content-Type"] = "application/json"
        if opts and opts.idempotency_key:
            headers["X-Idempotency-Key"] = opts.idempotency_key

        body_bytes: bytes | None = None
        if spec.body is not None:
            body_bytes = _json.dumps(spec.body, separators=(",", ":")).encode("utf-8")

        last_transport_err: BaseException | None = None
        for attempt in range(1, self._max_retries + 1):
            try:
                response = self._client.request(
                    spec.method,
                    url,
                    params=params,
                    headers=headers or None,
                    content=body_bytes,
                    timeout=per_call_timeout,
                )
            except httpx.RequestError as exc:
                last_transport_err = exc
                if attempt == self._max_retries:
                    raise DanipaNetworkError(
                        f"Danipa SDK: request to {spec.method} {spec.path} "
                        f"failed after {self._max_retries} attempts",
                        cause=exc,
                    ) from exc
                self._backoff(attempt)
                continue

            if response.is_success:
                return self._parse_body(response)

            # 4xx — caller error; never retry.
            if response.status_code < 500:
                raise self._to_api_error(response)

            # 5xx — retry until budget exhausted, then surface as ApiError.
            if attempt == self._max_retries:
                raise self._to_api_error(response)
            self._backoff(attempt)

        raise DanipaNetworkError(
            "Danipa SDK: retry loop exited unexpectedly",
            cause=last_transport_err,
        )

    def _build_url(self, path: str) -> str:
        suffix = path if path.startswith("/") else f"/{path}"
        return self._base_url + suffix

    @staticmethod
    def _parse_body(response: httpx.Response) -> Any:
        text = response.text
        if not text:
            return None
        try:
            return _json.loads(text)
        except ValueError:
            return text

    def _to_api_error(self, response: httpx.Response) -> DanipaApiError:
        raw = self._parse_body(response)
        envelope = raw if isinstance(raw, dict) else None
        first_error: dict[str, Any] = {}
        if envelope:
            errors = envelope.get("errors")
            if isinstance(errors, list) and errors and isinstance(errors[0], dict):
                first_error = errors[0]
        correlation_id = envelope.get("correlationId") if envelope else None
        return DanipaApiError(
            status=response.status_code,
            code=str(first_error.get("code") or "UNKNOWN"),
            message=str(first_error.get("description") or f"HTTP {response.status_code}"),
            correlation_id=correlation_id if isinstance(correlation_id, str) else None,
            raw=raw,
        )

    @staticmethod
    def _backoff(attempt: int) -> None:
        base_ms = min(200 * (2 ** (attempt - 1)), 2_000)
        jitter_ms = random.random() * 50
        time.sleep((base_ms + jitter_ms) / 1000.0)
