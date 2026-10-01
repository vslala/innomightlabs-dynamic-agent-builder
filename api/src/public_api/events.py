"""The public /v1 stream contract, mapped from internal agent events.

Internal SSEEvent types are free to change; these event names and payloads are
not. Internal types without a mapping (thoughts, lifecycle notices, token
aggregates, images, canvases, forms) are not part of the public stream.
"""

import json
from typing import Any, AsyncIterator, Callable

from src.agents.architectures.base import AgentInvocationResult
from src.agents.turns.transcript import TurnTranscript
from src.llm.events import SSEEvent, SSEEventType

PublicEvent = tuple[str, dict[str, Any]]

_PUBLIC_EVENTS: dict[SSEEventType, Callable[[SSEEvent], PublicEvent]] = {
    SSEEventType.USER_MESSAGE_SAVED: lambda e: ("message.created", {"message_id": e.message_id, "role": "user"}),
    SSEEventType.AGENT_RESPONSE_TO_USER: lambda e: ("message.delta", {"text": e.content}),
    SSEEventType.TOOL_CALL_START: lambda e: (
        "tool.started",
        {"tool_call_id": e.tool_call_id, "name": e.display_tool_name or e.tool_name},
    ),
    SSEEventType.TOOL_CALL_RESULT: lambda e: ("tool.completed", {"tool_call_id": e.tool_call_id, "success": e.success}),
    SSEEventType.ASSISTANT_MESSAGE_SAVED: lambda e: (
        "message.completed",
        {"message_id": e.message_id, "role": "assistant"},
    ),
    SSEEventType.ERROR: lambda e: ("error", {"message": e.content}),
    SSEEventType.STREAM_COMPLETE: lambda e: ("done", {}),
}


def to_public_event(event: SSEEvent) -> PublicEvent | None:
    to_public = _PUBLIC_EVENTS.get(event.event_type)
    return to_public(event) if to_public else None


async def stream_public_events(transcript: TurnTranscript) -> AsyncIterator[str]:
    async for sequence, event in transcript.follow():
        public = to_public_event(event)
        if public:
            name, data = public
            yield f"id: {sequence}\nevent: {name}\ndata: {json.dumps(data)}\n\n"


async def collect_invocation(transcript: TurnTranscript) -> AgentInvocationResult:
    """Wait for the turn to finish and return its buffered result."""
    result = AgentInvocationResult()
    async for _, event in transcript.follow():
        result.add(event)
    return result
