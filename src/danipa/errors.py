"""Exception hierarchy raised by the Danipa SDK.

Matches the Node SDK 1:1 — catch :class:`DanipaError` once, then narrow with
``isinstance(err, DanipaApiError)`` for HTTP failures or
``isinstance(err, DanipaNetworkError)`` for transport failures.
"""

from __future__ import annotations

from typing import Any


class DanipaError(Exception):
    """Base class for every error this SDK raises."""


class DanipaApiError(DanipaError):
    """Raised when the backend returns a non-2xx response.

    Carries the parsed error envelope (matches ``StatusUtils.createErrorStatus``
    on the fintech backend) so callers can branch on stable error codes.
    """

    def __init__(
        self,
        status: int,
        code: str,
        message: str,
        correlation_id: str | None,
        raw: Any,
    ) -> None:
        super().__init__(message)
        self.status = status
        self.code = code
        self.correlation_id = correlation_id
        self.raw = raw


class DanipaNetworkError(DanipaError):
    """Raised when the request never reached the backend (DNS, TLS, timeout, abort)."""

    def __init__(self, message: str, cause: BaseException | None = None) -> None:
        super().__init__(message)
        self.cause = cause
