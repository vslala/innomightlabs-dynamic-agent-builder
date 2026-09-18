import asyncio
from datetime import datetime, timezone
from typing import AsyncIterator, cast

import pytest
from pydantic import ValidationError

from src.dream.planner import MAX_PARSE_ATTEMPTS, DreamPlanner
from src.dream.sessions import DreamSession, DreamSessionChunk
from src.llm.providers.base import LLMEvent, LLMProvider
from src.memory.models import CoreMemory, MemoryBlockDefinition
from src.messages.models import Message


class FakeProvider:
    def __init__(self, events: list[LLMEvent]) -> None:
        self.events = events
        self.calls: list[tuple[list[dict], dict, object, str | None]] = []

    async def stream_response(
        self,
        messages: list[dict],
        credentials: dict,
        tools: object = None,
        model: str | None = None,
    ) -> AsyncIterator[LLMEvent]:
        self.calls.append((messages, credentials, tools, model))
        for event in self.events:
            yield event


def dream_chunk() -> DreamSessionChunk:
    message = Message(
        message_id="message-1",
        conversation_id="conversation-1",
        role="user",
        content="I prefer concise answers.",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )
    session = DreamSession("conversation-1", "Preferences", [message])
    return DreamSessionChunk(session, index=0, total=1, messages=[message], granularity="session")


def memory_blocks() -> tuple[list[MemoryBlockDefinition], list[CoreMemory]]:
    return (
        [MemoryBlockDefinition(agent_id="agent-1", user_id="user-1", block_name="human", description="User facts")],
        [CoreMemory(agent_id="agent-1", user_id="user-1", block_name="human", lines=["Uses Python"] )],
    )


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "response",
    [
        'Here is the plan:\n{"actions": [], "session_summary": "Captured preference."}\nThanks.',
        '```json\n{"actions": [], "session_summary": "Captured preference."}\n```',
    ],
)
async def test_plan_extracts_strict_json_from_prose_or_code_fence(response: str) -> None:
    provider = FakeProvider([LLMEvent(type="text", content=response)])
    blocks, memories = memory_blocks()

    result = await DreamPlanner().plan(
        provider=cast(LLMProvider, provider),
        credentials={"token": "test"},
        model_name="dream-model",
        chunk=dream_chunk(),
        block_definitions=blocks,
        core_memories=memories,
    )

    assert result.plan.session_summary == "Captured preference."
    assert result.plan.actions == []
    assert provider.calls[0][2] is None
    assert provider.calls[0][3] == "dream-model"


@pytest.mark.asyncio
async def test_plan_rejects_malformed_response_without_json_object() -> None:
    provider = FakeProvider([LLMEvent(type="text", content="I cannot produce a plan today.")])
    blocks, memories = memory_blocks()

    with pytest.raises(ValueError, match="JSON object"):
        await DreamPlanner().plan(
            provider=cast(LLMProvider, provider),
            credentials={},
            model_name="dream-model",
            chunk=dream_chunk(),
            block_definitions=blocks,
            core_memories=memories,
        )


@pytest.mark.asyncio
async def test_plan_accumulates_usage_events_across_the_stream() -> None:
    provider = FakeProvider(
        [
            LLMEvent(type="usage", prompt_tokens=10, completion_tokens=2),
            LLMEvent(type="text", content='{"actions": [], '),
            LLMEvent(type="usage", prompt_tokens=7, completion_tokens=5),
            LLMEvent(type="text", content='"session_summary": "done"}'),
        ]
    )
    blocks, memories = memory_blocks()

    result = await DreamPlanner().plan(
        provider=cast(LLMProvider, provider),
        credentials={},
        model_name="dream-model",
        chunk=dream_chunk(),
        block_definitions=blocks,
        core_memories=memories,
    )

    assert result.plan.session_summary == "done"
    assert (result.prompt_tokens, result.completion_tokens) == (17, 7)


class SequencedProvider:
    """Returns a different canned response on each successive call, to test retries."""

    def __init__(self, responses: list[list[LLMEvent]]) -> None:
        self.responses = responses
        self.call_count = 0

    async def stream_response(self, *args, **kwargs) -> AsyncIterator[LLMEvent]:
        events = self.responses[self.call_count]
        self.call_count += 1
        for event in events:
            yield event


@pytest.mark.asyncio
async def test_plan_ignores_json_like_fragments_inside_a_think_block() -> None:
    """Reproduces a real Qwen3 response: reasoning wrapped in <think> mentions a JSON-shaped
    tool-call fragment before the actual answer. Naive "first { to last }" extraction used to
    span both and fail with a "trailing characters" error; this must succeed on the first try."""
    provider = FakeProvider(
        [
            LLMEvent(
                type="text",
                content=(
                    "<think>\n"
                    'Maybe I should call {"action": "reset_thread"} but the instructions say JSON only.\n'
                    "</think>\n"
                    '{"actions": [], "session_summary": "Captured preference."}'
                ),
            )
        ]
    )
    blocks, memories = memory_blocks()

    result = await DreamPlanner().plan(
        provider=cast(LLMProvider, provider),
        credentials={},
        model_name="dream-model",
        chunk=dream_chunk(),
        block_definitions=blocks,
        core_memories=memories,
    )

    assert result.plan.session_summary == "Captured preference."
    assert len(provider.calls) == 1


@pytest.mark.asyncio
async def test_plan_retries_after_malformed_json_then_succeeds() -> None:
    provider = SequencedProvider(
        [
            [LLMEvent(type="text", content='{"actions": [}')],  # unbalanced bracket: invalid JSON
            [LLMEvent(type="text", content='{"actions": [], "session_summary": "done on retry"}')],
        ]
    )
    blocks, memories = memory_blocks()

    result = await DreamPlanner().plan(
        provider=cast(LLMProvider, provider),
        credentials={},
        model_name="dream-model",
        chunk=dream_chunk(),
        block_definitions=blocks,
        core_memories=memories,
    )

    assert result.plan.session_summary == "done on retry"
    assert provider.call_count == 2


@pytest.mark.asyncio
async def test_plan_gives_up_after_max_parse_attempts_and_raises_last_error() -> None:
    provider = SequencedProvider([[LLMEvent(type="text", content='{"actions": [}')]] * MAX_PARSE_ATTEMPTS)
    blocks, memories = memory_blocks()

    with pytest.raises(ValidationError):
        await DreamPlanner().plan(
            provider=cast(LLMProvider, provider),
            credentials={},
            model_name="dream-model",
            chunk=dream_chunk(),
            block_definitions=blocks,
            core_memories=memories,
        )

    assert provider.call_count == MAX_PARSE_ATTEMPTS


class StallingProvider:
    """Never yields, simulating a connection the provider keeps open but sends nothing on."""

    async def stream_response(self, *args, **kwargs) -> AsyncIterator[LLMEvent]:
        await asyncio.Event().wait()
        yield LLMEvent(type="stop")  # pragma: no cover - unreachable, satisfies generator typing


class SlowButProgressingProvider:
    """Sends events slower than the stall timeout, but never goes quiet for that long."""

    def __init__(self, events: list[LLMEvent], *, delay_seconds: float) -> None:
        self.events = events
        self.delay_seconds = delay_seconds

    async def stream_response(self, *args, **kwargs) -> AsyncIterator[LLMEvent]:
        for event in self.events:
            await asyncio.sleep(self.delay_seconds)
            yield event


@pytest.mark.asyncio
async def test_plan_raises_when_the_provider_goes_quiet_mid_stream() -> None:
    blocks, memories = memory_blocks()

    with pytest.raises(TimeoutError, match="received no data"):
        await DreamPlanner().plan(
            provider=cast(LLMProvider, StallingProvider()),
            credentials={},
            model_name="dream-model",
            chunk=dream_chunk(),
            block_definitions=blocks,
            core_memories=memories,
            stall_timeout_seconds=0.01,
        )


@pytest.mark.asyncio
async def test_plan_does_not_time_out_a_response_that_keeps_actively_streaming() -> None:
    blocks, memories = memory_blocks()
    events = [
        LLMEvent(type="text", content='{"actions": [], '),
        LLMEvent(type="text", content='"session_summary": "done"}'),
    ]
    provider = SlowButProgressingProvider(events, delay_seconds=0.02)

    result = await DreamPlanner().plan(
        provider=cast(LLMProvider, provider),
        credentials={},
        model_name="dream-model",
        chunk=dream_chunk(),
        block_definitions=blocks,
        core_memories=memories,
        # Each individual gap (0.02s) is under the stall timeout even though the
        # call's total duration (0.04s) exceeds it — proves this is not a flat cap.
        stall_timeout_seconds=0.03,
    )

    assert result.plan.session_summary == "done"
