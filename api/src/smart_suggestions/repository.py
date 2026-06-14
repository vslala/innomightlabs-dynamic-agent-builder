"""Repository for user-level smart suggestion settings."""

from __future__ import annotations

from datetime import datetime, timezone

from src.config import settings
from src.db import get_dynamodb_resource
from src.smart_suggestions.models import SmartSuggestionSettings


class SmartSuggestionSettingsRepository:
    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, suggestion_settings: SmartSuggestionSettings) -> SmartSuggestionSettings:
        existing = self.find_by_user(suggestion_settings.user_email)
        if existing:
            suggestion_settings.created_at = existing.created_at
            suggestion_settings.updated_at = datetime.now(timezone.utc)
        self.table.put_item(Item=suggestion_settings.to_dynamo_item())
        return suggestion_settings

    def find_by_user(self, user_email: str) -> SmartSuggestionSettings | None:
        response = self.table.get_item(
            Key={
                "pk": f"User#{user_email}",
                "sk": "SmartSuggestionSettings",
            }
        )
        item = response.get("Item")
        if not item:
            return None
        return SmartSuggestionSettings.from_dynamo_item(item)


def get_smart_suggestion_settings_repository() -> SmartSuggestionSettingsRepository:
    return SmartSuggestionSettingsRepository()

