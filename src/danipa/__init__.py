"""Official Python SDK for the Danipa fintech API."""

from __future__ import annotations

from danipa._version import __version__
from danipa.client import AsyncDanipa, Danipa
from danipa.errors import (
    AuthenticationError,
    ConflictError,
    DanipaApiError,
    DanipaConfigurationError,
    DanipaConnectionError,
    DanipaError,
    DanipaNetworkError,
    DanipaTimeoutError,
    FieldError,
    IdempotencyError,
    NotFoundError,
    PermissionDeniedError,
    RateLimitError,
    ResponseParseError,
    ServerError,
    ValidationError,
    WebhookVerificationError,
)
from danipa.http import RequestOptions, ResponseMeta
from danipa.webhook import (
    REPLAY_WINDOW_SECONDS,
    WebhookEvent,
    compute_signature,
    construct_event,
    verify,
)

verify_webhook = verify
"""Top-level alias for :func:`danipa.webhook.verify`."""

__all__ = [
    "REPLAY_WINDOW_SECONDS",
    "AsyncDanipa",
    "AuthenticationError",
    "ConflictError",
    "Danipa",
    "DanipaApiError",
    "DanipaConfigurationError",
    "DanipaConnectionError",
    "DanipaError",
    "DanipaNetworkError",
    "DanipaTimeoutError",
    "FieldError",
    "IdempotencyError",
    "NotFoundError",
    "PermissionDeniedError",
    "RateLimitError",
    "RequestOptions",
    "ResponseMeta",
    "ResponseParseError",
    "ServerError",
    "ValidationError",
    "WebhookEvent",
    "WebhookVerificationError",
    "__version__",
    "compute_signature",
    "construct_event",
    "verify",
    "verify_webhook",
]
