from __future__ import annotations

import io

import pytest
from PIL import Image

from src.vision.errors import ImageInputError
from src.vision.images import normalise_image
from src.vision.models import ImageInputLimits

LIMITS = ImageInputLimits(max_bytes=200_000, max_images_per_message=4, max_edge_px=200, max_pixels=1_000_000)


def _image_bytes(fmt: str, size: tuple[int, int] = (50, 30), mode: str = "RGB", **save_args) -> bytes:
    out = io.BytesIO()
    Image.new(mode, size, "red").save(out, fmt, **save_args)
    return out.getvalue()


@pytest.mark.parametrize(
    ("fmt", "mime"),
    [("PNG", "image/png"), ("JPEG", "image/jpeg"), ("WEBP", "image/webp")],
)
def test_supported_formats_pass_through_in_their_own_format(fmt: str, mime: str) -> None:
    image = normalise_image(_image_bytes(fmt), LIMITS)

    assert image.mime_type == mime
    assert (image.width, image.height) == (50, 30)
    assert Image.open(io.BytesIO(image.body)).format == fmt


def test_a_gif_becomes_a_png_of_its_first_frame() -> None:
    frames = [Image.new("P", (20, 20), color) for color in (1, 2)]
    out = io.BytesIO()
    frames[0].save(out, "GIF", save_all=True, append_images=frames[1:])

    image = normalise_image(out.getvalue(), LIMITS)

    assert image.mime_type == "image/png"
    assert Image.open(io.BytesIO(image.body)).format == "PNG"


def test_a_file_that_is_not_an_image_is_unreadable_whatever_its_name() -> None:
    with pytest.raises(ImageInputError) as refused:
        normalise_image(b"%PDF-1.7 not an image at all", LIMITS)

    assert refused.value.code == "image_unreadable"


def test_an_image_format_we_do_not_support_is_refused() -> None:
    with pytest.raises(ImageInputError) as refused:
        normalise_image(_image_bytes("BMP"), LIMITS)

    assert refused.value.code == "image_type_unsupported"


def test_an_oversized_upload_is_refused_before_decoding() -> None:
    with pytest.raises(ImageInputError) as refused:
        normalise_image(b"x" * (LIMITS.max_bytes + 1), LIMITS)

    assert (refused.value.code, refused.value.status_code) == ("image_too_large", 413)
    assert "MB or smaller" in refused.value.message


def test_too_many_pixels_is_refused() -> None:
    limits = LIMITS.model_copy(update={"max_pixels": 1000})

    with pytest.raises(ImageInputError) as refused:
        normalise_image(_image_bytes("PNG", (100, 100)), limits)

    assert refused.value.code == "image_too_large"


def test_a_large_image_is_downscaled_to_the_longest_edge_limit() -> None:
    image = normalise_image(_image_bytes("PNG", (800, 400)), LIMITS)

    assert (image.width, image.height) == (200, 100)


def test_exif_is_dropped_and_the_orientation_applied() -> None:
    source = Image.new("RGB", (60, 20), "blue")
    exif = Image.Exif()
    exif[0x0112] = 6  # rotated 90 degrees: displays upright as 20 wide, 60 tall
    exif[0x8825] = {1: "N"}  # GPS IFD
    out = io.BytesIO()
    source.save(out, "JPEG", exif=exif)

    image = normalise_image(out.getvalue(), LIMITS)

    assert (image.width, image.height) == (20, 60)
    assert not Image.open(io.BytesIO(image.body)).getexif()
