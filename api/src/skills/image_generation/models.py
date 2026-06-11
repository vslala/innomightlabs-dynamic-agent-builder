from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, Field, StringConstraints, field_validator


class GenerateImageActionRequest(BaseModel):
    prompt: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=4000)]
    size: str | None = Field(default=None, max_length=32)
    quality: str | None = Field(default=None, max_length=32)
    output_format: Literal["png", "jpeg", "webp"] = "png"

    @field_validator("size", "quality")
    @classmethod
    def normalize_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        return cleaned or None
