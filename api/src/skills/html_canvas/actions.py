from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from src.artifacts.models import ArtifactSource
from src.artifacts.service import ArtifactService
from src.skills.html_canvas.models import CANVAS_ARTIFACT_FILENAME, RenderCanvasRequest

_EXTERNAL_REFERENCE_RE = re.compile(
    r"""(?:src|href)\s*=\s*['"]https?://|@import\s+url\(\s*['"]?https?://|"""
    r"""fetch\(\s*['"]https?://|XMLHttpRequest|WebSocket\(\s*['"]wss?://""",
    re.IGNORECASE,
)


def render_canvas(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del config
    request = _validate_request(arguments)

    if _EXTERNAL_REFERENCE_RE.search(request.html):
        return {
            "ok": False,
            "message": (
                "The canvas HTML references an external http(s)/ws(s) resource. Canvases must be "
                "fully self-contained (inline <style>/<script> only) -- retry without external references."
            ),
        }

    owner_email = _required_context(context, "owner_email")
    artifact = ArtifactService().create_artifact(
        owner_email=owner_email,
        artifact_type="canvas",
        title=request.title,
        filename=CANVAS_ARTIFACT_FILENAME,
        mime_type="text/html",
        body=request.html.encode("utf-8"),
        source=ArtifactSource(
            skill_id="html_canvas",
            agent_id=_context_value(context, "agent_id"),
            conversation_id=_context_value(context, "conversation_id"),
            message_id=_context_value(context, "user_message_id"),
            metadata={"caption": request.caption} if request.caption else {},
        ),
    )
    return {
        "ok": True,
        "type": "canvas_artifact",
        "artifact_id": artifact.artifact_id,
        "title": artifact.title,
        "caption": request.caption,
        "mime_type": artifact.mime_type,
        "size_bytes": artifact.size_bytes,
        "view_url": artifact.view_url,
    }


def _validate_request(arguments: dict[str, Any]) -> RenderCanvasRequest:
    try:
        return RenderCanvasRequest.model_validate(arguments)
    except ValidationError as exc:
        raise ValueError(f"Invalid html_canvas render_canvas arguments: {exc}") from exc


def _required_context(context: dict[str, Any], key: str) -> str:
    value = str(context.get(key) or "").strip()
    if not value:
        raise ValueError(f"Missing skill runtime context: {key}")
    return value


def _context_value(context: dict[str, Any], key: str) -> str | None:
    value = str(context.get(key) or "").strip()
    return value or None
