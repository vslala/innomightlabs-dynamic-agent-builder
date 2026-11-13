"""Drawing: what a provider's image generator takes and gives back, whichever way the provider draws."""

from __future__ import annotations

import struct
from collections.abc import AsyncIterator
from dataclasses import dataclass
from typing import Any, Literal, Protocol


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


class ImageGenerator(Protocol):
    """How one provider draws. Which of its models draw is its catalog's answer."""

    async def generate(
        self, *, prompt: str, credentials: dict[str, Any], model: str, options: ImageGenerationOptions
    ) -> list[GeneratedImageBytes]: ...

    def stream_generate(
        self, *, prompt: str, credentials: dict[str, Any], model: str, options: ImageGenerationOptions
    ) -> AsyncIterator[ImageGenerationStreamEvent]: ...


@dataclass(frozen=True)
class ImageDimensions:
    width: int | None
    height: int | None


def mime_type_for_format(output_format: str) -> str:
    normalized = output_format.lower().lstrip(".")
    if normalized in {"jpg", "jpeg"}:
        return "image/jpeg"
    if normalized == "webp":
        return "image/webp"
    return "image/png"


def image_dimensions(data: bytes, output_format: str) -> ImageDimensions:
    """Read from a PNG's header; other formats are stored without dimensions."""
    normalized = output_format.lower().lstrip(".")
    if normalized == "png" and data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return ImageDimensions(width=int(width), height=int(height))
    return ImageDimensions(width=None, height=None)
