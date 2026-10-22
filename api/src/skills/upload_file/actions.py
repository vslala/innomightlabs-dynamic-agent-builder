from __future__ import annotations

import asyncio
from typing import Any

from pydantic import ValidationError

from src.artifacts.models import ArtifactSource
from src.artifacts.service import ArtifactService, run_artifact_holder
from src.skills.upload_file.mime import infer_mime_type
from src.skills.upload_file.models import UploadFileRequest, max_bytes_for
from src.skills.upload_file.sources import source_for
from src.skills.upload_file.validators import ArtifactValidatorRegistry


async def upload_file(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    del config
    request = _validate_request(arguments)
    account_id, user_id = await asyncio.to_thread(run_artifact_holder, context)
    content = await source_for(request).load(request, context, max_bytes_for(request.artifact_type))
    try:
        content = ArtifactValidatorRegistry().validator_for(request.artifact_type).validate(request, content)
        mime_type = infer_mime_type(request.artifact_type, request.filename, request.mime_type)
        artifact = await asyncio.to_thread(
            ArtifactService().create_artifact,
            account_id=account_id,
            user_id=user_id,
            artifact_type=request.artifact_type,
            title=request.title,
            filename=request.filename,
            mime_type=mime_type,
            body=content.file,
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
    finally:
        content.close()
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


def _context_value(context: dict[str, Any], key: str) -> str | None:
    value = str(context.get(key) or "").strip()
    return value or None
