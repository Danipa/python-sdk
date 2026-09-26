"""Exception hierarchy raised by the Danipa SDK.

Catch :class:`DanipaError` once, then narrow::

    DanipaError
    ├── DanipaApiError              the server answered with a non-2xx status
    │   ├── ValidationError         400 / 422 (``field_errors`` populated)
    │   ├── AuthenticationError     401 (bad / expired API key)
    │   ├── PermissionDeniedError   403 (incl. API_KEY_SCOPE_DENIED, AMBIGUOUS_CREDENTIALS)
    │   ├── NotFoundError           404
    │   ├── ConflictError           409
    │   │   └── IdempotencyError    409 with an IDEMPOTENCY_* code
    │   ├── RateLimitError          429 (``retry_after`` in seconds)
    │   └── ServerError             5xx
    ├── DanipaNetworkError          no response at all (DNS, TLS, reset, timeout)
    │   ├── DanipaConnectionError   could not connect / connection dropped
    │   └── DanipaTimeoutError      the request timed out
    ├── ResponseParseError          a 2xx whose body could not be parsed. The call
    │                               may well have SUCCEEDED; only re-issue it with
    │                               the same ``idempotency_key``
    └── WebhookVerificationError    ``construct_event`` rejected a delivery

Both server error shapes are understood: the ``ApiStatus`` envelope
(``errors[0].code/description``, ``fieldErrors``, ``retryable``,
``retryAfterSeconds``, ``traceId``, ``correlationId``, ``messageKey``) and the
flat ``{"code", "description"}`` body written by servlet filters.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any


class DanipaError(Exception):
    """Base class for every error this SDK raises."""


@dataclass(frozen=True, slots=True)
class FieldError:
    """One field-level validation failure from ``ApiStatus.fieldErrors``."""

    field: str | None
    code: str | None
    message: str | None


class DanipaApiError(DanipaError):
    """The backend returned a non-2xx response."""

    def __init__(
        self,
        *,
        status: int,
        code: str,
        message: str,
        request_id: str | None = None,
        raw: Any = None,
        headers: Mapping[str, str] | None = None,
        field_errors: list[FieldError] | None = None,
        retryable: bool | None = None,
        retry_after: float | None = None,
        trace_id: str | None = None,
        correlation_id: str | None = None,
        message_key: str | None = None,
        idempotency_key: str | None = None,
        idempotent_replay: bool = False,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.message = message
        self.request_id = request_id
        self.raw = raw
        self.headers: dict[str, str] = dict(headers or {})
        self.field_errors: list[FieldError] = list(field_errors or [])
        self.retryable = retryable
        self.retry_after = retry_after
        self.trace_id = trace_id
        self.correlation_id = correlation_id
        self.message_key = message_key
        self.idempotency_key = idempotency_key
        self.idempotent_replay = idempotent_replay

    def __str__(self) -> str:
        text = f"[HTTP {self.status} {self.code}] {self.message}"
        if self.request_id:
            text += f" (request_id={self.request_id})"
        return text

    def __repr__(self) -> str:
        return (
            f"{type(self).__name__}(status={self.status!r}, code={self.code!r}, "
            f"message={self.message!r}, request_id={self.request_id!r})"
        )


class ValidationError(DanipaApiError):
    """400 / 422: the request was rejected; see :attr:`field_errors`."""


class AuthenticationError(DanipaApiError):
    """401: the API key is missing, invalid or expired."""


class PermissionDeniedError(DanipaApiError):
    """403: the key is valid but may not do this.

    Common codes: ``API_KEY_SCOPE_DENIED`` (the route is not on the API-key
    surface yet, see #5573), ``AMBIGUOUS_CREDENTIALS``, ``IP_NOT_ALLOWED``,
    ``REFERER_NOT_ALLOWED``, ``BILLING_SUSPENDED``.
    """


class NotFoundError(DanipaApiError):
    """404: the resource does not exist (or is not visible to this key)."""


class ConflictError(DanipaApiError):
    """409: the request conflicts with the current state."""


class IdempotencyError(ConflictError):
    """409 with an ``IDEMPOTENCY_*`` code: the key was reused with a different body."""


class RateLimitError(DanipaApiError):
    """429: slow down. :attr:`retry_after` holds the server's hint in seconds."""


class ServerError(DanipaApiError):
    """5xx: the server failed. 500 and 501 are not retried automatically."""


class DanipaNetworkError(DanipaError):
    """The request never produced a response (DNS, TLS, connection reset, timeout).

    For a mutating call the server may still have processed it; re-issue it with
    the same :attr:`idempotency_key` to be safe.
    """

    def __init__(
        self,
        message: str,
        cause: BaseException | None = None,
        *,
        idempotency_key: str | None = None,
    ) -> None:
        super().__init__(message)
        self.cause = cause
        self.idempotency_key = idempotency_key


class DanipaConnectionError(DanipaNetworkError):
    """Could not connect, or the connection dropped before a response arrived."""


class DanipaTimeoutError(DanipaNetworkError):
    """The request timed out before a response arrived."""


class ResponseParseError(DanipaError):
    """The server answered 2xx but the body could not be parsed.

    This is NOT a network error: the call most likely succeeded server-side.
    """

    def __init__(
        self,
        message: str,
        *,
        status: int,
        body: str,
        request_id: str | None = None,
        idempotency_key: str | None = None,
        cause: BaseException | None = None,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.body = body
        self.request_id = request_id
        self.idempotency_key = idempotency_key
        self.cause = cause


class WebhookVerificationError(DanipaError):
    """A webhook delivery failed signature/timestamp verification or could not be parsed."""


_STATUS_CLASSES: dict[int, type[DanipaApiError]] = {
    400: ValidationError,
    401: AuthenticationError,
    403: PermissionDeniedError,
    404: NotFoundError,
    409: ConflictError,
    422: ValidationError,
    429: RateLimitError,
}


def error_class_for(status: int, code: str) -> type[DanipaApiError]:
    """Pick the typed subclass for an HTTP status (and, for 409, the code)."""
    if status == 409 and code.upper().startswith("IDEMPOTENCY"):
        return IdempotencyError
    if status >= 500:
        return ServerError
    return _STATUS_CLASSES.get(status, DanipaApiError)
