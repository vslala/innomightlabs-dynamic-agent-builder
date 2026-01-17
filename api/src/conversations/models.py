"""
Conversation models for the conversations module.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    """Request model for creating a conversation."""

    title: str = Field(min_length=1, max_length=200, description="Title of the conversation")
    description: Optional[str] = Field(
        default=None, max_length=1000, description="Optional description"
    )
    agent_id: str = Field(description="ID of the agent that will manage this conversation")


class UpdateConversationRequest(BaseModel):
    """Request model for updating a conversation."""

    title: Optional[str] = Field(
        default=None, min_length=1, max_length=200, description="New title"
    )
    description: Optional[str] = Field(default=None, max_length=1000, description="New description")
    agent_id: Optional[str] = Field(default=None, description="New agent ID to assign")


class ConversationResponse(BaseModel):
    """Response model for conversation."""

    conversation_id: str
    title: str
    description: Optional[str] = None
    agent_id: str
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class Conversation(BaseModel):
    """Domain model for conversation with DynamoDB serialization."""

    conversation_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    description: Optional[str] = None
    agent_id: str
    created_by: str  # User email who created this conversation
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        """Partition key: USER#{created_by} - allows querying all conversations by user."""
        return f"USER#{self.created_by}"

    @property
    def sk(self) -> str:
        """Sort key: CONVERSATION#{conversation_id} - unique identifier."""
        return f"CONVERSATION#{self.conversation_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        """Convert to DynamoDB item format."""
        return {
            "pk": self.pk,
            "sk": self.sk,
            "conversation_id": self.conversation_id,
            "title": self.title,
            "description": self.description,
            "agent_id": self.agent_id,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "entity_type": "Conversation",
            # GSI for sorting by created_at (reverse chronological)
            "gsi1_pk": self.pk,
            "gsi1_sk": f"CONVERSATION#{self.created_at.isoformat()}#{self.conversation_id}",
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "Conversation":
        """Create Conversation from DynamoDB item."""
        return cls(
            conversation_id=item["conversation_id"],
            title=item["title"],
            description=item.get("description"),
            agent_id=item["agent_id"],
            created_by=item["created_by"],
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )

    def to_response(self) -> ConversationResponse:
        """Convert to response model."""
        return ConversationResponse(
            conversation_id=self.conversation_id,
            title=self.title,
            description=self.description,
            agent_id=self.agent_id,
            created_by=self.created_by,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
