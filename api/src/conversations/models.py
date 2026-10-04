"""
Conversation models for the conversations module.
"""

from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class CreateConversationRequest(BaseModel):
    """Request model for creating a conversation."""

    title: str = Field(min_length=1, max_length=200, description="Title of the conversation")
    description: Optional[str] = Field(
        default=None, max_length=1000, description="Optional description"
    )
    agent_id: str = Field(description="ID of the agent that will manage this conversation")
    context: Optional[str] = Field(
        default=None,
        description="Standing instructions sent to the agent on every turn of this conversation",
    )


class UpdateConversationRequest(BaseModel):
    """Request model for updating a conversation."""

    title: Optional[str] = Field(
        default=None, min_length=1, max_length=200, description="New title"
    )
    description: Optional[str] = Field(default=None, max_length=1000, description="New description")
    agent_id: Optional[str] = Field(default=None, description="New agent ID to assign")
    context: Optional[str] = Field(default=None, description="New conversation context")


class ConversationResponse(BaseModel):
    """Response model for conversation."""

    conversation_id: str
    title: str
    description: Optional[str] = None
    agent_id: str
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    context: Optional[str] = None
    conversation_type: Literal["chat", "automation"] = "chat"
    automation_id: Optional[str] = None
    automation_run_id: Optional[str] = None


class Conversation(BaseModel):
    """Domain model for conversation with DynamoDB serialization."""

    conversation_id: str = Field(default_factory=lambda: str(uuid4()))
    title: str
    description: Optional[str] = None
    agent_id: str
    created_by: str  # User email who created this conversation
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    #: Sent to the LLM on every turn, so it never has to live in the message history.
    context: Optional[str] = None

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
            "context": self.context,
            "entity_type": "Conversation",
            "conversation_type": "chat",
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
            updated_at=(
                datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None
            ),
            context=item.get("context"),
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
            context=self.context,
            conversation_type="chat",
        )


class AutomationConversation(Conversation):
    """Conversation subtype for automation runs spanning one or more agents."""

    conversation_type: Literal["automation"] = "automation"
    automation_id: str
    automation_run_id: str

    def to_dynamo_item(self) -> dict[str, Any]:
        """Convert to DynamoDB item format."""
        item = super().to_dynamo_item()
        item.update(
            {
                "entity_type": "AutomationConversation",
                "conversation_type": self.conversation_type,
                "automation_id": self.automation_id,
                "automation_run_id": self.automation_run_id,
            }
        )
        return item

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
            context=self.context,
            conversation_type=self.conversation_type,
            automation_id=self.automation_id,
            automation_run_id=self.automation_run_id,
        )

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "AutomationConversation":
        """Create AutomationConversation from DynamoDB item."""
        return cls(
            conversation_id=item["conversation_id"],
            title=item["title"],
            description=item.get("description"),
            agent_id=item["agent_id"],
            created_by=item["created_by"],
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=(
                datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None
            ),
            context=item.get("context"),
            automation_id=item["automation_id"],
            automation_run_id=item["automation_run_id"],
        )


class ApiConversation(Conversation):
    """Conversation created through the public /v1 API with a secret key.

    Stored under the key's own pseudo-owner partition rather than the agent
    owner's, so a busy integration never floods the owner's dashboard list and
    one key can never load another key's conversations. A conversation started
    for an end user gets that end user's own partition within the key, the way
    each dashboard user has theirs.
    """

    api_key_id: str
    end_user_id: Optional[str] = None

    @staticmethod
    def owner_for(api_key_id: str, end_user_id: Optional[str] = None) -> str:
        """The `created_by` a conversation of this key, and of this end user if any, is stored under."""
        owner = f"secret-key:{api_key_id}"
        return f"{owner}:{end_user_id}" if end_user_id else owner

    @classmethod
    def start(
        cls,
        *,
        api_key_id: str,
        agent_id: str,
        title: str,
        end_user_id: Optional[str] = None,
        context: Optional[str] = None,
    ) -> "ApiConversation":
        return cls(
            api_key_id=api_key_id,
            agent_id=agent_id,
            title=title,
            end_user_id=end_user_id,
            context=context,
            created_by=cls.owner_for(api_key_id, end_user_id),
        )

    @property
    def actor_id(self) -> str:
        """Memory scope: per key, or per end user of that key when one is given."""
        return self.owner_for(self.api_key_id, self.end_user_id)

    def to_dynamo_item(self) -> dict[str, Any]:
        item = super().to_dynamo_item()
        item.update(
            {
                "entity_type": "ApiConversation",
                "api_key_id": self.api_key_id,
                "end_user_id": self.end_user_id,
            }
        )
        return item

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "ApiConversation":
        return cls(
            conversation_id=item["conversation_id"],
            title=item["title"],
            description=item.get("description"),
            agent_id=item["agent_id"],
            created_by=item["created_by"],
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=(
                datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None
            ),
            context=item.get("context"),
            api_key_id=item["api_key_id"],
            end_user_id=item.get("end_user_id"),
        )
