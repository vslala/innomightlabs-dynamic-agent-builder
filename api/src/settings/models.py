"""
Provider Settings model for storing user's LLM provider configurations.
"""

from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Any, Optional


class ProviderSettings(BaseModel):
    """
    User's configuration for an LLM provider (e.g., Bedrock, OpenAI).

    Stores encrypted credentials for the provider.
    """
    user_email: str
    provider_name: str  # "Bedrock", "OpenAI", etc.
    encrypted_credentials: str  # JSON string of encrypted credentials
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: Optional[datetime] = None

    @property
    def pk(self) -> str:
        """Partition key: User#{user_email}"""
        return f"User#{self.user_email}"

    @property
    def sk(self) -> str:
        """Sort key: ProviderSettings#{provider_name}"""
        return f"ProviderSettings#{self.provider_name}"

    def to_dynamo_item(self) -> dict:
        """Convert to DynamoDB item format"""
        return {
            "pk": self.pk,
            "sk": self.sk,
            "user_email": self.user_email,
            "provider_name": self.provider_name,
            "encrypted_credentials": self.encrypted_credentials,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "entity_type": "ProviderSettings",
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "ProviderSettings":
        """Create ProviderSettings from DynamoDB item"""
        return cls(
            user_email=item["user_email"],
            provider_name=item["provider_name"],
            encrypted_credentials=item["encrypted_credentials"],
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )


class ProviderSettingsResponse(BaseModel):
    """Response model for provider settings (excludes encrypted credentials)"""
    provider_name: str
    is_configured: bool
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
