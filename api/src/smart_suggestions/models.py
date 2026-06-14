"""Models for schema-driven smart suggestions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class SmartSuggestionType:
    CRON_EXPRESSION = "cron_expression"


class SmartSuggestionSettings(BaseModel):
    user_email: str
    enabled: bool = False
    provider_name: str | None = None
    model_name: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None

    @model_validator(mode="after")
    def validate_model_when_enabled(self) -> "SmartSuggestionSettings":
        if self.enabled and (not self.provider_name or not self.model_name):
            raise ValueError("provider_name and model_name are required when smart suggestions are enabled")
        return self

    @property
    def pk(self) -> str:
        return f"User#{self.user_email}"

    @property
    def sk(self) -> str:
        return "SmartSuggestionSettings"

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "user_email": self.user_email,
            "enabled": self.enabled,
            "provider_name": self.provider_name,
            "model_name": self.model_name,
            "created_at": self.created_at.isoformat(),
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "entity_type": "SmartSuggestionSettings",
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "SmartSuggestionSettings":
        return cls(
            user_email=item["user_email"],
            enabled=bool(item.get("enabled", False)),
            provider_name=item.get("provider_name"),
            model_name=item.get("model_name"),
            created_at=datetime.fromisoformat(item["created_at"]),
            updated_at=datetime.fromisoformat(item["updated_at"]) if item.get("updated_at") else None,
        )


class SmartSuggestionSettingsRequest(BaseModel):
    enabled: bool = False
    provider_name: str | None = None
    model_name: str | None = None

    @model_validator(mode="after")
    def validate_model_when_enabled(self) -> "SmartSuggestionSettingsRequest":
        if self.enabled and (not self.provider_name or not self.model_name):
            raise ValueError("provider_name and model_name are required when smart suggestions are enabled")
        return self


class SmartSuggestionSettingsResponse(BaseModel):
    enabled: bool
    provider_name: str | None = None
    model_name: str | None = None
    is_configured: bool
    created_at: datetime | None = None
    updated_at: datetime | None = None

    @classmethod
    def from_settings(cls, settings: SmartSuggestionSettings | None) -> "SmartSuggestionSettingsResponse":
        if not settings:
            return cls(enabled=False, is_configured=False)
        return cls(
            enabled=settings.enabled,
            provider_name=settings.provider_name,
            model_name=settings.model_name,
            is_configured=settings.enabled and bool(settings.provider_name and settings.model_name),
            created_at=settings.created_at,
            updated_at=settings.updated_at,
        )


class SmartSuggestionRequest(BaseModel):
    suggestion_type: Literal["cron_expression"]
    query: str = Field(min_length=1)
    current_value: str | None = None
    context: dict[str, Any] = Field(default_factory=dict)

    @field_validator("query")
    @classmethod
    def normalize_query(cls, value: str) -> str:
        return value.strip()


class SmartSuggestionResponse(BaseModel):
    suggestion_type: str
    value: str
    display_text: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

