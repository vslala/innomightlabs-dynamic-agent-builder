"""
Agent API Key models for widget authentication.

API keys allow external websites to authenticate requests to agents
via the embeddable chat widget.
"""

import secrets
from datetime import datetime, timezone
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def generate_public_key() -> str:
    """Generate a cryptographically secure public API key.

    Format: pk_live_{32 random hex characters}
    """
    return f"pk_live_{secrets.token_hex(16)}"


class CreateApiKeyRequest(BaseModel):
    """Request model for creating an API key."""
    name: str = Field(..., min_length=1, max_length=100, description="Human-readable name for this key")
    allowed_origins: list[str] = Field(
        default_factory=list,
        description="List of allowed origins (e.g., ['https://example.com']). Empty = allow all."
    )


class UpdateApiKeyRequest(BaseModel):
    """Request model for updating an API key."""
    name: Optional[str] = Field(None, min_length=1, max_length=100)
    allowed_origins: Optional[list[str]] = None
    is_active: Optional[bool] = None


class ApiKeyResponse(BaseModel):
    """Response model for API key (excludes sensitive internal fields)."""
    key_id: str
    agent_id: str
    public_key: str
    name: str
    allowed_origins: list[str]
    is_active: bool
    created_by: str
    created_at: datetime
    last_used_at: Optional[datetime] = None
    request_count: int = 0


class AgentApiKey(BaseModel):
    """
    API key for agent widget authentication.

    DynamoDB Schema:
    - pk: Agent#{agent_id}
    - sk: ApiKey#{key_id}
    - GSI (gsi2): gsi2_pk=ApiKey#{public_key}, gsi2_sk=Agent#{agent_id}
    """
    key_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str
    public_key: str = Field(default_factory=generate_public_key)
    name: str
    allowed_origins: list[str] = Field(default_factory=list)
    is_active: bool = True
    created_by: str  # User email who created this key
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    last_used_at: Optional[datetime] = None
    request_count: int = 0

    @property
    def pk(self) -> str:
        """Partition key: Agent#{agent_id}"""
        return f"Agent#{self.agent_id}"

    @property
    def sk(self) -> str:
        """Sort key: ApiKey#{key_id}"""
        return f"ApiKey#{self.key_id}"

    @property
    def gsi2_pk(self) -> str:
        """GSI2 partition key for lookup by public key."""
        return f"ApiKey#{self.public_key}"

    @property
    def gsi2_sk(self) -> str:
        """GSI2 sort key."""
        return f"Agent#{self.agent_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        """Convert to DynamoDB item format."""
        return {
            "pk": self.pk,
            "sk": self.sk,
            "gsi2_pk": self.gsi2_pk,
            "gsi2_sk": self.gsi2_sk,
            "key_id": self.key_id,
            "agent_id": self.agent_id,
            "public_key": self.public_key,
            "name": self.name,
            "allowed_origins": self.allowed_origins,
            "is_active": self.is_active,
            "created_by": self.created_by,
            "created_at": self.created_at.isoformat(),
            "last_used_at": self.last_used_at.isoformat() if self.last_used_at else None,
            "request_count": self.request_count,
            "entity_type": "AgentApiKey",
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "AgentApiKey":
        """Create AgentApiKey from DynamoDB item."""
        return cls(
            key_id=item["key_id"],
            agent_id=item["agent_id"],
            public_key=item["public_key"],
            name=item["name"],
            allowed_origins=item.get("allowed_origins", []),
            is_active=item.get("is_active", True),
            created_by=item["created_by"],
            created_at=datetime.fromisoformat(item["created_at"]),
            last_used_at=datetime.fromisoformat(item["last_used_at"]) if item.get("last_used_at") else None,
            request_count=item.get("request_count", 0),
        )

    def to_response(self) -> ApiKeyResponse:
        """Convert to response model."""
        return ApiKeyResponse(
            key_id=self.key_id,
            agent_id=self.agent_id,
            public_key=self.public_key,
            name=self.name,
            allowed_origins=self.allowed_origins,
            is_active=self.is_active,
            created_by=self.created_by,
            created_at=self.created_at,
            last_used_at=self.last_used_at,
            request_count=self.request_count,
        )

    def is_origin_allowed(self, origin: Optional[str]) -> bool:
        """Check if the given origin is allowed for this API key.

        Returns True if:
        - allowed_origins is empty (allow all)
        - origin matches one of the allowed origins
        """
        if not self.allowed_origins:
            return True
        if not origin:
            return False
        return origin in self.allowed_origins
