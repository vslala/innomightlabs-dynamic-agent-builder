"""Fitting an image to what a network accepts. One source image becomes one rendition per network, so a network's size
rules never leak into the others."""

from __future__ import annotations

import io
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
    """An upright JPEG, flattened onto white (JPEG has no transparency), within the network's side and size limits."""
    try:
        with Image.open(io.BytesIO(source.data)) as opened:
            image = ImageOps.exif_transpose(opened)
            image.load()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as error:
        raise PublishError(PublishErrorKind.REJECTED, "One of the images could not be read") from error

    image.thumbnail((limits.max_image_side, limits.max_image_side))
    flat = Image.new("RGB", image.size, "white")
    rgba = image.convert("RGBA")
    flat.paste(rgba, mask=rgba.getchannel("A"))

    for quality in QUALITY_STEPS:
        out = io.BytesIO()
        flat.save(out, "JPEG", quality=quality, optimize=True)
        if out.tell() <= limits.max_image_bytes:
            return PreparedImage(data=out.getvalue(), mime_type="image/jpeg", alt_text=source.alt_text)
    raise PublishError(PublishErrorKind.REJECTED, "One of the images is too large for this network")
