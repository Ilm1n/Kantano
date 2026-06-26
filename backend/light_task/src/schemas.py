from typing import Any

from pydantic import BaseModel, ConfigDict, field_validator
from pydantic.alias_generators import to_camel


class BaseSchema(BaseModel):
    model_config = ConfigDict(
        from_attributes=True,
        alias_generator=to_camel,
        populate_by_name=True,
        use_enum_values=True,
    )

    @field_validator("*", mode="before")
    @classmethod
    def sanitize_strings(cls, v: Any) -> Any:
        if isinstance(v, str):
            if "\x00" in v:
                raise ValueError("Null bytes are not allowed in strings")
            v = v.strip()
        return v
