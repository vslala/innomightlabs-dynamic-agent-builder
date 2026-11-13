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
    """How one provider draws. Which of its models draw is its catalog's answer (`ModelCapability.IMAGE_GENERATION`)."""

    def draw(
        self, *, prompt: str, credentials: dict[str, Any], model: str, options: ImageGenerationOptions
    ) -> AsyncIterator[ImageGenerationStreamEvent]:
        """`started`, `generating`, any `partial` frames, one `image` per picture, `completed`. A vendor that can't
        stream sends no `partial` events."""
        ...


async def collect_images(events: AsyncIterator[ImageGenerationStreamEvent]) -> list[GeneratedImageBytes]:
    """The pictures from a draw, for callers that don't stream (the widget, `/v1`)."""
    images = [event.image async for event in events if event.kind == "image" and event.image]
    if not images:
        raise RuntimeError("Image generation completed without image output")
    return images


#: The image skill speaks OpenAI's sizes; vendors that take an aspect ratio instead (xAI, Gemini) are given this.
ASPECT_RATIOS = {"1024x1024": "1:1", "1536x1024": "3:2", "1024x1536": "2:3"}


def aspect_ratio_of(size: str | None) -> str | None:
    """The aspect ratio of one of the skill's sizes, or None for "auto" or a size it doesn't name."""
    return ASPECT_RATIOS.get(size or "")


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


def image_format_of(data: bytes) -> str:
    """The format the bytes are in, from their signature: a vendor's word for it isn't always what it sent."""
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    return "png"


def image_dimensions(data: bytes, output_format: str) -> ImageDimensions:
    """Read from the image's header; a format without a reader here is stored without dimensions."""
    reader = _DIMENSION_READERS.get(output_format.lower().lstrip("."))
    return (reader(data) if reader else None) or ImageDimensions(width=None, height=None)


def generated_image(
    data: bytes, *, prompt: str, provider_key: str, metadata: dict[str, Any] | None = None, **details: Any
) -> GeneratedImageBytes:
    """A picture a vendor sent as plain bytes, described from the bytes themselves. `details` are the rest of
    `GeneratedImageBytes` (`revised_prompt`, `quality`); `metadata` is recorded beside the provider's key."""
    output_format = image_format_of(data)
    dimensions = image_dimensions(data, output_format)
    return GeneratedImageBytes(
        data=data,
        output_format=output_format,
        mime_type=mime_type_for_format(output_format),
        prompt=prompt,
        width=dimensions.width,
        height=dimensions.height,
        provider_metadata={"provider": provider_key, **(metadata or {})},
        **details,
    )


def _png_dimensions(data: bytes) -> ImageDimensions | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) >= 24:
        width, height = struct.unpack(">II", data[16:24])
        return ImageDimensions(width=int(width), height=int(height))
    return None


#: JPEG start-of-frame markers (baseline, extended, progressive, lossless): they carry the height and width.
_JPEG_FRAME_MARKERS = frozenset({0xC0, 0xC1, 0xC2, 0xC3})


def _jpeg_dimensions(data: bytes) -> ImageDimensions | None:
    """Walk the marker segments to the first start-of-frame."""
    position = 2
    while position + 4 <= len(data) and data[position] == 0xFF:
        marker = data[position + 1]
        length = int.from_bytes(data[position + 2 : position + 4], "big")
        if marker in _JPEG_FRAME_MARKERS and position + 9 <= len(data):
            height, width = struct.unpack(">HH", data[position + 5 : position + 9])
            return ImageDimensions(width=int(width), height=int(height))
        position += 2 + length
    return None


_DIMENSION_READERS = {"png": _png_dimensions, "jpeg": _jpeg_dimensions, "jpg": _jpeg_dimensions}
