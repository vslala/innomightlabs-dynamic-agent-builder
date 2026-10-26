from __future__ import annotations

import io
from pathlib import PurePath
from typing import Protocol

from PIL import Image, UnidentifiedImageError

from src.artifacts.models import ArtifactType
from src.skills.league_insights_report.html_safety import extract_html_document, validate_safe_report_html
from src.skills.upload_file.content import UploadContent
from src.skills.upload_file.mime import IMAGE_FORMATS, VIDEO_MIME_TYPES
from src.skills.upload_file.models import UploadFileRequest


class ArtifactContentValidator(Protocol):
    def validate(self, request: UploadFileRequest, content: UploadContent) -> UploadContent:
        ...


class HtmlArtifactValidator:
    def validate(self, request: UploadFileRequest, content: UploadContent) -> UploadContent:
        del request
        try:
            html = extract_html_document(content.read_all().decode("utf-8"))
        except UnicodeDecodeError as exc:
            raise ValueError("An HTML report must be UTF-8 text") from exc
        validate_safe_report_html(html)
        content.close()
        return UploadContent.from_bytes(html.encode("utf-8"))


class VideoArtifactValidator:
    """A video is what its name and its first bytes both say it is: MP4 and MOV files open with an `ftyp` box, WebM
    with the EBML marker."""

    def validate(self, request: UploadFileRequest, content: UploadContent) -> UploadContent:
        suffix = PurePath(request.filename).suffix.lower()
        if suffix not in VIDEO_MIME_TYPES:
            raise ValueError(f"A video filename must end with {', '.join(sorted(VIDEO_MIME_TYPES))}")
        head = content.head(12)
        is_webm = head.startswith(b"\x1a\x45\xdf\xa3")
        is_isobmff = head[4:8] == b"ftyp"
        if (suffix == ".webm") != is_webm or (suffix != ".webm" and not is_isobmff):
            raise ValueError(f"The file is not a valid {suffix[1:]} video")
        return content


class ImageArtifactValidator:
    """A picture whose bytes are the raster format its name says: what a post or a page can show as it is."""

    def validate(self, request: UploadFileRequest, content: UploadContent) -> UploadContent:
        suffix = PurePath(request.filename).suffix.lower()
        if suffix == ".svg":
            raise ValueError(
                "An SVG isn't an image networks accept. Render it to PNG first (for example with a browser_studio "
                "screenshot of a page showing it), then upload the PNG."
            )
        if suffix not in IMAGE_FORMATS:
            raise ValueError(f"An image filename must end with {', '.join(sorted(IMAGE_FORMATS))}")
        try:
            with Image.open(io.BytesIO(content.read_all())) as image:
                image.verify()
                actual = image.format
        except (UnidentifiedImageError, OSError, Image.DecompressionBombError) as exc:
            raise ValueError("The file is not an image that can be read") from exc
        if actual != IMAGE_FORMATS[suffix]:
            raise ValueError(f"The file is a {actual} image, not {suffix[1:]}: give it the matching extension")
        return content


class NoopArtifactValidator:
    def validate(self, request: UploadFileRequest, content: UploadContent) -> UploadContent:
        del request
        return content


class ArtifactValidatorRegistry:
    def __init__(self) -> None:
        self._noop = NoopArtifactValidator()
        self._validators: dict[str, ArtifactContentValidator] = {
            "html_report": HtmlArtifactValidator(),
            "video": VideoArtifactValidator(),
            "image": ImageArtifactValidator(),
        }

    def validator_for(self, artifact_type: ArtifactType) -> ArtifactContentValidator:
        return self._validators.get(str(artifact_type), self._noop)
