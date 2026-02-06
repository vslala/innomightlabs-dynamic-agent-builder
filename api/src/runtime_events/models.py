"""Durable runtime event log for agent execution.

This is the backbone for the "waterfall" execution model:
- Every action (skill load, tool call, tool result, etc.) is persisted
- Context for the next loop iteration is rebuilt from these events

The SSE stream is the real-time view; RuntimeEvents are the durable truth.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


class RuntimeEventType(str, Enum):
    TURN_STARTED = "TURN_STARTED"
    TURN_FINISHED = "TURN_FINISHED"

    SKILLS_LIST_SHOWN = "SKILLS_LIST_SHOWN"
    SKILL_LOADED = "SKILL_LOADED"

    TOOL_CALL_REQUESTED = "TOOL_CALL_REQUESTED"
    TOOL_CALL_RESULT = "TOOL_CALL_RESULT"

    ERROR = "ERROR"


class RuntimeEvent(BaseModel):
    """A durable event emitted during a single agent execution."""

    event_id: str = Field(default_factory=lambda: str(uuid4()))
    agent_id: str
    conversation_id: str
    actor_id: str
    owner_email: str

    event_type: RuntimeEventType
    payload: dict[str, Any] = Field(default_factory=dict)

    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def pk(self) -> str:
        return f"Runtime#Agent#{self.agent_id}#Actor#{self.actor_id}#Conversation#{self.conversation_id}"

    @property
    def sk(self) -> str:
        return f"Event#{self.created_at.isoformat()}#{self.event_id}"

    def to_dynamo_item(self) -> dict:
        return {
            "pk": self.pk,
            "sk": self.sk,
            "event_id": self.event_id,
            "agent_id": self.agent_id,
            "conversation_id": self.conversation_id,
            "actor_id": self.actor_id,
            "owner_email": self.owner_email,
            "event_type": self.event_type.value,
            "payload": self.payload,
            "created_at": self.created_at.isoformat(),
            "entity_type": "RuntimeEvent",
        }

    @classmethod
    def from_dynamo_item(cls, item: dict) -> "RuntimeEvent":
        return cls(
            event_id=item["event_id"],
            agent_id=item["agent_id"],
            conversation_id=item["conversation_id"],
            actor_id=item["actor_id"],
            owner_email=item.get("owner_email", ""),
            event_type=RuntimeEventType(item["event_type"]),
            payload=item.get("payload", {}),
            created_at=datetime.fromisoformat(item["created_at"]),
        )


class RuntimeEventPage(BaseModel):
    items: list[RuntimeEvent]
    next_cursor: Optional[str] = None
    has_more: bool = False
