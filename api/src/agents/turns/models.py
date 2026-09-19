"""ConversationTurn domain model.

One turn tracks one call to `AgentArchitecture.handle_message(...)` running
outside the HTTP request that started it. See api/docs/LLD-async-chat-turns.md.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

from src.common import as_aware_utc
from src.utils.dynamodb import convert_decimals

CHAT_TURN_TTL_DAYS = 7


class ConversationTurnStatus(str, Enum):
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


TERMINAL_TURN_STATUSES = frozenset(
    {
        ConversationTurnStatus.SUCCEEDED,
        ConversationTurnStatus.FAILED,
        ConversationTurnStatus.CANCELLED,
    }
)


class ConversationTurnResponse(BaseModel):
    """What the SPA needs to reattach to a turn: identity and status only."""

    turn_id: str
    conversation_id: str
    agent_id: str
    status: ConversationTurnStatus
    created_at: datetime


class ConversationTurn(BaseModel):
    """A chat turn's liveness and outcome, decoupled from the SSE connection that started it."""

    turn_id: str = Field(default_factory=lambda: f"turn_{uuid4().hex}")
    conversation_id: str
    agent_id: str
    created_by: str
    status: ConversationTurnStatus = ConversationTurnStatus.RUNNING
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: datetime | None = None
    last_heartbeat_at: datetime | None = None
    completed_at: datetime | None = None
    ttl: int = Field(
        default_factory=lambda: int(
            (datetime.now(timezone.utc) + timedelta(days=CHAT_TURN_TTL_DAYS)).timestamp()
        )
    )

    @property
    def pk(self) -> str:
        return f"CONVERSATION#{self.conversation_id}"

    @property
    def sk(self) -> str:
        return f"TURN#{self.created_at.isoformat()}#{self.turn_id}"

    @property
    def gsi2_pk(self) -> str:
        return f"ConversationTurn#{self.turn_id}"

    @property
    def gsi2_sk(self) -> str:
        return f"ConversationTurn#{self.turn_id}"

    def is_stale(self, *, stale_after_seconds: int, now: datetime | None = None) -> bool:
        if self.status != ConversationTurnStatus.RUNNING:
            return False
        reference = self.last_heartbeat_at or self.started_at or self.created_at
        checked_at = now or datetime.now(timezone.utc)
        return (checked_at - as_aware_utc(reference)) > timedelta(seconds=stale_after_seconds)

    def to_dynamo_item(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload.update(
            {
                "pk": self.pk,
                "sk": self.sk,
                "gsi2_pk": self.gsi2_pk,
                "gsi2_sk": self.gsi2_sk,
                "entity_type": "ConversationTurn",
            }
        )
        return payload

    @classmethod
    def from_dynamo_item(cls, item: dict[str, Any]) -> "ConversationTurn":
        payload = convert_decimals(dict(item))
        for key in ("pk", "sk", "gsi2_pk", "gsi2_sk", "entity_type"):
            payload.pop(key, None)
        return cls(**payload)

    def to_response(self) -> ConversationTurnResponse:
        return ConversationTurnResponse(
            turn_id=self.turn_id,
            conversation_id=self.conversation_id,
            agent_id=self.agent_id,
            status=self.status,
            created_at=self.created_at,
        )
