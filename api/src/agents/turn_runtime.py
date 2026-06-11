"""Turn-scoped runtime events for agent tool execution."""

from __future__ import annotations

import asyncio
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field
from uuid import uuid4

from src.llm.events import SSEEvent, SSEEventType

log = logging.getLogger(__name__)

_current_turn_runtime: ContextVar["AgentTurnRuntime | None"] = ContextVar(
    "current_agent_turn_runtime",
    default=None,
)


@dataclass
class AgentTurnRuntime:
    """Ambient runtime state for one streamed agent turn."""

    turn_id: str = field(default_factory=lambda: str(uuid4()))
    max_events: int = 100
    closed: bool = False

    def __post_init__(self) -> None:
        self.events: asyncio.Queue[SSEEvent] = asyncio.Queue(maxsize=self.max_events)

    async def emit(self, event: SSEEvent, *, droppable: bool = False) -> None:
        if self.closed:
            log.debug("Dropping runtime event for closed turn turn_id=%s event_type=%s", self.turn_id, event.event_type)
            return

        if droppable:
            try:
                self.events.put_nowait(event)
            except asyncio.QueueFull:
                log.debug("Dropping runtime event due to full queue turn_id=%s event_type=%s", self.turn_id, event.event_type)
            return

        await self.events.put(event)

    async def next_event(self) -> SSEEvent:
        return await self.events.get()

    def drain_available(self) -> list[SSEEvent]:
        drained: list[SSEEvent] = []
        while True:
            try:
                drained.append(self.events.get_nowait())
            except asyncio.QueueEmpty:
                return drained

    def close(self) -> None:
        self.closed = True


def current_turn_runtime() -> AgentTurnRuntime | None:
    return _current_turn_runtime.get()


async def emit_turn_event(event: SSEEvent, *, droppable: bool = False) -> None:
    runtime = current_turn_runtime()
    if not runtime:
        log.debug("No active agent turn runtime for event_type=%s", event.event_type)
        return
    await runtime.emit(event, droppable=droppable)


@contextmanager
def use_turn_runtime(runtime: AgentTurnRuntime):
    token = _current_turn_runtime.set(runtime)
    try:
        yield runtime
    finally:
        runtime.close()
        _current_turn_runtime.reset(token)


def is_droppable_runtime_event(event: SSEEvent) -> bool:
    return event.event_type == SSEEventType.IMAGE_GENERATION_PARTIAL
