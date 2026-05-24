"""Models for agent image generation."""

from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, Field


class GenerateImageRequest(BaseModel):
    """Request to explicitly generate an image with an agent."""

    prompt: str = Field(min_length=1, max_length=4000)
    size: str | None = Field(default=None, max_length=32)
    quality: str | None = Field(default=None, max_length=32)
    output_format: Literal["png", "jpeg", "webp"] = "png"


class GeneratedImageResponse(BaseModel):
    """Generated image response item."""

    image_id: str
    url: str | None = None
    s3_key: str
    filename: str
    mime_type: str
    width: int | None = None
    height: int | None = None
    size_bytes: int
    prompt: str
    revised_prompt: str | None = None


class GenerateImageResponse(BaseModel):
    """Response for explicit agent image generation."""

    agent_id: str
    conversation_id: str
    user_message_id: str
    assistant_message_id: str
    images: list[GeneratedImageResponse]


@dataclass(frozen=True)
class ImageGenerationOptions:
    """Provider-neutral image generation options."""

    size: str | None = None
    quality: str | None = None
    output_format: str = "png"


@dataclass(frozen=True)
class GeneratedImageBytes:
    """Raw image result from a provider before storage."""

    data: bytes
    output_format: str
    mime_type: str
    prompt: str
    revised_prompt: str | None = None
    width: int | None = None
    height: int | None = None
    quality: str | None = None
    background: str | None = None
    provider_metadata: dict[str, Any] | None = None


@dataclass(frozen=True)
class ImageGenerationStreamEvent:
    """Provider stream event for image generation."""

    kind: Literal["started", "generating", "partial", "image", "completed"]
    image_b64: str | None = None
    image: GeneratedImageBytes | None = None
    output_format: str | None = None
    mime_type: str | None = None
    width: int | None = None
    height: int | None = None
    quality: str | None = None
    message: str = ""
