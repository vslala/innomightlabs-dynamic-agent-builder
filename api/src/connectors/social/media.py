"""Fitting an image to what a network accepts. One source image becomes one rendition per network, so a network's size
rules never leak into the others."""

from __future__ import annotations

import io
import math
from dataclasses import dataclass

from PIL import Image, ImageOps, UnidentifiedImageError

from src.connectors.social.networks.base import NetworkLimits, PreparedImage, PublishError, PublishErrorKind

#: JPEG quality is stepped down from the first to the last until the file fits
QUALITY_STEPS = (90, 80, 70, 60)


@dataclass(frozen=True)
class SourceImage:
    data: bytes
    alt_text: str = ""


def prepare(source: SourceImage, limits: NetworkLimits) -> PreparedImage:
    """An upright JPEG, flattened onto white (JPEG has no transparency), within the network's side and size limits,
    and padded onto white into the network's aspect range (Instagram) rather than cropped."""
    try:
        with Image.open(io.BytesIO(source.data)) as opened:
            image = ImageOps.exif_transpose(opened)
            image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise PublishError(PublishErrorKind.REJECTED, "One of the images could not be read") from error

    image.thumbnail((limits.max_image_side, limits.max_image_side))
    rgba = image.convert("RGBA")
    flat = Image.new("RGB", _padded_size(rgba.size, limits.aspect_range), "white")
    flat.paste(rgba, ((flat.width - rgba.width) // 2, (flat.height - rgba.height) // 2), mask=rgba.getchannel("A"))
    flat.thumbnail((limits.max_image_side, limits.max_image_side))

    for quality in QUALITY_STEPS:
        out = io.BytesIO()
        flat.save(out, "JPEG", quality=quality, optimize=True)
        if out.tell() <= limits.max_image_bytes:
            return PreparedImage(data=out.getvalue(), mime_type="image/jpeg", alt_text=source.alt_text)
    raise PublishError(PublishErrorKind.REJECTED, "One of the images is too large for this network")


def _padded_size(size: tuple[int, int], aspect_range: tuple[float, float] | None) -> tuple[int, int]:
    """The smallest canvas around `size` whose width / height is within `aspect_range`: a tall phone screenshot gets
    white bars at the sides, a wide panorama above and below."""
    width, height = size
    if aspect_range is None:
        return size
    narrowest, widest = aspect_range
    if width / height < narrowest:
        return math.ceil(height * narrowest), height
    if width / height > widest:
        return width, math.ceil(width / widest)
    return size
