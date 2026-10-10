"""
Provider Settings model for storing user's LLM provider configurations.
"""

from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Any, Optional

from src.accounts.owner import member_partition


class ProviderSettings(BaseModel):
    """
    The account's configuration for a provider: an LLM (Bedrock, OpenAI, ...) or an OAuth connection (Google
    Mail, Drive, Ads). Admins set it up; every member's agents use it, and the account pays for it.

    Stores encrypted credentials for the provider.
    """
    account_id: str
    provider_name: str  # "Bedrock", "OpenAI", etc.
    encrypted_credentials: str  # JSON string of encrypted credentials
    auth_type: str = "api_key"  # "api_key" | "oauth"
    #: The user_id of whoever last connected or changed it, for audit
    updated_by: Optional[str] = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        """Partition key: Account#{account_id}"""
        return f"Account#{self.account_id}"

    @property
    def sk(self) -> str:
        """Sort key: ProviderSettings#{provider_name}"""
        return f"ProviderSettings#{self.provider_name}"

    def to_dynamo_item(self) -> dict:
        """Convert to DynamoDB item format"""
        return {
            "pk": self.pk,
            "sk": self.sk,
            "account_id": self.account_id,
            "provider_name": self.provider_name,
            "encrypted_credentials": self.encrypted_credentials,
            "auth_type": self.auth_type,
            "updated_by": self.updated_by,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "entity_type": "ProviderSettings",
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "ProviderSettings":
        """Create ProviderSettings from DynamoDB item"""
        return cls(
            account_id=item["account_id"],
            provider_name=item["provider_name"],
            encrypted_credentials=item["encrypted_credentials"],
            auth_type=item.get("auth_type", "api_key"),
            updated_by=item.get("updated_by"),
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )


class ProviderSettingsResponse(BaseModel):
    """Response model for provider settings (excludes encrypted credentials)"""
    provider_name: str
    is_configured: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class Agent2AgentAllowedOrigin(BaseModel):
    """User-approved origin for outbound Agent2Agent registry/service calls."""

    origin: str
    label: str | None = None


class Agent2AgentSettings(BaseModel):
    """The account's Agent2Agent outbound trust settings."""

    account_id: str
    updated_by: Optional[str] = None
    allowed_origins: list[Agent2AgentAllowedOrigin] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        return f"Account#{self.account_id}"

    @property
    def sk(self) -> str:
        return "Agent2AgentSettings"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "account_id": self.account_id,
            "updated_by": self.updated_by,
            "allowed_origins": [
                origin.model_dump(mode="json", exclude_none=True)
                for origin in self.allowed_origins
            ],
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "entity_type": "Agent2AgentSettings",
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "Agent2AgentSettings":
        return cls(
            account_id=item["account_id"],
            updated_by=item.get("updated_by"),
            allowed_origins=[
                Agent2AgentAllowedOrigin.model_validate(origin)
                for origin in item.get("allowed_origins", [])
                if isinstance(origin, dict)
            ],
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )


class Agent2AgentSettingsResponse(BaseModel):
    allowed_origins: list[Agent2AgentAllowedOrigin] = Field(default_factory=list)
    allowed_origins_map: dict[str, str] = Field(default_factory=dict)
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None


class DefaultAgentPreference(BaseModel):
    """A member's preferred agent to preselect when starting a new conversation, in one account."""

    account_id: str
    user_id: str
    agent_id: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        return member_partition(self.account_id, self.user_id)

    @property
    def sk(self) -> str:
        return "DefaultAgentPreference"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "account_id": self.account_id,
            "user_id": self.user_id,
            "agent_id": self.agent_id,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "entity_type": "DefaultAgentPreference",
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "DefaultAgentPreference":
        return cls(
            account_id=item["account_id"],
            user_id=item["user_id"],
            agent_id=item["agent_id"],
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )


class DefaultAgentPreferenceResponse(BaseModel):
    agent_id: Optional[str] = None
    updated_at: Optional[datetime] = None
