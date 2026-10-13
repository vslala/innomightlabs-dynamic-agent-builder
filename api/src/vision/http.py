"""What the three surfaces' image routes (dashboard, widget, `/v1`) share: reading an upload and serving a stored image."""

from __future__ import annotations

from fastapi import UploadFile
from fastapi.responses import Response

from src.agents.image_generation.storage import StoredImage
from src.config import settings

def dashboard_image_url(conversation_id: str, image_id: str) -> str:
    return f"{settings.api_base_url.rstrip('/')}/conversations/{conversation_id}/images/{image_id}"


#: What a browser may cache an image for: it is private to the signed-in viewer.
CACHE_CONTROL = "private, max-age=300"


async def read_image_upload(file: UploadFile) -> bytes:
    """The uploaded bytes. One byte past the limit is read so an oversized file is refused, not buffered whole."""
    return await file.read(settings.vision_max_image_bytes + 1)


def image_response(stored: StoredImage) -> Response:
    return Response(
        content=stored.body,
        media_type=stored.content_type,
        headers={"Cache-Control": CACHE_CONTROL, "X-Content-Type-Options": "nosniff"},
    )
