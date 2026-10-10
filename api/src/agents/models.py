from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Any, Literal, Optional
from uuid import uuid4

from src.agents.image_generation.capabilities import image_capability_registry
from src.iam.actions import ResourceRef

# How the caller reaches an agent: they own it, it was shared with them, or they see it as an admin
# (metadata only: no persona)
AgentAccess = Literal["owner", "shared", "admin"]


class CreateAgentRequest(BaseModel):
    """Request model for creating an agent"""
    agent_name: str
    agent_architecture: str
    agent_provider: str
    agent_model: Optional[str] = None  # e.g., "claude-sonnet-4", "claude-3.5-haiku"
    agent_persona: str
    agent_description: Optional[str] = None  # Short human-readable description
    session_timeout_minutes: Optional[int] = None  # None = use default (60 minutes)
    # Ollama only: "enabled" | "disabled" | None (let the model use its own default)
    agent_ollama_thinking: Optional[str] = None


class AgentResponse(BaseModel):
    """Response model for agent (excludes sensitive fields)"""
    agent_id: str
    agent_name: str
    agent_architecture: str
    agent_provider: str
    agent_model: Optional[str] = None
    agent_persona: str
    agent_description: Optional[str] = None
    capabilities: list[str] = Field(default_factory=list)
    session_timeout_minutes: int = 60  # Default 60 minutes
    is_agent2agent_enabled: bool = False
    agent_ollama_thinking: str = "default"
    account_id: str
    owner_id: str
    created_by: str
    access: AgentAccess = "owner"
    created_at: datetime
    updated_at: Optional[datetime] = None


class MemoryCapacityWarning(BaseModel):
    block_name: str
    word_count: int
    word_limit: int
    percent: float


class Agent(BaseModel):
    agent_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_name: str
    agent_architecture: str
    agent_provider: str
    agent_model: Optional[str] = None  # e.g., "claude-sonnet-4", "claude-3.5-haiku"
    agent_provider_api_key: Optional[str] = None  # Deprecated: now stored in ProviderSettings
    agent_persona: str
    agent_description: Optional[str] = None  # Short human-readable description
    session_timeout_minutes: int = 60  # Session timeout in minutes, 0 = no timeout
    is_agent2agent_enabled: bool = False
    # Ollama only: "enabled" | "disabled" | None (let the model use its own default)
    agent_ollama_thinking: Optional[str] = None
    account_id: str
    # The member it belongs to (a user_id). Authorization follows it; a transfer changes it.
    owner_id: str
    created_by: str  # user_id of whoever created it, kept for audit only
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        """Partition key: the account, which shares agents among its members"""
        return f"Account#{self.account_id}"

    @property
    def resource_ref(self) -> ResourceRef:
        return ResourceRef("agent", self.agent_id, self.owner_id)

    @property
    def sk(self) -> str:
        """Sort key: Agent#{agent_id} - unique identifier for the agent"""
        return f"Agent#{self.agent_id}"

    def to_dynamo_item(self) -> dict:
        """Convert to DynamoDB item format"""
        item = {
            "pk": self.pk,
            "sk": self.sk,
            "agent_id": self.agent_id,
            "agent_name": self.agent_name,
            "agent_architecture": self.agent_architecture,
            "agent_provider": self.agent_provider,
            "agent_model": self.agent_model,
            "agent_persona": self.agent_persona,
            "agent_description": self.agent_description,
            "session_timeout_minutes": self.session_timeout_minutes,
            "is_agent2agent_enabled": self.is_agent2agent_enabled,
            "agent_ollama_thinking": self.agent_ollama_thinking,
            "account_id": self.account_id,
            "owner_id": self.owner_id,
            "created_by": self.created_by,
            # Agent ids are global: widget, /v1, A2A and schedules find an agent by id alone
            "gsi2_pk": f"Agent#{self.agent_id}",
            "gsi2_sk": "Agent",
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "entity_type": "Agent",
        }
        # Only include api_key if present (backward compatibility)
        if self.agent_provider_api_key:
            item["agent_provider_api_key"] = self.agent_provider_api_key
        return item

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "Agent":
        """Create Agent from DynamoDB item"""
        from src.utils.dynamodb import convert_decimals

        # Convert all Decimals to int/float (DynamoDB returns numbers as Decimal)
        item = convert_decimals(item)

        return cls(
            agent_id=item["agent_id"],
            agent_name=item["agent_name"],
            agent_architecture=item.get("agent_architecture", "krishna-mini"),  # Default for backward compat
            agent_provider=item["agent_provider"],
            agent_model=item.get("agent_model"),  # Optional, defaults to provider's default
            agent_provider_api_key=item.get("agent_provider_api_key"),  # Optional for backward compat
            agent_persona=item["agent_persona"],
            agent_description=item.get("agent_description"),
            session_timeout_minutes=item.get("session_timeout_minutes", 60),
            is_agent2agent_enabled=bool(item.get("is_agent2agent_enabled", False)),
            agent_ollama_thinking=item.get("agent_ollama_thinking"),
            account_id=item["account_id"],
            owner_id=item["owner_id"],
            created_by=item["created_by"],
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )

    def to_response(self, access: AgentAccess = "owner") -> AgentResponse:
        """Convert to response model (excludes sensitive fields). An admin sees metadata only."""
        response = AgentResponse(
            agent_id=self.agent_id,
            agent_name=self.agent_name,
            agent_architecture=self.agent_architecture,
            agent_provider=self.agent_provider,
            agent_model=self.agent_model,
            agent_persona=self.agent_persona,
            agent_description=self.agent_description,
            capabilities=image_capability_registry.capabilities_for(
                self.agent_provider,
                self.agent_model,
            ),
            session_timeout_minutes=self.session_timeout_minutes,
            is_agent2agent_enabled=self.is_agent2agent_enabled,
            agent_ollama_thinking=self.agent_ollama_thinking or "default",
            account_id=self.account_id,
            owner_id=self.owner_id,
            created_by=self.created_by,
            access=access,
            created_at=self.created_at,
            updated_at=self.updated_at,
        )
        if access == "admin":
            response.agent_persona = ""
        return response
