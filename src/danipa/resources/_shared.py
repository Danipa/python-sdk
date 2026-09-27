"""Response-to-model mapping shared by the sync and async resources."""

from __future__ import annotations

import uuid
from typing import Any, TypeVar

import pydantic

from danipa.errors import ResponseParseError
from danipa.http import ResponseMeta
from danipa.models._base import _ResponseModel

M = TypeVar("M", bound=_ResponseModel)


def to_model(model: type[M], body: Any, meta: ResponseMeta) -> M:
    """Validate a 2xx body into ``model``.

    A body that does not match the model is a :class:`ResponseParseError`, never
    a network error: the server answered 2xx, so the call may have succeeded.
    """
    try:
        result = model.model_validate(body)
    except pydantic.ValidationError as exc:
        raise ResponseParseError(
            f"Danipa SDK: HTTP {meta.status} response did not match {model.__name__} "
            "(the call may have succeeded)",
            status=meta.status,
            body=repr(body),
            request_id=meta.request_id,
            idempotency_key=meta.idempotency_key,
            cause=exc,
        ) from exc
    result._response_meta = meta
    return result


def to_model_list(model: type[M], body: Any, meta: ResponseMeta) -> list[M]:
    """Validate a 2xx JSON array into ``list[model]`` (each item carries ``meta``)."""
    if not isinstance(body, list):
        raise ResponseParseError(
            f"Danipa SDK: HTTP {meta.status} response is not a JSON array of "
            f"{model.__name__} (the call may have succeeded)",
            status=meta.status,
            body=repr(body),
            request_id=meta.request_id,
            idempotency_key=meta.idempotency_key,
        )
    return [to_model(model, item, meta) for item in body]


def path_id(value: str | uuid.UUID) -> str:
    """Validate a resource id as a UUID and render it canonically.

    The server only routes UUID ids for API keys; any other value would come
    back as a misleading ``403 API_KEY_SCOPE_DENIED``, so it is rejected here
    with a :class:`ValueError` before anything is sent.
    """
    if isinstance(value, uuid.UUID):
        return str(value)
    try:
        return str(uuid.UUID(value))
    except (ValueError, TypeError, AttributeError):
        raise ValueError(f"Danipa SDK: id must be a UUID, got {value!r}") from None


MAX_PAGE_SIZE = 200


def paging(page: int | None, size: int | None) -> dict[str, Any]:
    """Query params for a list call; bounds match the server (page >= 0, size 1 to 200)."""
    if page is not None and page < 0:
        raise ValueError("Danipa SDK: page must be >= 0 (pages are zero-based)")
    if size is not None and not 1 <= size <= MAX_PAGE_SIZE:
        raise ValueError(f"Danipa SDK: size must be between 1 and {MAX_PAGE_SIZE}")
    return {"page": page, "size": size}
