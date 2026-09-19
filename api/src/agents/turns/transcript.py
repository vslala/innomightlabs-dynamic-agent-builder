"""The replayable record of one chat turn's SSE events.

See api/docs/LLD-async-chat-turns.md ("1. TurnTranscript") for why this is a
separate module from `src.agents.turn_runtime.AgentTurnRuntime`: that runtime is
a single-consumer, consume-once, bounded queue scoped to one agentic-loop call.
A transcript is multi-consumer, retain-and-replay, and outlives the request
that started the turn.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import AsyncIterator

from src.agents.turn_runtime import is_droppable_runtime_event
from src.llm.events import SSEEvent, SSEEventType

log = logging.getLogger(__name__)


@dataclass
class TurnTranscript:
    """The ordered record of everything one agent turn said, replayable from any point."""

    turn_id: str
    events: list[SSEEvent] = field(default_factory=list)
    finished: bool = False
    task: "asyncio.Task[None] | None" = None
    _arrival: asyncio.Event = field(default_factory=asyncio.Event, repr=False)

    def record(self, event: SSEEvent) -> None:
        """Append an event. Synchronous and unbounded — must never block the turn."""
        if event.event_type == SSEEventType.IMAGE_GENERATION_COMPLETE:
            self._blank_superseded_partials()
        self.events.append(event)
        self._wake()

    def finish(self) -> None:
        """Mark the turn done. Every in-progress `follow()` call returns after this."""
        self.finished = True
        self._wake()

    async def follow(self, *, after_sequence: int = 0) -> AsyncIterator[tuple[int, SSEEvent]]:
        """Replay events after `after_sequence`, then keep yielding new ones until `finish()`."""
        cursor = max(after_sequence, 0)
        while True:
            arrival = self._arrival
            while cursor < len(self.events):
                cursor += 1
                yield cursor, self.events[cursor - 1]
            if self.finished:
                return
            await arrival.wait()

    def _blank_superseded_partials(self) -> None:
        for index, event in enumerate(self.events):
            if is_droppable_runtime_event(event) and event.image_b64 is not None:
                self.events[index] = event.model_copy(update={"image_b64": None})

    def _wake(self) -> None:
        waiters, self._arrival = self._arrival, asyncio.Event()
        waiters.set()


_transcripts: dict[str, TurnTranscript] = {}


def open_transcript(turn_id: str) -> TurnTranscript:
    transcript = TurnTranscript(turn_id=turn_id)
    _transcripts[turn_id] = transcript
    return transcript


def live_transcript(turn_id: str) -> TurnTranscript | None:
    return _transcripts.get(turn_id)


def forget_transcript(turn_id: str) -> None:
    _transcripts.pop(turn_id, None)
