"""
Repository for user skill configuration persistence.

Handles CRUD operations for UserSkillConfig in DynamoDB.
Follows the Repository pattern used elsewhere in the codebase.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Optional

from src.config import settings
from src.db import get_dynamodb_resource

from .models import UserSkillConfig


class UserSkillConfigRepository:
    """
    Persists and retrieves user skill configuration.

    Uses composite keys: User#email (pk), SkillConfig#skill_id (sk).
    """

    def __init__(self):
        self._dynamodb = get_dynamodb_resource()
        self._table = self._dynamodb.Table(settings.dynamodb_table)

    def save(self, config: UserSkillConfig) -> None:
        """
        Save or update user skill configuration.

        Args:
            config: The configuration to persist.
        """
        now = datetime.now(timezone.utc).isoformat()
        config.updated_at = now
        if not config.created_at:
            config.created_at = now

        self._table.put_item(Item=config.to_dynamo_item())

    def get(self, user_email: str, skill_id: str) -> Optional[UserSkillConfig]:
        """
        Retrieve configuration for a user and skill.

        Args:
            user_email: The user's email.
            skill_id: The skill identifier.

        Returns:
            The configuration if found, else None.
        """
        response = self._table.get_item(
            Key={
                "pk": f"User#{user_email}",
                "sk": f"SkillConfig#{skill_id}",
            }
        )
        item = response.get("Item")
        if item:
            return UserSkillConfig.from_dynamo_item(item)
        return None

    def list_enabled(self, user_email: str) -> list[UserSkillConfig]:
        """
        List all skills enabled for a user.

        Args:
            user_email: The user's email.

        Returns:
            List of enabled skill configurations.
        """
        response = self._table.query(
            KeyConditionExpression="pk = :pk AND begins_with(sk, :sk_prefix)",
            ExpressionAttributeValues={
                ":pk": f"User#{user_email}",
                ":sk_prefix": "SkillConfig#",
            },
        )
        items = response.get("Items", [])
        return [UserSkillConfig.from_dynamo_item(item) for item in items]

    def delete(self, user_email: str, skill_id: str) -> bool:
        """
        Remove a user's configuration for a skill.

        Args:
            user_email: The user's email.
            skill_id: The skill identifier.

        Returns:
            True if an item was deleted.
        """
        try:
            self._table.delete_item(
                Key={
                    "pk": f"User#{user_email}",
                    "sk": f"SkillConfig#{skill_id}",
                }
            )
            return True
        except Exception:
            return False
