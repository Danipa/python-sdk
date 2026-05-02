"""Base Pydantic config shared by every SDK model.

Python attributes are snake_case (idiomatic). The wire format is camelCase —
:class:`pydantic.alias_generators.to_camel` handles the conversion. Both
spellings are accepted on construction (``populate_by_name=True``) and
serialization defaults to camelCase via ``model.model_dump(by_alias=True)``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class _ApiModel(BaseModel):
    model_config = ConfigDict(
        populate_by_name=True,
        alias_generator=to_camel,
        extra="ignore",
    )
