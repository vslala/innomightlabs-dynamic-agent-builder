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
        pk: Account#{account_id}   the account, which shares agents among its members
        sk: Agent#{agent_id}
        gsi2: Agent#{agent_id} / Agent   agent ids are global, so credentials, schedules and
              automations find an agent by id alone and act as its account and owner

    Finding an agent is not authorizing its use: dashboard routes check the caller's permissions
    (`principal.require`), credentials are bound to the agent they were issued for.
    """

    GSI2_NAME = "gsi2"

    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save(self, agent: Agent) -> Agent:
        """Create or update; an update keeps the original created_at."""
        existing = self.find_in_account(agent.account_id, agent.agent_id)
        if existing:
            agent.created_at = existing.created_at
            agent.updated_at = datetime.now(timezone.utc)

        self.table.put_item(Item=agent.to_dynamo_item())
        log.info(f"Saved agent {agent.agent_id} in account {agent.account_id}")
        return agent

    def get(self, agent_id: str) -> Optional[Agent]:
        """The agent with this id, in whatever account. The index is eventually consistent: right after
        a write, read it in its account with `find_in_account`."""
        response = self.table.query(
            IndexName=self.GSI2_NAME,
            KeyConditionExpression=Key("gsi2_pk").eq(f"Agent#{agent_id}") & Key("gsi2_sk").eq("Agent"),
        )
        items = response.get("Items", [])
        return Agent.from_dynamo_item(items[0]) if items else None

    def find_in_account(self, account_id: str, agent_id: str) -> Optional[Agent]:
        item = self.table.get_item(Key={"pk": f"Account#{account_id}", "sk": f"Agent#{agent_id}"}).get("Item")
        return Agent.from_dynamo_item(item) if item else None

    def list_in_account(self, account_id: str) -> list[Agent]:
        """Every agent in the account, whoever owns it; callers filter to what the caller may see."""
        items: list[dict[str, Any]] = []
        query: dict[str, Any] = {
            "KeyConditionExpression": Key("pk").eq(f"Account#{account_id}") & Key("sk").begins_with("Agent#"),
        }
        while True:
            response = self.table.query(**query)
            items.extend(response.get("Items", []))
            if "LastEvaluatedKey" not in response:
                break
            query["ExclusiveStartKey"] = response["LastEvaluatedKey"]
        return [Agent.from_dynamo_item(item) for item in items]

    def list_owned(self, account_id: str, owner_id: str) -> list[Agent]:
        return [agent for agent in self.list_in_account(account_id) if agent.owner_id == owner_id]

    def find_by_name(self, account_id: str, owner_id: str, agent_name: str) -> Optional[Agent]:
        """Names are unique per owner within an account (creating an agent is idempotent on its name)."""
        return next((agent for agent in self.list_owned(account_id, owner_id) if agent.agent_name == agent_name), None)

    def delete(self, account_id: str, agent_id: str) -> bool:
        try:
            self.table.delete_item(Key={"pk": f"Account#{account_id}", "sk": f"Agent#{agent_id}"})
            log.info(f"Deleted agent {agent_id} from account {account_id}")
            return True
        except Exception as e:
            log.error(f"Failed to delete agent {agent_id}: {e}", exc_info=True)
            return False

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
