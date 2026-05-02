"""Official Python SDK for the Danipa fintech API."""

from __future__ import annotations

from danipa._version import __version__
from danipa.client import Danipa
from danipa.errors import DanipaApiError, DanipaError, DanipaNetworkError
from danipa.http import RequestOptions
from danipa.webhook import REPLAY_WINDOW_SECONDS, compute_signature, verify

verify_webhook = verify
"""Top-level alias for :func:`danipa.webhook.verify`."""

__all__ = [
    "REPLAY_WINDOW_SECONDS",
    "Danipa",
    "DanipaApiError",
    "DanipaError",
    "DanipaNetworkError",
    "RequestOptions",
    "__version__",
    "compute_signature",
    "verify",
    "verify_webhook",
]
