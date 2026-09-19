"""Tool call audit records and the log that persists them."""

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

from src.llm.events import SSEEvent, SSEEventType
from src.messages.models import Message, MessageKind
from src.messages.repositories import MessageRepository

MAX_TOOL_RESULT_CHARS = 12000


class ToolCallAuditMessage(BaseModel):
    type: Literal["tool_call_audit"] = "tool_call_audit"
    tool_call_id: str
    sequence: int
    tool_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)
    result: str = ""
    success: bool
    started_at: datetime
    completed_at: datetime
    result_truncated: bool = False
    result_size_chars: int = 0


class ToolCallStart(BaseModel):
    sequence: int
    tool_name: str
    tool_args: dict[str, Any] = Field(default_factory=dict)
    started_at: datetime


def build_tool_call_audit_message(
    *,
    tool_call_id: str,
    sequence: int,
    tool_name: str,
    tool_args: dict[str, Any],
    result: str,
    success: bool,
    started_at: datetime,
) -> ToolCallAuditMessage:
    result_size = len(result)
    return ToolCallAuditMessage(
        tool_call_id=tool_call_id,
        sequence=sequence,
        tool_name=tool_name,
        tool_args=tool_args,
        result=result[:MAX_TOOL_RESULT_CHARS],
        success=success,
        started_at=started_at,
        completed_at=datetime.now(timezone.utc),
        result_size_chars=result_size,
        result_truncated=result_size > MAX_TOOL_RESULT_CHARS,
    )


@dataclass
class ToolCallAuditLog:
    """Persists one audit row per tool call, pairing each start with its result.

    Rows are written under the AUDIT# sort-key prefix, so they stay out of the
    conversation context and the message list -- see
    api/docs/LLD-agent-runtime-refactor.md (P0.1).
    """

    message_repo: MessageRepository
    conversation_id: str
    actor_email: str
    _sequence: int = 0
    _starts: dict[str, ToolCallStart] = field(default_factory=dict)

    def observe(self, event: SSEEvent) -> None:
        if event.event_type == SSEEventType.TOOL_CALL_START:
            self._sequence += 1
            self._starts[event.tool_call_id or ""] = ToolCallStart(
                sequence=self._sequence,
                tool_name=event.tool_name or "",
                tool_args=event.tool_args or {},
                started_at=datetime.now(timezone.utc),
            )
        elif event.event_type == SSEEventType.TOOL_CALL_RESULT:
            self._record_result(event)

    def _record_result(self, event: SSEEvent) -> None:
        start = self._starts.get(event.tool_call_id or "")
        if not start:
            return

        audit = build_tool_call_audit_message(
            tool_call_id=event.tool_call_id or "",
            sequence=start.sequence,
            tool_name=start.tool_name,
            tool_args=start.tool_args,
            result=event.content,
            success=bool(event.success),
            started_at=start.started_at,
        )
        self.message_repo.save(
            Message(
                conversation_id=self.conversation_id,
                created_by=self.actor_email,
                role="system",
                content=audit.model_dump_json(),
                kind=MessageKind.TOOL_AUDIT,
            )
        )
