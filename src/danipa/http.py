"""HTTP core shared by :class:`danipa.Danipa` and :class:`danipa.AsyncDanipa`.

Everything that decides *what goes on the wire* (headers, idempotency key, body)
and *whether to retry* lives in :class:`_BaseHttp`, so the sync and async clients
cannot drift. The two subclasses only differ in how they send and sleep.

Wire contract (phase 1, identical across the Node, Python, Java and PHP SDKs):

* Auth is ``X-API-Key: <key>``. ``Authorization`` is never sent: the fintech
  ``ApiKeyAuthenticationFilter`` rejects a request carrying both with
  ``403 AMBIGUOUS_CREDENTIALS``. An ``Authorization`` header set on an injected
  ``httpx`` client is stripped, and client-level ``auth`` is ignored.
* Every POST/PUT/PATCH/DELETE carries ``Idempotency-Key`` (max 255 chars). One is
  generated (UUIDv4) when the caller gives none, and the same key is reused on
  every retry of that call.
* Retries: GET/HEAD/OPTIONS always; mutating methods only because they always
  carry a key. Retried on connect/read errors and on 408, 429, 502, 503, 504,
  never on 500/501 or any other 4xx. ``Retry-After`` (seconds) is honoured up to
  60 s; otherwise exponential backoff with full jitter (base 0.5 s, cap 8 s).
"""

from __future__ import annotations

import asyncio
import json
import platform
import random
import time
import uuid
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal

import httpx

from danipa._version import package_version
from danipa.errors import (
    DanipaApiError,
    DanipaConfigurationError,
    DanipaConnectionError,
    DanipaNetworkError,
    DanipaTimeoutError,
    FieldError,
    ResponseParseError,
    error_class_for,
)

SANDBOX_BASE_URL = "https://api.sandbox.danipa.com/ms"
PRODUCTION_BASE_URL = "https://api.danipa.com/ms"
"""Production is not live yet; only a ``dk_live_`` key (or an explicit override) reaches it."""

TEST_KEY_PREFIX = "dk_test_"
LIVE_KEY_PREFIX = "dk_live_"

Environment = Literal["sandbox", "live"]
"""An explicit environment: ``"sandbox"`` or ``"live"``."""

ENVIRONMENT_BASE_URLS: dict[str, str] = {
    "sandbox": SANDBOX_BASE_URL,
    "live": PRODUCTION_BASE_URL,
}

DEFAULT_TIMEOUT = 30.0
DEFAULT_MAX_RETRIES = 2
MAX_IDEMPOTENCY_KEY_LENGTH = 255
RETRY_AFTER_CAP_SECONDS = 60.0
BACKOFF_BASE_SECONDS = 0.5
BACKOFF_CAP_SECONDS = 8.0

RETRYABLE_STATUSES = frozenset({408, 429, 502, 503, 504})
SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
MUTATING_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})

TimeoutTypes = float | httpx.Timeout


def infer_base_url(api_key: str) -> str:
    """Infer the host from the key prefix (the server's own environment marker).

    ``dk_test_*`` resolves to sandbox and ``dk_live_*`` to production (not live
    yet). Any other prefix raises :class:`~danipa.DanipaConfigurationError`
    rather than guessing: sending a key to the wrong environment is never what
    you want. Pass ``base_url`` or ``environment`` to choose explicitly.
    """
    if api_key.startswith(TEST_KEY_PREFIX):
        return SANDBOX_BASE_URL
    if api_key.startswith(LIVE_KEY_PREFIX):
        return PRODUCTION_BASE_URL
    raise DanipaConfigurationError(
        "Danipa SDK: cannot tell the environment from this API key. Danipa keys start "
        f"with '{TEST_KEY_PREFIX}' (sandbox) or '{LIVE_KEY_PREFIX}' (live). Check the key, "
        "or pass base_url=... or environment='sandbox'|'live' explicitly."
    )


def resolve_base_url(
    api_key: str,
    base_url: str | None = None,
    environment: str | None = None,
) -> str:
    """Pick the host: ``base_url`` wins, then ``environment``, then the key prefix."""
    if base_url:
        return base_url.rstrip("/")
    if environment is not None:
        try:
            return ENVIRONMENT_BASE_URLS[environment]
        except KeyError:
            raise DanipaConfigurationError(
                f"Danipa SDK: unknown environment {environment!r}; use 'sandbox' or 'live'"
            ) from None
    return infer_base_url(api_key)


def user_agent() -> str:
    """``danipa-python/<package version> python/<runtime version>``."""
    return f"danipa-python/{package_version()} python/{platform.python_version()}"


@dataclass(frozen=True, slots=True)
class RequestOptions:
    """Per-call overrides accepted by every resource method."""

    idempotency_key: str | None = None
    """Sent as ``Idempotency-Key``. Generated automatically for mutating calls when omitted."""

    timeout: TimeoutTypes | None = None
    """Per-call timeout (seconds or an :class:`httpx.Timeout`)."""

    max_retries: int | None = None
    """Per-call retry budget (number of RETRIES; 0 disables)."""


@dataclass(frozen=True, slots=True)
class ResponseMeta:
    """What the SDK knows about the HTTP exchange behind a returned model."""

    status: int
    headers: dict[str, str]
    request_id: str | None
    idempotency_key: str | None
    idempotent_replay: bool


@dataclass(frozen=True, slots=True)
class _RequestSpec:
    method: str
    path: str
    query: dict[str, Any] | None = None
    body: Any = None
    options: RequestOptions | None = None


@dataclass(frozen=True, slots=True)
class _Prepared:
    method: str
    url: str
    params: dict[str, Any] | None
    headers: dict[str, str]
    content: bytes | None
    timeout: TimeoutTypes
    idempotency_key: str | None
    max_retries: int


def _validate_max_retries(value: int) -> int:
    if value < 0:
        raise ValueError("Danipa SDK: max_retries must be >= 0")
    return value


def _json_default(value: Any) -> Any:
    if isinstance(value, Decimal):
        return str(value)
    raise TypeError(f"Object of type {type(value).__name__} is not JSON serializable")


def _parse_json(text: str) -> Any:
    """Parse JSON keeping every JSON number with a fraction as :class:`Decimal`."""
    return json.loads(text, parse_float=Decimal)


def _parse_retry_after(value: str | None) -> float | None:
    if value is None:
        return None
    try:
        seconds = float(value.strip())
    except ValueError:
        return None  # HTTP-date form: fall back to backoff
    if seconds != seconds or seconds < 0:  # NaN or negative
        return None
    return seconds


def _request_id(headers: httpx.Headers, body: Any) -> str | None:
    for name in ("x-correlation-id", "x-request-id"):
        header: str | None = headers.get(name)
        if header:
            return header
    if isinstance(body, dict):
        for key in ("correlationId", "traceId"):
            value = body.get(key)
            if isinstance(value, str) and value:
                return value
    return None


def _opt_str(value: Any) -> str | None:
    return value if isinstance(value, str) else None


class _BaseHttp:
    """Request building, retry policy and response mapping. No I/O."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None,
        timeout: TimeoutTypes,
        max_retries: int,
        environment: str | None = None,
    ) -> None:
        if not api_key:
            raise TypeError("Danipa SDK: api_key is required")
        self._api_key = api_key
        self._base_url = resolve_base_url(api_key, base_url, environment)
        self._timeout = timeout
        self._max_retries = _validate_max_retries(max_retries)
        self._user_agent = user_agent()

    @property
    def base_url(self) -> str:
        return self._base_url

    # -- request building -------------------------------------------------

    def _prepare(self, spec: _RequestSpec) -> _Prepared:
        method = spec.method.upper()
        opts = spec.options or RequestOptions()

        key = opts.idempotency_key
        if key is not None:
            if not key:
                raise ValueError("Danipa SDK: idempotency_key must not be empty")
            if len(key) > MAX_IDEMPOTENCY_KEY_LENGTH:
                raise ValueError(
                    f"Danipa SDK: idempotency_key must be at most "
                    f"{MAX_IDEMPOTENCY_KEY_LENGTH} characters"
                )
        elif method in MUTATING_METHODS:
            key = str(uuid.uuid4())

        headers = {
            "X-API-Key": self._api_key,
            "Accept": "application/json",
            "User-Agent": self._user_agent,
        }
        if key is not None:
            headers["Idempotency-Key"] = key

        content: bytes | None = None
        if spec.body is not None:
            headers["Content-Type"] = "application/json"
            content = json.dumps(spec.body, separators=(",", ":"), default=_json_default).encode(
                "utf-8"
            )

        path = spec.path if spec.path.startswith("/") else f"/{spec.path}"
        params = {k: v for k, v in (spec.query or {}).items() if v is not None} or None
        max_retries = (
            _validate_max_retries(opts.max_retries)
            if opts.max_retries is not None
            else self._max_retries
        )
        return _Prepared(
            method=method,
            url=self._base_url + path,
            params=params,
            headers=headers,
            content=content,
            timeout=opts.timeout if opts.timeout is not None else self._timeout,
            idempotency_key=key,
            max_retries=max_retries,
        )

    @staticmethod
    def _build(client: httpx.Client | httpx.AsyncClient, p: _Prepared) -> httpx.Request:
        request = client.build_request(
            p.method,
            p.url,
            params=p.params,
            headers=p.headers,
            content=p.content,
            timeout=p.timeout,
        )
        # Never send Authorization alongside X-API-Key (403 AMBIGUOUS_CREDENTIALS),
        # even if an injected client carries a default one.
        request.headers.pop("Authorization", None)
        return request

    # -- retry policy -----------------------------------------------------

    @staticmethod
    def _retry_safe(p: _Prepared) -> bool:
        return p.method in SAFE_METHODS or p.idempotency_key is not None

    @staticmethod
    def _backoff(retries_done: int) -> float:
        ceiling = min(BACKOFF_CAP_SECONDS, BACKOFF_BASE_SECONDS * (2**retries_done))
        return random.uniform(0.0, ceiling)

    def _retry_delay(
        self,
        p: _Prepared,
        retries_done: int,
        response: httpx.Response | None,
        exc: Exception | None = None,
    ) -> float | None:
        """Seconds to wait before the next attempt, or ``None`` to stop."""
        if retries_done >= p.max_retries or not self._retry_safe(p):
            return None
        if response is not None:
            if response.status_code not in RETRYABLE_STATUSES:
                return None
            retry_after = _parse_retry_after(response.headers.get("retry-after"))
            if retry_after is not None:
                return min(retry_after, RETRY_AFTER_CAP_SECONDS)
            return self._backoff(retries_done)
        if isinstance(exc, (httpx.UnsupportedProtocol, httpx.LocalProtocolError)):
            return None  # a malformed request will not get better by repeating it
        if isinstance(exc, httpx.TransportError):
            return self._backoff(retries_done)
        return None

    # -- response mapping -------------------------------------------------

    def _finish(self, p: _Prepared, response: httpx.Response) -> tuple[Any, ResponseMeta]:
        text = response.text
        if response.is_success:
            meta = self._meta(p, response, None)
            if not text.strip():
                return None, meta
            try:
                body = _parse_json(text)
            except ValueError as exc:
                raise ResponseParseError(
                    f"Danipa SDK: {p.method} {p.url} returned HTTP {response.status_code} "
                    "but the body is not valid JSON (the call may have succeeded)",
                    status=response.status_code,
                    body=text,
                    request_id=meta.request_id,
                    idempotency_key=p.idempotency_key,
                    cause=exc,
                ) from exc
            meta = self._meta(p, response, body)
            return body, meta
        raise self._api_error(p, response, text)

    @staticmethod
    def _meta(p: _Prepared, response: httpx.Response, body: Any) -> ResponseMeta:
        return ResponseMeta(
            status=response.status_code,
            headers={k.lower(): v for k, v in response.headers.items()},
            request_id=_request_id(response.headers, body),
            idempotency_key=p.idempotency_key,
            idempotent_replay=response.headers.get("x-idempotent-replay", "").lower() == "true",
        )

    def _api_error(self, p: _Prepared, response: httpx.Response, text: str) -> DanipaApiError:
        raw: Any
        try:
            raw = _parse_json(text) if text.strip() else None
        except ValueError:
            raw = text
        body: dict[str, Any] = raw if isinstance(raw, dict) else {}

        first: dict[str, Any] = {}
        errors = body.get("errors")
        if isinstance(errors, list) and errors and isinstance(errors[0], dict):
            first = errors[0]
        code = _opt_str(first.get("code")) or _opt_str(body.get("code")) or "UNKNOWN"
        message = (
            _opt_str(first.get("description"))
            or _opt_str(body.get("description"))
            or _opt_str(body.get("message"))
            or f"HTTP {response.status_code}"
        )

        field_errors: list[FieldError] = []
        raw_fields = body.get("fieldErrors")
        if isinstance(raw_fields, list):
            for item in raw_fields:
                if isinstance(item, dict):
                    field_errors.append(
                        FieldError(
                            field=_opt_str(item.get("field")),
                            code=_opt_str(item.get("code")),
                            message=_opt_str(item.get("message")),
                        )
                    )

        retry_after = _parse_retry_after(response.headers.get("retry-after"))
        body_retry_after = body.get("retryAfterSeconds")
        if (
            retry_after is None
            and isinstance(body_retry_after, (int, Decimal))
            and not isinstance(body_retry_after, bool)
        ):
            retry_after = float(body_retry_after)
        retryable = body.get("retryable")

        meta = self._meta(p, response, body)
        cls = error_class_for(response.status_code, code)
        return cls(
            status=response.status_code,
            code=code,
            message=message,
            request_id=meta.request_id,
            raw=raw,
            headers=meta.headers,
            field_errors=field_errors,
            retryable=retryable if isinstance(retryable, bool) else None,
            retry_after=retry_after,
            trace_id=_opt_str(body.get("traceId")),
            correlation_id=_opt_str(body.get("correlationId")),
            message_key=_opt_str(body.get("messageKey")),
            idempotency_key=p.idempotency_key,
            idempotent_replay=meta.idempotent_replay,
        )

    @staticmethod
    def _network_error(p: _Prepared, exc: Exception, attempts: int) -> DanipaNetworkError:
        cls: type[DanipaNetworkError] = (
            DanipaTimeoutError if isinstance(exc, httpx.TimeoutException) else DanipaConnectionError
        )
        return cls(
            f"Danipa SDK: {p.method} {p.url} failed after {attempts} attempt(s): {exc}",
            cause=exc,
            idempotency_key=p.idempotency_key,
        )


class _SyncHttp(_BaseHttp):
    """Blocking transport over :class:`httpx.Client`."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        environment: str | None = None,
        timeout: TimeoutTypes = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: httpx.Client | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        super().__init__(
            api_key,
            base_url=base_url,
            environment=environment,
            timeout=timeout,
            max_retries=max_retries,
        )
        self._owns_client = http_client is None
        self._client = http_client or httpx.Client(timeout=timeout, transport=transport)

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def request(self, spec: _RequestSpec) -> tuple[Any, ResponseMeta]:
        p = self._prepare(spec)
        retries = 0
        while True:
            request = self._build(self._client, p)
            try:
                response = self._client.send(request, auth=httpx.Auth(), follow_redirects=False)
            except httpx.RequestError as exc:
                delay = self._retry_delay(p, retries, None, exc)
                if delay is None:
                    raise self._network_error(p, exc, retries + 1) from exc
            else:
                delay = self._retry_delay(p, retries, response)
                if delay is None:
                    return self._finish(p, response)
                response.close()
            time.sleep(delay)
            retries += 1


class _AsyncHttp(_BaseHttp):
    """Non-blocking transport over :class:`httpx.AsyncClient`."""

    def __init__(
        self,
        api_key: str,
        *,
        base_url: str | None = None,
        environment: str | None = None,
        timeout: TimeoutTypes = DEFAULT_TIMEOUT,
        max_retries: int = DEFAULT_MAX_RETRIES,
        http_client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        super().__init__(
            api_key,
            base_url=base_url,
            environment=environment,
            timeout=timeout,
            max_retries=max_retries,
        )
        self._owns_client = http_client is None
        self._client = http_client or httpx.AsyncClient(timeout=timeout, transport=transport)

    async def aclose(self) -> None:
        if self._owns_client:
            await self._client.aclose()

    async def request(self, spec: _RequestSpec) -> tuple[Any, ResponseMeta]:
        p = self._prepare(spec)
        retries = 0
        while True:
            request = self._build(self._client, p)
            try:
                response = await self._client.send(
                    request, auth=httpx.Auth(), follow_redirects=False
                )
            except httpx.RequestError as exc:
                delay = self._retry_delay(p, retries, None, exc)
                if delay is None:
                    raise self._network_error(p, exc, retries + 1) from exc
            else:
                delay = self._retry_delay(p, retries, response)
                if delay is None:
                    return self._finish(p, response)
                await response.aclose()
            await asyncio.sleep(delay)
            retries += 1
