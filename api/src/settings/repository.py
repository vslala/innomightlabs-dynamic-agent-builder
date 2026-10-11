"""
Repositories for the account's settings (provider settings, A2A trust settings) and a member's default agent,
using DynamoDB single table design.
"""

from ..db import get_dynamodb_resource
from boto3.dynamodb.conditions import Key
from datetime import datetime, timezone
from typing import Optional
import logging

from src.accounts.owner import member_partition
from src.settings.models import Agent2AgentSettings, DefaultAgentPreference, ProviderSettings
from src.config import settings

log = logging.getLogger(__name__)


class ProviderSettingsRepository:
    """
    Repository for ProviderSettings entity using DynamoDB single table design.

    Key Structure:
        pk: Account#{account_id}             - The account's, used by every member's agents
        sk: ProviderSettings#{provider_name} - Unique provider identifier

    Access Patterns:
        - save: PutItem (create or update)
        - find_by_provider: GetItem by pk + sk
        - find_all_in_account: Query by pk with sk prefix "ProviderSettings#"
        - delete: DeleteItem by pk + sk
    """

    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, provider_settings: ProviderSettings) -> ProviderSettings:
        """
        Save provider settings (create or update).

        If settings exist for this provider, updates the existing record.
        Otherwise, creates a new record.
        """
        existing = self.find_by_provider(provider_settings.account_id, provider_settings.provider_name)

        if existing:
            # Update: preserve created_at, update updated_at
            provider_settings.created_at = existing.created_at
            provider_settings.updated_at = datetime.now(timezone.utc)

        self.table.put_item(Item=provider_settings.to_dynamo_item())
        log.info(f"Saved provider settings for {provider_settings.provider_name} in account {provider_settings.account_id}")
        return provider_settings

    def find_by_provider(self, account_id: str, provider_name: str) -> Optional[ProviderSettings]:
        """The account's settings for one provider (e.g. "Bedrock"), or None."""
        response = self.table.get_item(
            Key={
                "pk": f"Account#{account_id}",
                "sk": f"ProviderSettings#{provider_name}",
            }
        )
        item = response.get("Item")
        if item:
            return ProviderSettings.from_dynamo_item(item)
        return None

    def find_all_in_account(self, account_id: str) -> list[ProviderSettings]:
        """Every provider the account has configured."""
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"Account#{account_id}") & Key("sk").begins_with("ProviderSettings#")
        )

        items = response.get("Items", [])
        settings_list = [ProviderSettings.from_dynamo_item(item) for item in items]

        log.info(f"Found {len(settings_list)} provider settings in account {account_id}")
        return settings_list

    def delete(self, account_id: str, provider_name: str) -> bool:
        """
        Delete provider settings.

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            self.table.delete_item(
                Key={
                    "pk": f"Account#{account_id}",
                    "sk": f"ProviderSettings#{provider_name}",
                }
            )
            log.info(f"Deleted provider settings for {provider_name} in account {account_id}")
            return True
        except Exception as e:
            log.error(f"Failed to delete provider settings {provider_name}: {e}", exc_info=True)
            return False

def get_provider_settings_repository() -> ProviderSettingsRepository:
    """Dependency for ProviderSettingsRepository"""
    return ProviderSettingsRepository()


class Agent2AgentSettingsRepository:
    """
    Repository for the account's Agent2Agent outbound trust settings.

    Key Structure:
        pk: Account#{account_id}
        sk: Agent2AgentSettings
    """

    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, a2a_settings: Agent2AgentSettings) -> Agent2AgentSettings:
        existing = self.find_in_account(a2a_settings.account_id)
        if existing:
            a2a_settings.created_at = existing.created_at
            a2a_settings.updated_at = datetime.now(timezone.utc)

        self.table.put_item(Item=a2a_settings.to_dynamo_item())
        log.info("Saved Agent2Agent settings for account %s", a2a_settings.account_id)
        return a2a_settings

    def find_in_account(self, account_id: str) -> Optional[Agent2AgentSettings]:
        response = self.table.get_item(
            Key={
                "pk": f"Account#{account_id}",
                "sk": "Agent2AgentSettings",
            }
        )
        item = response.get("Item")
        return Agent2AgentSettings.from_dynamo_item(item) if item else None


def get_agent2agent_settings_repository() -> Agent2AgentSettingsRepository:
    return Agent2AgentSettingsRepository()


class DefaultAgentPreferenceRepository:
    """
    Repository for a member's default-agent preference.

    Key Structure:
        pk: Account#{account_id}#Member#{user_id}
        sk: DefaultAgentPreference
    """

    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, preference: DefaultAgentPreference) -> DefaultAgentPreference:
        existing = self.find_for_member(preference.account_id, preference.user_id)
        if existing:
            preference.created_at = existing.created_at
            preference.updated_at = datetime.now(timezone.utc)

        self.table.put_item(Item=preference.to_dynamo_item())
        log.info("Saved default agent preference for member %s", preference.user_id)
        return preference

    def find_for_member(self, account_id: str, user_id: str) -> Optional[DefaultAgentPreference]:
        response = self.table.get_item(
            Key={
                "pk": member_partition(account_id, user_id),
                "sk": "DefaultAgentPreference",
            }
        )
        item = response.get("Item")
        return DefaultAgentPreference.from_dynamo_item(item) if item else None

    def delete(self, account_id: str, user_id: str) -> None:
        self.table.delete_item(
            Key={
                "pk": member_partition(account_id, user_id),
                "sk": "DefaultAgentPreference",
            }
        )
        log.info("Cleared default agent preference for member %s", user_id)


def get_default_agent_preference_repository() -> DefaultAgentPreferenceRepository:
    return DefaultAgentPreferenceRepository()
