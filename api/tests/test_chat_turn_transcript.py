from __future__ import annotations

import asyncio

from src.agents.turns.transcript import TurnTranscript
from src.llm.events import SSEEvent, SSEEventType


def _text_event(content: str) -> SSEEvent:
    return SSEEvent(event_type=SSEEventType.AGENT_RESPONSE_TO_USER, content=content)


async def test_follower_receives_events_in_order_then_returns_on_finish():
    transcript = TurnTranscript(turn_id="turn-1")
    received: list[tuple[int, str]] = []

    async def consumer():
        async for sequence, event in transcript.follow():
            received.append((sequence, event.content))

    consumer_task = asyncio.create_task(consumer())
    await asyncio.sleep(0)

    for i in range(3):
        transcript.record(_text_event(str(i)))
        await asyncio.sleep(0)
    transcript.finish()

    await asyncio.wait_for(consumer_task, timeout=2)
    assert received == [(1, "0"), (2, "1"), (3, "2")]


async def test_follower_attaching_after_finish_replays_everything_and_terminates():
    transcript = TurnTranscript(turn_id="turn-1")
    for i in range(3):
        transcript.record(_text_event(str(i)))
    transcript.finish()

    received = [(seq, event.content) async for seq, event in transcript.follow()]

    assert received == [(1, "0"), (2, "1"), (3, "2")]


async def test_two_followers_at_different_cursors_each_get_full_sequence():
    transcript = TurnTranscript(turn_id="turn-1")
    early_received: list[int] = []
    late_received: list[int] = []

    async def early_follower():
        async for sequence, _event in transcript.follow():
            early_received.append(sequence)

    early_task = asyncio.create_task(early_follower())
    await asyncio.sleep(0)

    transcript.record(_text_event("0"))
    transcript.record(_text_event("1"))
    await asyncio.sleep(0)

    async def late_follower():
        async for sequence, _event in transcript.follow(after_sequence=0):
            late_received.append(sequence)

    late_task = asyncio.create_task(late_follower())
    await asyncio.sleep(0)

    transcript.record(_text_event("2"))
    transcript.finish()

    await asyncio.wait_for(asyncio.gather(early_task, late_task), timeout=2)
    assert early_received == [1, 2, 3]
    assert late_received == [1, 2, 3]


async def test_slow_subscriber_never_blocks_producer():
    transcript = TurnTranscript(turn_id="turn-1")
    received: list[int] = []

    async def slow_follower():
        async for sequence, _event in transcript.follow():
            received.append(sequence)
            if sequence == 1:
                await asyncio.sleep(0.05)

    follower_task = asyncio.create_task(slow_follower())
    await asyncio.sleep(0)

    transcript.record(_text_event("first"))
    for _ in range(999):
        transcript.record(_text_event("x"))
    transcript.finish()

    await asyncio.wait_for(follower_task, timeout=2)
    assert received == list(range(1, 1001))


async def test_after_sequence_yields_exact_range_with_no_gap_or_repeat():
    transcript = TurnTranscript(turn_id="turn-1")
    for i in range(5):
        transcript.record(_text_event(str(i)))
    transcript.finish()

    sequences = [sequence async for sequence, _event in transcript.follow(after_sequence=2)]

    assert sequences == [3, 4, 5]


async def test_image_generation_complete_blanks_earlier_partial_image_b64():
    transcript = TurnTranscript(turn_id="turn-1")
    transcript.record(
        SSEEvent(
            event_type=SSEEventType.IMAGE_GENERATION_PARTIAL,
            content="",
            image_b64="partial-bytes",
        )
    )
    transcript.record(
        SSEEvent(
            event_type=SSEEventType.IMAGE_GENERATION_COMPLETE,
            content="",
            image_b64="final-bytes",
        )
    )

    assert len(transcript.events) == 2
    assert transcript.events[0].image_b64 is None
    assert transcript.events[1].image_b64 == "final-bytes"
