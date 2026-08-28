from ..db import get_dynamodb_resource
from boto3.dynamodb.conditions import Key, Attr
from datetime import datetime, timezone
from typing import Any, Optional
import logging

from pydantic import BaseModel, Field

from src.agents.models import Agent
from src.config import settings

log = logging.getLogger(__name__)


class AgentPage(BaseModel):
    items: list[Agent] = Field(default_factory=list)
    cursor: dict[str, Any] | None = None


class AgentRepository:
    """
    Repository for Agent entity using DynamoDB single table design.

    Key Structure:
        pk: User#{created_by_email}  - Partition by user for efficient queries
        sk: Agent#{agent_id}         - Unique agent identifier

    Access Patterns:
        - save: PutItem (create or update)
        - find_agent_by_id: GetItem by pk + sk
        - find_all_by_created_by: Query by pk with sk prefix "Agent#"
        - delete_by_id: DeleteItem by pk + sk
    """

    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, agent: Agent) -> Agent:
        """
        Save an agent (create or update).

        If agent_id exists, updates the existing record.
        Otherwise, creates a new record.
        """
        existing = self.find_agent_by_id(agent.agent_id, agent.created_by)

        if existing:
            # Update: preserve created_at, update updated_at
            agent.created_at = existing.created_at
            agent.updated_at = datetime.now(timezone.utc)

        self.table.put_item(Item=agent.to_dynamo_item())
        log.info(f"Saved agent {agent.agent_id} for user {agent.created_by}")
        return agent

    def find_agent_by_id(self, agent_id: str, created_by: str) -> Optional[Agent]:
        """
        Find an agent by ID and creator email.

        Args:
            agent_id: The unique agent identifier
            created_by: The email of the user who created the agent

        Returns:
            Agent if found, None otherwise
        """
        response = self.table.get_item(
            Key={
                "pk": f"User#{created_by}",
                "sk": f"Agent#{agent_id}",
            }
        )
        item = response.get("Item")
        if item:
            return Agent.from_dynamo_item(item)
        return None

    def find_all_by_created_by(self, created_by: str) -> list[Agent]:
        """
        Find all agents created by a specific user.

        Args:
            created_by: The email of the user

        Returns:
            List of agents created by the user
        """
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"User#{created_by}") & Key("sk").begins_with("Agent#")
        )

        items = response.get("Items", [])
        agents = [Agent.from_dynamo_item(item) for item in items]

        log.info(f"Found {len(agents)} agents for user {created_by}")
        return agents

    def list_agent2agent_enabled(
        self,
        *,
        limit: int = 50,
        cursor: Optional[dict] = None,
    ) -> AgentPage:
        """
        List agents enabled for public Agent2Agent discovery.

        V1 intentionally scans Agent rows to avoid duplicating agent metadata or
        adding pointer items. If discovery volume grows, replace this with a GSI
        on the Agent row keyed by is_agent2agent_enabled.
        """
        bounded_limit = max(1, min(limit, 100))
        agents: list[Agent] = []
        exclusive_start_key = cursor

        while len(agents) < bounded_limit:
            scan_kwargs = {
                "FilterExpression": Attr("entity_type").eq("Agent")
                & Attr("is_agent2agent_enabled").eq(True),
                "Limit": bounded_limit,
            }
            if exclusive_start_key:
                scan_kwargs["ExclusiveStartKey"] = exclusive_start_key

            response = self.table.scan(**scan_kwargs)
            agents.extend(
                Agent.from_dynamo_item(item)
                for item in response.get("Items", [])
            )
            exclusive_start_key = response.get("LastEvaluatedKey")
            if not exclusive_start_key:
                break

        return AgentPage(items=agents[:bounded_limit], cursor=exclusive_start_key)

    def find_agent2agent_enabled_by_id(self, agent_id: str) -> Optional[Agent]:
        """Find a single A2A-enabled agent by id using the v1 scan-based discovery path."""
        exclusive_start_key = None
        while True:
            scan_kwargs = {
                "FilterExpression": Attr("entity_type").eq("Agent")
                & Attr("is_agent2agent_enabled").eq(True)
                & Attr("agent_id").eq(agent_id),
                "Limit": 100,
            }
            if exclusive_start_key:
                scan_kwargs["ExclusiveStartKey"] = exclusive_start_key

            response = self.table.scan(**scan_kwargs)
            items = response.get("Items", [])
            if items:
                return Agent.from_dynamo_item(items[0])

            exclusive_start_key = response.get("LastEvaluatedKey")
            if not exclusive_start_key:
                return None

    def find_by_name(self, agent_name: str, created_by: str) -> Optional[Agent]:
        """
        Find an agent by name for a specific user.

        Used for idempotency check - agent_name is unique per user.

        Args:
            agent_name: The name of the agent
            created_by: The email of the user who created the agent

        Returns:
            Agent if found, None otherwise
        """
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"User#{created_by}") & Key("sk").begins_with("Agent#"),
            FilterExpression=Attr("agent_name").eq(agent_name)
        )

        items = response.get("Items", [])
        if items:
            return Agent.from_dynamo_item(items[0])
        return None

    def delete_by_id(self, agent_id: str, created_by: str) -> bool:
        """
        Delete an agent by ID.

        Args:
            agent_id: The unique agent identifier
            created_by: The email of the user who created the agent

        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            self.table.delete_item(
                Key={
                    "pk": f"User#{created_by}",
                    "sk": f"Agent#{agent_id}",
                }
            )
            log.info(f"Deleted agent {agent_id} for user {created_by}")
            return True
        except Exception as e:
            log.error(f"Failed to delete agent {agent_id}: {e}", exc_info=True)
            return False
