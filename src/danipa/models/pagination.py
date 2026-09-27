"""``Page[T]``: one page of a list endpoint (a Spring Data ``Page`` on the server).

The server serialises ``Page`` directly today (``content`` plus flat
``totalElements`` / ``totalPages`` / ``number`` / ``size``). Spring Data's newer
stable shape nests the counters under ``page``; both parse to the same model so
a server-side switch does not break the SDK.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import Field, model_validator

from danipa.models._base import _ApiModel, _ResponseModel

T = TypeVar("T", bound=_ApiModel)

_PAGE_COUNTERS = ("size", "number", "totalElements", "totalPages")


class Page(_ResponseModel, Generic[T]):
    """One page of results. ``number`` is zero-based."""

    content: list[T] = Field(default_factory=list)
    total_elements: int = 0
    total_pages: int = 0
    number: int = 0
    """Zero-based index of this page."""
    size: int = 0
    """Requested page size (1 to 200)."""

    @model_validator(mode="before")
    @classmethod
    def _lift_nested_page(cls, data: Any) -> Any:
        if isinstance(data, dict) and isinstance(data.get("page"), dict):
            lifted = {k: v for k, v in data.items() if k != "page"}
            for key in _PAGE_COUNTERS:
                if key in data["page"] and key not in lifted:
                    lifted[key] = data["page"][key]
            return lifted
        return data

    @property
    def has_next(self) -> bool:
        """``True`` when a later page exists."""
        return self.number + 1 < self.total_pages
