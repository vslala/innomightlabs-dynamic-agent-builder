"""The account's image generation: whether it is on, and which provider and model draw. Admins set it.

Like the account's Image Reading (`src/vision/`), the drawing model is chosen apart from an agent's own model: most
providers draw with a model of their own (an image model), which a chat model can't stand in for.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field, model_validator

from src.config import settings
from src.db import get_dynamodb_resource


class ImageGenerationSettings(BaseModel):
    """DynamoDB: pk=Account#{account_id}, sk=ImageGenerationSettings."""

    account_id: str
    #: The user_id of whoever last changed it, for audit
    updated_by: str | None = None
    enabled: bool = False
    provider_name: str | None = None
    model_name: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_model_when_enabled(self) -> "ImageGenerationSettings":
        if self.enabled and (not self.provider_name or not self.model_name):
            raise ValueError("provider_name and model_name are required when image generation is enabled")
        return self

    @property
    def is_configured(self) -> bool:
        return self.enabled and bool(self.provider_name and self.model_name)

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": f"Account#{self.account_id}",
            "sk": "ImageGenerationSettings",
            "account_id": self.account_id,
            "updated_by": self.updated_by,
            "enabled": self.enabled,
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "entity_type": "ImageGenerationSettings",
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "ImageGenerationSettings":
        return cls(
            account_id=item["account_id"],
            updated_by=item.get("updated_by"),
            enabled=bool(item.get("enabled", False)),
            provider_name=item.get("provider_name"),
            model_name=item.get("model_name"),
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )


class ImageGenerationSettingsRequest(BaseModel):
    enabled: bool = False
    provider_name: str | None = None
    model_name: str | None = None

    @model_validator(mode="after")
    def validate_model_when_enabled(self) -> "ImageGenerationSettingsRequest":
        if self.enabled and (not self.provider_name or not self.model_name):
            raise ValueError("provider_name and model_name are required when image generation is enabled")
        return self


class ImageGenerationSettingsResponse(BaseModel):
    enabled: bool
    provider_name: str | None = None
    model_name: str | None = None
    is_configured: bool

    @classmethod
    def from_settings(cls, saved: ImageGenerationSettings | None) -> "ImageGenerationSettingsResponse":
        if not saved:
            return cls(enabled=False, is_configured=False)
        return cls(
            enabled=saved.enabled,
            provider_name=saved.provider_name,
            model_name=saved.model_name,
            is_configured=saved.is_configured,
        )


class ImageGenerationSettingsRepository:
    def __init__(self) -> None:
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def save(self, saved: ImageGenerationSettings) -> ImageGenerationSettings:
        existing = self.find_in_account(saved.account_id)
        if existing:
            saved.created_at = existing.created_at
            saved.updated_at = datetime.now(timezone.utc)
        self.table.put_item(Item=saved.to_dynamo_item())
        return saved

    def find_in_account(self, account_id: str) -> ImageGenerationSettings | None:
        item = self.table.get_item(Key={"pk": f"Account#{account_id}", "sk": "ImageGenerationSettings"}).get("Item")
        return ImageGenerationSettings.from_dynamo_item(item) if item else None


def get_image_generation_settings_repository() -> ImageGenerationSettingsRepository:
    return ImageGenerationSettingsRepository()
