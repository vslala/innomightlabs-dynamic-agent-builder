from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from src.artifacts.models import ArtifactSource
from src.artifacts.service import ArtifactService
from src.skills.upload_file.mime import infer_mime_type
from src.skills.upload_file.models import UploadFileRequest
from src.skills.upload_file.validators import ArtifactValidatorRegistry


def upload_file(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del config
    request = _validate_request(arguments)
    owner_email = _required_context(context, "owner_email")
    body = request.to_body_bytes()
    body = ArtifactValidatorRegistry().validator_for(request.artifact_type).validate(request, body)
    mime_type = infer_mime_type(request.artifact_type, request.filename, request.mime_type)

    artifact = ArtifactService().create_artifact(
        owner_email=owner_email,
        artifact_type=request.artifact_type,
        title=request.title,
        filename=request.filename,
        mime_type=mime_type,
        body=body,
        source=ArtifactSource(
            skill_id="upload_file",
            agent_id=_context_value(context, "agent_id"),
            automation_id=_context_value(context, "automation_id"),
            automation_run_id=_context_value(context, "automation_run_id"),
            automation_node_id=_context_value(context, "automation_node_id"),
            conversation_id=_context_value(context, "conversation_id"),
            message_id=_context_value(context, "user_message_id"),
            metadata=request.metadata,
        ),
    )
    return {
        "ok": True,
        "artifact_id": artifact.artifact_id,
        "artifact_type": artifact.artifact_type,
        "title": artifact.title,
        "filename": artifact.filename,
        "mime_type": artifact.mime_type,
        "size_bytes": artifact.size_bytes,
        "url": artifact.view_url or artifact.url,
        "view_url": artifact.view_url,
        "download_url": artifact.url,
    }


def _validate_request(arguments: dict[str, Any]) -> UploadFileRequest:
    try:
        return UploadFileRequest.model_validate(arguments)
    except ValidationError as exc:
        raise ValueError(f"Invalid Upload File arguments: {exc}") from exc


def _required_context(context: dict[str, Any], key: str) -> str:
    value = str(context.get(key) or "").strip()
    if not value:
        raise ValueError(f"Missing skill runtime context: {key}")
    return value


def _context_value(context: dict[str, Any], key: str) -> str | None:
    value = str(context.get(key) or "").strip()
    return value or None
