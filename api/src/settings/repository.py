"""
Repository for ProviderSettings entity using DynamoDB single table design.
"""

import boto3
from boto3.dynamodb.conditions import Key
from datetime import datetime, timezone
from typing import Optional
import logging

from src.settings.models import ProviderSettings
from src.config import settings

log = logging.getLogger(__name__)


class ProviderSettingsRepository:
    """
    Repository for ProviderSettings entity using DynamoDB single table design.

    Key Structure:
        pk: User#{user_email}              - Partition by user
        sk: ProviderSettings#{provider_name} - Unique provider identifier

    Access Patterns:
        - save: PutItem (create or update)
        - find_by_provider: GetItem by pk + sk
        - find_all_by_user: Query by pk with sk prefix "ProviderSettings#"
        - delete: DeleteItem by pk + sk
    """

    def __init__(self):
        self.dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, provider_settings: ProviderSettings) -> ProviderSettings:
        """
        Save provider settings (create or update).

        If settings exist for this provider, updates the existing record.
        Otherwise, creates a new record.
        """
        existing = self.find_by_provider(provider_settings.user_email, provider_settings.provider_name)

        if existing:
            # Update: preserve created_at, update updated_at
            provider_settings.created_at = existing.created_at
            provider_settings.updated_at = datetime.now(timezone.utc)

        self.table.put_item(Item=provider_settings.to_dynamo_item())
        log.info(f"Saved provider settings for {provider_settings.provider_name} for user {provider_settings.user_email}")
        return provider_settings

    def find_by_provider(self, user_email: str, provider_name: str) -> Optional[ProviderSettings]:
        """
        Find settings for a specific provider and user.

        Args:
            user_email: The user's email
            provider_name: The provider name (e.g., "Bedrock")

        Returns:
            ProviderSettings if found, None otherwise
        """
        response = self.table.get_item(
            Key={
                "pk": f"User#{user_email}",
                "sk": f"ProviderSettings#{provider_name}",
            }
        )
        item = response.get("Item")
        if item:
            return ProviderSettings.from_dynamo_item(item)
        return None

    def find_all_by_user(self, user_email: str) -> list[ProviderSettings]:
        """
        Find all provider settings for a user.

        Args:
            user_email: The user's email

        Returns:
            List of provider settings configured by the user
        """
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"User#{user_email}") & Key("sk").begins_with("ProviderSettings#")
        )

        items = response.get("Items", [])
        settings_list = [ProviderSettings.from_dynamo_item(item) for item in items]

        log.info(f"Found {len(settings_list)} provider settings for user {user_email}")
        return settings_list

    def delete(self, user_email: str, provider_name: str) -> bool:
        """
        Delete provider settings.

        Args:
            user_email: The user's email
            provider_name: The provider name

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            self.table.delete_item(
                Key={
                    "pk": f"User#{user_email}",
                    "sk": f"ProviderSettings#{provider_name}",
                }
            )
            log.info(f"Deleted provider settings for {provider_name} for user {user_email}")
            return True
        except Exception as e:
            log.error(f"Failed to delete provider settings {provider_name}: {e}")
            return False
