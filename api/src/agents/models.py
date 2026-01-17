from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4


class CreateAgentRequest(BaseModel):
    """Request model for creating an agent"""
    agent_name: str
    agent_architecture: str
    agent_provider: str
    agent_provider_api_key: str
    agent_persona: str


class AgentResponse(BaseModel):
    """Response model for agent (excludes sensitive fields)"""
    agent_id: str
    agent_name: str
    agent_architecture: str
    agent_provider: str
    agent_persona: str
    created_by: str
    created_at: datetime
    updated_at: Optional[datetime] = None


class Agent(BaseModel):
    agent_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_name: str
    agent_architecture: str
    agent_provider: str
    agent_provider_api_key: str
    agent_persona: str
    created_by: str  # User email who created this agent
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        """Partition key: User#{created_by} - allows querying all agents by user"""
        return f"User#{self.created_by}"

    @property
    def sk(self) -> str:
        """Sort key: Agent#{agent_id} - unique identifier for the agent"""
        return f"Agent#{self.agent_id}"

    def to_dynamo_item(self) -> dict:
        """Convert to DynamoDB item format"""
        return {
            "pk": self.pk,
            "sk": self.sk,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_architecture": self.agent_architecture,
            "agent_provider": self.agent_provider,
            "agent_provider_api_key": self.agent_provider_api_key,
            "agent_persona": self.agent_persona,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "entity_type": "Agent",  # For easier filtering if needed
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "Agent":
        """Create Agent from DynamoDB item"""
        return cls(
            agent_id=item["agent_id"],
            agent_name=item["agent_name"],
            agent_architecture=item.get("agent_architecture", "krishna-mini"),  # Default for backward compat
            agent_provider=item["agent_provider"],
            agent_provider_api_key=item["agent_provider_api_key"],
            agent_persona=item["agent_persona"],
            created_by=item["created_by"],
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )

    def to_response(self) -> AgentResponse:
        """Convert to response model (excludes sensitive fields)"""
        return AgentResponse(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            agent_architecture=self.agent_architecture,
            agent_provider=self.agent_provider,
            agent_persona=self.agent_persona,
            created_by=self.created_by,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )