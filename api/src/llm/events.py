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

    # Status events
    MESSAGE_SAVED = "MESSAGE_SAVED"
    STREAM_COMPLETE = "STREAM_COMPLETE"

    # Error event
    ERROR = "ERROR"


class SSEEvent(BaseModel):
    """
    Server-Sent Event model.

    This model represents a single SSE event that can be streamed to the client.
    The event_type determines how the frontend should handle the event.
    """

    event_type: SSEEventType
    content: str
    message_id: Optional[str] = None

    def to_sse(self) -> str:
        """
        Format as SSE data line.

        Returns a properly formatted SSE data string with double newline.
        """
        return f"data: {self.model_dump_json()}\n\n"
