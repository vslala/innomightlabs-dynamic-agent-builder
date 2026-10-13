"""Turning whatever was uploaded into an image we are willing to store and send to a model.

Checking the content type alone would let anything through, so the bytes are decoded. Re-encoding drops EXIF
(phone photos carry GPS coordinates) and downscaling keeps a request of several images under every provider's
limits.
"""

from __future__ import annotations

import io
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from src.vision.errors import ImageInputError
from src.vision.models import ALLOWED_FORMATS, ImageInputLimits

JPEG_QUALITY = 90


@dataclass(frozen=True)
class NormalisedImage:
    body: bytes
    mime_type: str
    extension: str
    width: int
    height: int


def normalise_image(raw: bytes, limits: ImageInputLimits) -> NormalisedImage:
    """The bytes we store and send: a verified, upright, metadata-free image within the limits."""
    if len(raw) > limits.max_bytes:
        raise _too_large(limits)

    image = _decode(raw, limits)
    source_format = str(image.format)
    image = ImageOps.exif_transpose(image)
    image.thumbnail((limits.max_edge_px, limits.max_edge_px))

    output_format = "PNG" if source_format == "GIF" else source_format  # providers read a GIF's first frame only
    body = _encode(image, output_format)
    if len(body) > limits.max_bytes:
        raise _too_large(limits)
    return NormalisedImage(
        body=body,
        mime_type=ALLOWED_FORMATS[output_format],
        extension=output_format.lower(),
        width=image.width,
        height=image.height,
    )


def _decode(raw: bytes, limits: ImageInputLimits) -> Image.Image:
    try:
        with Image.open(io.BytesIO(raw)) as probe:
            probe.verify()
        image = Image.open(io.BytesIO(raw))
        if image.format not in ALLOWED_FORMATS:
            raise ImageInputError("image_type_unsupported", "Only PNG, JPEG, WebP and GIF images are supported.")
        if image.width * image.height > limits.max_pixels:  # read from the header, before any pixels are decoded
            raise ImageInputError("image_too_large", "That image has too many pixels.", status_code=413)
        image.load()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError, SyntaxError) as exc:
        raise ImageInputError("image_unreadable", "That file isn't a readable PNG, JPEG, WebP or GIF image.") from exc
    return image


def _encode(image: Image.Image, output_format: str) -> bytes:
    out = io.BytesIO()
    if output_format == "JPEG":
        image.convert("RGB").save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    elif output_format == "WEBP":
        image.save(out, "WEBP", quality=JPEG_QUALITY)
    else:
        image.convert("RGBA" if image.mode not in ("RGB", "RGBA", "L", "LA") else image.mode).save(
            out, "PNG", optimize=True
        )
    return out.getvalue()


def _too_large(limits: ImageInputLimits) -> ImageInputError:
    return ImageInputError(
        "image_too_large", f"Images must be {limits.max_bytes // (1024 * 1024)}MB or smaller.", status_code=413
    )
