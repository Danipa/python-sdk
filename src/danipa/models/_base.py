"""Base Pydantic config shared by every SDK model.

Python attributes are snake_case; the wire format is camelCase (``to_camel``).
Both spellings are accepted on construction. Unknown response fields are
ignored so a new server field never breaks an older SDK.

Money fields are :class:`decimal.Decimal`. The server writes ``BigDecimal`` as a
JSON number; the SDK parses JSON numbers straight to ``Decimal`` (no float
round-trip) and sends money as a decimal string.
"""

from __future__ import annotations

from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, PrivateAttr
from pydantic.alias_generators import to_camel

from danipa.http import ResponseMeta


class _ApiModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
        extra="ignore",
    )

    def _wire(self) -> dict[str, Any]:
        """The camelCase JSON body for a request model (money as strings, ``None`` dropped)."""
        return self.model_dump(mode="json", by_alias=True, exclude_none=True)


class _ResponseModel(_ApiModel):
    _response_meta: ResponseMeta | None = PrivateAttr(default=None)

    @property
    def response_meta(self) -> ResponseMeta | None:
        """HTTP metadata for the call that returned this object.

        Includes the ``Idempotency-Key`` the SDK sent and whether the server
        answered from its idempotency cache (``X-Idempotent-Replay: true``).
        """
        return self._response_meta


class _OpenEnum(str, Enum):
    """A string enum that maps any value the SDK does not know to ``UNKNOWN``.

    A status the server adds later therefore parses instead of raising.
    """

    @classmethod
    def _missing_(cls, value: object) -> Any:
        return cls.__members__.get("UNKNOWN")
