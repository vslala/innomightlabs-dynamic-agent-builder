from __future__ import annotations

import re
from typing import Annotated

from pydantic import BaseModel, ConfigDict, StringConstraints, model_validator

NonEmptyString = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
GOOGLE_DOC_MIME_TYPE = "application/vnd.google-apps.document"
FOLDER_MIME_TYPE = "application/vnd.google-apps.folder"
TEXT_APPLICATION_MIME_TYPES = {
    "application/json",
    "application/xml",
    "application/javascript",
    "application/x-javascript",
    "application/rtf",
    "application/x-sh",
    "application/sql",
}


def supports_text_content(mime_type: str) -> bool:
    return bool(re.fullmatch(r"text/[a-zA-Z0-9!#$&^_.+-]+", mime_type)) or mime_type in TEXT_APPLICATION_MIME_TYPES


class CreateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: NonEmptyString
    mime_type: NonEmptyString = "text/plain"
    description: str | None = None
    parent_folder_id: NonEmptyString | None = None
    content: str | None = None

    @model_validator(mode="after")
    def validate_content_type(self) -> CreateRequest:
        if self.mime_type == FOLDER_MIME_TYPE:
            if self.content is not None:
                raise ValueError("Folders cannot have content")
        elif self.mime_type != GOOGLE_DOC_MIME_TYPE and not supports_text_content(self.mime_type):
            raise ValueError("Create supports text-like files, Google Docs (plain-text import), and folders only")
        return self


class UpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    file_id: NonEmptyString
    name: NonEmptyString | None = None
    description: str | None = None
    content: str | None = None

    @model_validator(mode="after")
    def validate_changes(self) -> UpdateRequest:
        changes = self.model_fields_set - {"file_id"}
        if not changes:
            raise ValueError("Update requires name, description, or content")
        if any(getattr(self, field) is None for field in changes):
            raise ValueError("Update fields cannot be null; use an empty string to clear description or content")
        return self
