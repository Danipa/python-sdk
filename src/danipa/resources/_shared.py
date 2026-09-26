"""Response-to-model mapping shared by the sync and async resources."""

from __future__ import annotations

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
