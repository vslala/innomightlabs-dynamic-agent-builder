from datetime import datetime, timezone
from typing import AsyncIterator, cast

import pytest

from src.dream.planner import DreamPlanner
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
