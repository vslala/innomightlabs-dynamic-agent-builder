"""
SSE Event types and models for streaming responses.
"""

from enum import Enum
from typing import Optional

from pydantic import BaseModel


class SSEEventType(str, Enum):
    """Event types for Server-Sent Events streaming."""

    # Lifecycle events
    LIFECYCLE_NOTIFICATION = "LIFECYCLE_NOTIFICATION"

    # Response events
    AGENT_RESPONSE_TO_USER = "AGENT_RESPONSE_TO_USER"
    AGENT_THOUGHTS = "AGENT_THOUGHTS"

    # UI events
    UI_FORM_RENDER = "UI_FORM_RENDER"

    # Tool call events (for memGPT timeline)
    TOOL_CALL_START = "TOOL_CALL_START"
    TOOL_CALL_RESULT = "TOOL_CALL_RESULT"

    # Status events
    MESSAGE_SAVED = "MESSAGE_SAVED"
    STREAM_COMPLETE = "STREAM_COMPLETE"

    # Error event
    ERROR = "ERROR"


class SSEEvent(BaseModel):
    """Server-Sent Event model."""

    event_type: SSEEventType
    content: str
    message_id: Optional[str] = None

    # Tool call event fields (for memGPT timeline)
    tool_name: Optional[str] = None
    tool_args: Optional[dict] = None
    success: Optional[bool] = None

    # UI events
    form: Optional[dict] = None
    submit_label: Optional[str] = None
    form_id: Optional[str] = None
    form_label: Optional[str] = None

    def to_sse(self) -> str:
        """
        Format as SSE data line.

        Returns a properly formatted SSE data string with double newline.
        """
        return f"data: {self.model_dump_json()}\n\n"
