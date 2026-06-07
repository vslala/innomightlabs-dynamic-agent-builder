from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from boto3.dynamodb.conditions import Key

from src.config import settings
from src.connectors.mcp.models import AgentMCPConnection, MCPConnection
from src.db import get_dynamodb_resource

log = logging.getLogger(__name__)


class MCPConnectionRepository:
    """DynamoDB single-table repository for MCP connector configuration."""

    def __init__(self):
        self.dynamodb = get_dynamodb_resource()
        self.table = self.dynamodb.Table(settings.dynamodb_table)

    def save_connection(self, connection: MCPConnection) -> MCPConnection:
        existing = self.find_connection(connection.owner_email, connection.mcp_id)
        if existing:
            connection.created_at = existing.created_at
            connection.updated_at = datetime.now(timezone.utc)
        self.table.put_item(Item=connection.to_dynamo_item())
        log.info("Saved MCP connection %s for user %s", connection.mcp_id, connection.owner_email)
        return connection

    def find_connection(self, owner_email: str, mcp_id: str) -> Optional[MCPConnection]:
        response = self.table.get_item(
            Key={"pk": f"User#{owner_email}", "sk": f"MCPConnection#{mcp_id}"}
        )
        item = response.get("Item")
        return MCPConnection.from_dynamo_item(item) if item else None

    def list_connections(self, owner_email: str) -> list[MCPConnection]:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"User#{owner_email}")
            & Key("sk").begins_with("MCPConnection#")
        )
        return [MCPConnection.from_dynamo_item(item) for item in response.get("Items", [])]

    def delete_connection(self, owner_email: str, mcp_id: str) -> None:
        self.table.delete_item(
            Key={"pk": f"User#{owner_email}", "sk": f"MCPConnection#{mcp_id}"}
        )
        log.info("Deleted MCP connection %s for user %s", mcp_id, owner_email)

    def save_agent_connection(self, link: AgentMCPConnection) -> AgentMCPConnection:
        existing = self.find_agent_connection(link.agent_id, link.mcp_id)
        if existing:
            link.created_at = existing.created_at
            link.updated_at = datetime.now(timezone.utc)
        self.table.put_item(Item=link.to_dynamo_item())
        log.info("Saved MCP connection %s for agent %s", link.mcp_id, link.agent_id)
        return link

    def find_agent_connection(self, agent_id: str, mcp_id: str) -> Optional[AgentMCPConnection]:
        response = self.table.get_item(
            Key={"pk": f"Agent#{agent_id}", "sk": f"MCPConnection#{mcp_id}"}
        )
        item = response.get("Item")
        return AgentMCPConnection.from_dynamo_item(item) if item else None

    def list_agent_connections(self, agent_id: str) -> list[AgentMCPConnection]:
        response = self.table.query(
            KeyConditionExpression=Key("pk").eq(f"Agent#{agent_id}")
            & Key("sk").begins_with("MCPConnection#")
        )
        return [AgentMCPConnection.from_dynamo_item(item) for item in response.get("Items", [])]

    def delete_agent_connection(self, agent_id: str, mcp_id: str) -> None:
        self.table.delete_item(
            Key={"pk": f"Agent#{agent_id}", "sk": f"MCPConnection#{mcp_id}"}
        )
        log.info("Deleted MCP connection %s for agent %s", mcp_id, agent_id)


def get_mcp_connection_repository() -> MCPConnectionRepository:
    return MCPConnectionRepository()
