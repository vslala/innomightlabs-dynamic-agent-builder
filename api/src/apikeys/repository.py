"""
Repository for AgentApiKey entity using DynamoDB single table design.
"""

import logging
from datetime import datetime, timezone
from typing import Optional

import boto3
from boto3.dynamodb.conditions import Key

from src.apikeys.models import AgentApiKey
from src.config import settings

log = logging.getLogger(__name__)


class ApiKeyRepository:
    """
    Repository for AgentApiKey entity using DynamoDB single table design.

    Key Structure:
        pk: Agent#{agent_id}
        sk: ApiKey#{key_id}

    GSI2 (for lookup by public key):
        gsi2_pk: ApiKey#{public_key}
        gsi2_sk: Agent#{agent_id}

    Access Patterns:
        - save: PutItem (create or update)
        - find_by_id: GetItem by pk + sk
        - find_by_public_key: Query GSI2 by gsi2_pk
        - find_all_by_agent: Query by pk with sk prefix "ApiKey#"
        - delete_by_id: DeleteItem by pk + sk
        - increment_request_count: UpdateItem to increment counter
    """

    GSI2_NAME = "gsi2"  # Must match the GSI name in DynamoDB

    def __init__(self) -> None:
        self.dynamodb = boto3.resource("dynamodb", region_name=settings.aws_region)
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, api_key: AgentApiKey) -> AgentApiKey:
        """
        Save an API key (create or update).

        If key exists, preserves created_at.
        """
        existing = self.find_by_id(api_key.agent_id, api_key.key_id)

        if existing:
            api_key.created_at = existing.created_at

        self.table.put_item(Item=api_key.to_dynamo_item())
        log.info(f"Saved API key {api_key.key_id} for agent {api_key.agent_id}")
        return api_key

    def find_by_id(self, agent_id: str, key_id: str) -> Optional[AgentApiKey]:
        """
        Find an API key by agent ID and key ID.

        Args:
            agent_id: The agent this key belongs to
            key_id: The unique key identifier

        Returns:
            AgentApiKey if found, None otherwise
        """
        response = self.table.get_item(
            Key={
                "pk": f"Agent#{agent_id}",
                "sk": f"ApiKey#{key_id}",
            }
        )
        item = response.get("Item")
        if item:
            return AgentApiKey.from_dynamo_item(item)
        return None

    def find_by_public_key(self, public_key: str) -> Optional[AgentApiKey]:
        """
        Find an API key by its public key (pk_live_xxx).

        Uses GSI2 for efficient lookup.

        Args:
            public_key: The public API key string

        Returns:
            AgentApiKey if found, None otherwise
        """
        response = self.table.query(
            IndexName=self.GSI2_NAME,
            KeyConditionExpression=Key("gsi2_pk").eq(f"ApiKey#{public_key}"),
        )
        items = response.get("Items", [])
        if items:
            return AgentApiKey.from_dynamo_item(items[0])
        return None

    def find_all_by_agent(self, agent_id: str) -> list[AgentApiKey]:
        """
        Find all API keys for a specific agent.

        Args:
            agent_id: The agent ID

        Returns:
            List of API keys for the agent
        """
        response = self.table.query(
            KeyConditionExpression=(
                Key("pk").eq(f"Agent#{agent_id}") &
                Key("sk").begins_with("ApiKey#")
            )
        )

        items = response.get("Items", [])
        keys = [AgentApiKey.from_dynamo_item(item) for item in items]

        log.info(f"Found {len(keys)} API keys for agent {agent_id}")
        return keys

    def delete_by_id(self, agent_id: str, key_id: str) -> bool:
        """
        Delete an API key by ID.

        Args:
            agent_id: The agent this key belongs to
            key_id: The unique key identifier

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            self.table.delete_item(
                Key={
                    "pk": f"Agent#{agent_id}",
                    "sk": f"ApiKey#{key_id}",
                }
            )
            log.info(f"Deleted API key {key_id} for agent {agent_id}")
            return True
        except Exception as e:
            log.error(f"Failed to delete API key {key_id}: {e}", exc_info=True)
            return False

    def increment_request_count(self, agent_id: str, key_id: str) -> None:
        """
        Increment the request count and update last_used_at.

        This is called when an API key is used to make a request.
        Uses atomic counter update for accuracy.

        Args:
            agent_id: The agent this key belongs to
            key_id: The unique key identifier
        """
        try:
            self.table.update_item(
                Key={
                    "pk": f"Agent#{agent_id}",
                    "sk": f"ApiKey#{key_id}",
                },
                UpdateExpression="SET request_count = request_count + :inc, last_used_at = :now",
                ExpressionAttributeValues={
                    ":inc": 1,
                    ":now": datetime.now(timezone.utc).isoformat(),
                },
            )
        except Exception as e:
            log.error(f"Failed to increment request count for key {key_id}: {e}", exc_info=True)

    def delete_all_by_agent(self, agent_id: str) -> int:
        """
        Delete all API keys for an agent.

        Used when an agent is deleted.

        Args:
            agent_id: The agent ID

        Returns:
            Number of keys deleted
        """
        keys = self.find_all_by_agent(agent_id)
        deleted = 0

        for api_key in keys:
            if self.delete_by_id(agent_id, api_key.key_id):
                deleted += 1

        log.info(f"Deleted {deleted} API keys for agent {agent_id}")
        return deleted
