"""Every MCP call an agent makes, kept so its owner can see who uses their connectors and how.

A call is written twice: once as an audit row (newest first, expiring with the longest analytics window)
and once into a daily counter, so charts are a single range query instead of a scan over calls.
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field

from src.config import settings
from src.db import get_dynamodb_resource
from src.skills.models import ActorKind

RETENTION = timedelta(days=90)
MAX_ERROR_CHARS = 300
MAX_ARGUMENTS_PREVIEW_CHARS = 500


class MCPCall(BaseModel):
    call_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str
    mcp_id: str
    connection_name: str
    tool_name: str
    actor_kind: ActorKind
    actor_id: str
    actor_email: Optional[str] = None
    conversation_id: Optional[str] = None
    arguments_preview: str = ""
    success: bool
    error: Optional[str] = None
    duration_ms: int
    called_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def pk(self) -> str:
        return f"Agent#{self.agent_id}#MCPCalls"

    @property
    def sk(self) -> str:
        return f"{self.called_at.isoformat()}#{self.call_id}"

    @property
    def day(self) -> str:
        return self.called_at.date().isoformat()

    def to_dynamo_item(self) -> dict[str, Any]:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "entity_type": "MCPCall",
            **self.model_dump(mode="json"),
            "ttl": int((self.called_at + RETENTION).timestamp()),
        }

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "MCPCall":
        return cls.model_validate(item)


def arguments_preview(arguments: dict[str, Any]) -> str:
    """Enough of what was asked for an owner to recognise it. Credentials never travel in arguments."""
    return json.dumps(arguments, ensure_ascii=True, default=str)[:MAX_ARGUMENTS_PREVIEW_CHARS]


def reported_error(result: dict[str, Any]) -> Optional[str]:
    """MCP servers report a failed tool inside a successful response, as `isError` with text content."""
    if not result.get("isError"):
        return None
    texts = [part.get("text", "") for part in result.get("content", []) if isinstance(part, dict)]
    return (" ".join(texts).strip() or "The tool reported an error")[:MAX_ERROR_CHARS]


class MCPUsageRepository:
    def __init__(self) -> None:
        self.table = get_dynamodb_resource().Table(settings.dynamodb_table)

    def record(self, call: MCPCall) -> None:
        """Two plain writes, not a transaction: this is telemetry, and a missed count is not worth the cost."""
        self.table.put_item(Item=call.to_dynamo_item())
        self.table.update_item(
            Key={
                "pk": f"Agent#{call.agent_id}#MCPUsage",
                "sk": f"Day#{call.day}#{call.actor_kind.value}#{call.mcp_id}#{call.tool_name}",
            },
            UpdateExpression=(
                "SET calls = if_not_exists(calls, :zero) + :one, "
                "errors = if_not_exists(errors, :zero) + :failed, "
                "duration_ms_total = if_not_exists(duration_ms_total, :zero) + :duration_ms, "
                "#day = :day, actor_kind = :actor_kind, mcp_id = :mcp_id, tool_name = :tool_name, "
                "connection_name = :connection_name, entity_type = :entity_type"
            ),
            # DAY is a DynamoDB reserved word.
            ExpressionAttributeNames={"#day": "day"},
            ExpressionAttributeValues={
                ":zero": 0,
                ":one": 1,
                ":failed": 0 if call.success else 1,
                ":duration_ms": call.duration_ms,
                ":day": call.day,
                ":actor_kind": call.actor_kind.value,
                ":mcp_id": call.mcp_id,
                ":tool_name": call.tool_name,
                ":connection_name": call.connection_name,
                ":entity_type": "MCPDailyUsage",
            },
        )


def get_mcp_usage_repository() -> MCPUsageRepository:
    return MCPUsageRepository()
