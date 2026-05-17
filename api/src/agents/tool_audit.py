"""Tool call audit message helpers."""

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, Field

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
