"""
Message models for the messages module.
"""

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class MessageResponse(BaseModel):
    """Response model for message."""

    message_id: str
    conversation_id: str
    role: Literal["user", "assistant", "system"]
    content: str
    created_at: datetime


class Message(BaseModel):
    """Domain model for message with DynamoDB serialization."""

    message_id: str = Field(default_factory=lambda: str(uuid4()))
    conversation_id: str
    role: Literal["user", "assistant", "system"]
    content: str
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
        return {
            "pk": self.pk,
            "sk": self.sk,
            "message_id": self.message_id,
            "conversation_id": self.conversation_id,
            "role": self.role,
            "content": self.content,
            "created_at": self.created_at.isoformat(),
            "entity_type": "Message",
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "Message":
        """Create Message from DynamoDB item."""
        return cls(
            message_id=item["message_id"],
            conversation_id=item["conversation_id"],
            role=item["role"],
            content=item["content"],
            created_at=datetime.fromisoformat(item["created_at"]),
        )

    def to_response(self) -> MessageResponse:
        """Convert to response model."""
        return MessageResponse(
            message_id=self.message_id,
            conversation_id=self.conversation_id,
            role=self.role,
            content=self.content,
            created_at=self.created_at,
        )
