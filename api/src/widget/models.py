"""
Widget models for visitor conversations.

Separate from dashboard conversations to maintain data isolation
between agent owners and widget visitors.
"""

from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class WidgetVisitor(BaseModel):
    """Information about a widget visitor (from OAuth)."""
    visitor_id: str  # Google user ID or other unique identifier
    email: str
    name: Optional[str] = None
    picture: Optional[str] = None


class WidgetConversationResponse(BaseModel):
    """Response model for widget conversation."""
    conversation_id: str
    agent_id: str
    visitor_id: str
    visitor_name: Optional[str] = None
    title: str
    created_at: datetime
    updated_at: Optional[datetime] = None
    message_count: int = 0


class CreateWidgetConversationRequest(BaseModel):
    """Request model for creating a widget conversation."""
    title: Optional[str] = Field(
        default=None,
        max_length=200,
        description="Optional title (auto-generated if not provided)"
    )


class WidgetConversation(BaseModel):
    """
    Widget conversation between a visitor and an agent.

    DynamoDB Schema:
    - pk: Agent#{agent_id}#Widget
    - sk: Conversation#{conversation_id}
    - GSI (gsi2): gsi2_pk=Visitor#{visitor_id}, gsi2_sk=Agent#{agent_id}#Conversation#{conversation_id}

    This allows:
    - Query all conversations for an agent's widget
    - Query all conversations for a visitor across agents
    """
    conversation_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str
    visitor_id: str  # From OAuth (Google user ID)
    visitor_email: str
    visitor_name: Optional[str] = None
    visitor_picture: Optional[str] = None
    title: str = "New Conversation"
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None
    message_count: int = 0

    @property
    def pk(self) -> str:
        """Partition key: Agent#{agent_id}#Widget"""
        return f"Agent#{self.agent_id}#Widget"

    @property
    def sk(self) -> str:
        """Sort key: Conversation#{conversation_id}"""
        return f"Conversation#{self.conversation_id}"

    @property
    def gsi2_pk(self) -> str:
        """GSI2 partition key for visitor lookup."""
        return f"Visitor#{self.visitor_id}"

    @property
    def gsi2_sk(self) -> str:
        """GSI2 sort key for visitor lookup."""
        return f"Agent#{self.agent_id}#Conversation#{self.conversation_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        """Convert to DynamoDB item format."""
        return {
            "pk": self.pk,
            "sk": self.sk,
            "gsi2_pk": self.gsi2_pk,
            "gsi2_sk": self.gsi2_sk,
            "conversation_id": self.conversation_id,
            "agent_id": self.agent_id,
            "visitor_id": self.visitor_id,
            "visitor_email": self.visitor_email,
            "visitor_name": self.visitor_name,
            "visitor_picture": self.visitor_picture,
            "title": self.title,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "message_count": self.message_count,
            "entity_type": "WidgetConversation",
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "WidgetConversation":
        """Create WidgetConversation from DynamoDB item."""
        return cls(
            conversation_id=item["conversation_id"],
            agent_id=item["agent_id"],
            visitor_id=item["visitor_id"],
            visitor_email=item["visitor_email"],
            visitor_name=item.get("visitor_name"),
            visitor_picture=item.get("visitor_picture"),
            title=item.get("title", "New Conversation"),
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
            message_count=item.get("message_count", 0),
        )

    def to_response(self) -> WidgetConversationResponse:
        """Convert to response model."""
        return WidgetConversationResponse(
            conversation_id=self.conversation_id,
            agent_id=self.agent_id,
            visitor_id=self.visitor_id,
            visitor_name=self.visitor_name,
            title=self.title,
            created_at=self.created_at,
            updated_at=self.updated_at,
            message_count=self.message_count,
        )


class WidgetConfigResponse(BaseModel):
    """Configuration response for widget initialization."""
    agent_name: str
    agent_id: str
    welcome_message: Optional[str] = None
    theme: dict[str, Any] = Field(default_factory=dict)


class WidgetMessageRequest(BaseModel):
    """Request model for sending a message via widget."""
    content: str = Field(..., min_length=1, max_length=10000)
