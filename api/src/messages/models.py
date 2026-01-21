"""
Message models for the messages module.
"""

import os
from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, Field, field_validator

# Allowed file extensions for attachments
ALLOWED_EXTENSIONS = {
    ".txt", ".md", ".csv", ".json",
    ".py", ".js", ".ts", ".tsx", ".jsx",
    ".java", ".go", ".rs", ".rb", ".php",
    ".html", ".css", ".xml", ".yaml", ".yml",
    ".sh", ".sql", ".c", ".cpp", ".h",
}

MAX_FILE_SIZE = 100 * 1024  # 100KB per file
MAX_TOTAL_SIZE = 250 * 1024  # 250KB total
MAX_FILES = 5


class Attachment(BaseModel):
    """File attachment metadata and content."""

    filename: str
    content: str
    size: int  # Size in bytes

    @field_validator("filename")
    @classmethod
    def validate_filename(cls, v: str) -> str:
        ext = os.path.splitext(v)[1].lower()
        if ext not in ALLOWED_EXTENSIONS:
            raise ValueError(f"File type '{ext}' not allowed")
        return v

    @field_validator("size")
    @classmethod
    def validate_size(cls, v: int) -> int:
        if v > MAX_FILE_SIZE:
            raise ValueError(f"File exceeds {MAX_FILE_SIZE // 1024}KB limit")
        return v


class AttachmentResponse(BaseModel):
    """Attachment info returned to frontend (excludes content for list views)."""

    filename: str
    size: int


class MessageResponse(BaseModel):
    """Response model for message."""

    message_id: str
    conversation_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    attachments: list[AttachmentResponse] = Field(default_factory=list)
    created_at: datetime


class Message(BaseModel):
    """Domain model for message with DynamoDB serialization."""

    message_id: str = Field(default_factory=lambda: str(uuid4()))
    conversation_id: str
    created_by: str = ""
    role: Literal["user", "assistant", "system"]
    content: str
    attachments: list[Attachment] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def pk(self) -> str:
        """Partition key: CONVERSATION#{conversation_id} - allows querying all messages in a conversation."""
        return f"CONVERSATION#{self.conversation_id}"

    @property
    def sk(self) -> str:
        """Sort key: MESSAGE#{timestamp}#{message_id} - chronological ordering within conversation."""
        return f"MESSAGE#{self.created_at.isoformat()}#{self.message_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        """Convert to DynamoDB item format."""
        item: dict[str, Any] = {
            "pk": self.pk,
            "sk": self.sk,
            "message_id": self.message_id,
            "conversation_id": self.conversation_id,
            "created_by": self.created_by,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "entity_type": "Message",
        }
        if self.attachments:
            item["attachments"] = [att.model_dump() for att in self.attachments]
        return item

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "Message":
        """Create Message from DynamoDB item."""
        attachments = [
            Attachment(**att) for att in item.get("attachments", [])
        ]
        return cls(
            message_id=item["message_id"],
            conversation_id=item["conversation_id"],
            created_by=item.get("created_by", ""),
            role=item["role"],
            content=item["content"],
            attachments=attachments,
            created_at=datetime.fromisoformat(item["created_at"]),
        )

    def to_response(self) -> MessageResponse:
        """Convert to response model."""
        return MessageResponse(
            message_id=self.message_id,
            conversation_id=self.conversation_id,
            role=self.role,
            content=self.content,
            attachments=[
                AttachmentResponse(filename=att.filename, size=att.size)
                for att in self.attachments
            ],
            created_at=self.created_at,
        )
