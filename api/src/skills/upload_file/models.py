from __future__ import annotations

import base64
import binascii
import json
from typing import Any

from pydantic import BaseModel, Field, model_validator

from src.artifacts.models import ArtifactType

MAX_ARTIFACT_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_VIDEO_UPLOAD_BYTES = 100 * 1024 * 1024
MAX_METADATA_JSON_BYTES = 8 * 1024
UPLOADABLE_ARTIFACT_TYPES = {"html_report", "csv", "markdown", "json", "text", "code", "file", "video"}
#: Types too large or not text to send in a message: they are uploaded from a file in the workspace.
WORKSPACE_ONLY_ARTIFACT_TYPES = {"video"}


def max_bytes_for(artifact_type: str) -> int:
    return MAX_VIDEO_UPLOAD_BYTES if artifact_type == "video" else MAX_ARTIFACT_UPLOAD_BYTES


class UploadFileRequest(BaseModel):
    artifact_type: ArtifactType
    title: str
    filename: str
    mime_type: str | None = None
    text_content: str | None = None
    base64_content: str | None = None
    workspace_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def normalize(self) -> "UploadFileRequest":
        self.title = self.title.strip()
        self.filename = self.filename.strip()
        self.mime_type = self.mime_type.strip() if self.mime_type else None
        self.workspace_path = self.workspace_path.strip() if self.workspace_path else None
        if self.artifact_type not in UPLOADABLE_ARTIFACT_TYPES:
            raise ValueError("artifact_type is not supported by upload_file")
        if not self.title:
            raise ValueError("title is required")
        if not self.filename:
            raise ValueError("filename is required")
        provided = [value is not None for value in (self.text_content, self.base64_content, self.workspace_path)]
        if sum(provided) != 1:
            raise ValueError("Provide exactly one of text_content, base64_content or workspace_path")
        if self.artifact_type in WORKSPACE_ONLY_ARTIFACT_TYPES and self.workspace_path is None:
            raise ValueError(f"{self.artifact_type} files are uploaded from the workspace: provide workspace_path")
        _validate_metadata_size(self.metadata)
        if self.workspace_path is None and len(self.to_body_bytes()) > MAX_ARTIFACT_UPLOAD_BYTES:
            raise ValueError("File content exceeds the 10 MB upload limit")
        return self

    def to_body_bytes(self) -> bytes:
        """The content sent in the request itself (not a workspace file)."""
        if self.text_content is not None:
            return self.text_content.encode("utf-8")
        try:
            body = base64.b64decode(str(self.base64_content or ""), validate=True)
        except (binascii.Error, ValueError) as exc:
            raise ValueError("base64_content must be valid base64") from exc
        try:
            body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Decoded base64_content must be UTF-8 text for upload_file v1") from exc
        return body


def _validate_metadata_size(metadata: dict[str, Any]) -> None:
    try:
        encoded = json.dumps(metadata, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise ValueError("metadata must be JSON serializable") from exc
    if len(encoded) > MAX_METADATA_JSON_BYTES:
        raise ValueError("metadata exceeds the 8 KB limit")
