import copy
from dataclasses import dataclass
from typing import Any

from src.agents.agentic_loop import (
    FINAL_SUMMARY_PROMPT,
    ITERATION_LIMIT_SUMMARY_PROMPT,
    POST_TOOL_CONTINUATION_PROMPT,
    TurnComplete,
    run_agentic_tool_loop,
)
from src.agents.runtime_state import AgentTurnState
from src.agents.turn_runtime import emit_turn_event
from src.agents.tool_execution import ToolExecutionOutcome
from src.llm.events import SSEEvent, SSEEventType
from src.skills.models import ActorKind


def _type(item):
    """The event type, or None for the loop's two control signals."""
    return getattr(item, "event_type", None)


@dataclass
class FakeProviderEvent:
    type: str
    content: str = ""
    tool_name: str = ""
    tool_input: dict[str, Any] | None = None
    tool_use_id: str = ""
    thought_signature: bytes | None = None
    prompt_tokens: int = 0
    completion_tokens: int = 0


class FakeProvider:
    def __init__(self):
        self.calls = 0

    async def stream_response(self, context, credentials, tools, model):
        self.calls += 1
        if self.calls == 1:
            yield FakeProviderEvent(
                type="tool_use",
                tool_name="lookup_customer",
                tool_input={"customer_id": "cus_123"},
                tool_use_id="tooluse_1",
            )
            yield FakeProviderEvent(type="usage", prompt_tokens=10, completion_tokens=5)
            yield FakeProviderEvent(type="stop")
            return

        yield FakeProviderEvent(type="text", content="done")
        yield FakeProviderEvent(type="usage", prompt_tokens=7, completion_tokens=3)
        yield FakeProviderEvent(type="stop")


@dataclass
class FakeDayRecord:
    llm_model: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    call_count: int


class FakeTokenUsageService:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []
        self._totals: dict[str, dict[str, int]] = {}

    def record_usage(self, *, owner_email, agent_id, llm_model, prompt_tokens, completion_tokens, api_key_id=None):
        self.calls.append(
            {
                "owner_email": owner_email,
                "agent_id": agent_id,
                "llm_model": llm_model,
                "prompt_tokens": prompt_tokens,
                "completion_tokens": completion_tokens,
            }
        )
        totals = self._totals.setdefault(
            llm_model, {"prompt_tokens": 0, "completion_tokens": 0, "call_count": 0}
        )
        totals["prompt_tokens"] += prompt_tokens
        totals["completion_tokens"] += completion_tokens
        totals["call_count"] += 1
        return FakeDayRecord(
            llm_model=llm_model,
            prompt_tokens=totals["prompt_tokens"],
            completion_tokens=totals["completion_tokens"],
            total_tokens=totals["prompt_tokens"] + totals["completion_tokens"],
            call_count=totals["call_count"],
        )


def _turn_state() -> AgentTurnState:
    return AgentTurnState(
        owner_email="owner@example.com",
        actor_email="actor@example.com",
        actor_id="actor-1",
        actor_kind=ActorKind.OWNER,
        conversation_id="conversation-1",
        agent_id="agent-1",
        provider_name="Anthropic",
        model_name="claude-sonnet-4-5",
        user_message="hello",
    )


class FakeThoughtSignatureProvider:
    def __init__(self):
        self.calls = 0
        self.contexts = []

    async def stream_response(self, context, credentials, tools, model):
        self.calls += 1
        self.contexts.append(context.copy())
        if self.calls == 1:
            yield FakeProviderEvent(
                type="tool_use",
                tool_name="lookup_customer",
                tool_input={"customer_id": "cus_123"},
                tool_use_id="tooluse_1",
                thought_signature=b"gemini-signature",
            )
            yield FakeProviderEvent(type="stop")
            return

        yield FakeProviderEvent(type="text", content="done")
        yield FakeProviderEvent(type="stop")


class FakeToolRouter:
    def __init__(self):
        self.calls: list[dict[str, Any]] = []

    async def execute(self, *, tool_name, tool_input, tool_use_id, state):
        self.calls.append(
            {
                "tool_name": tool_name,
                "tool_input": tool_input,
                "tool_use_id": tool_use_id,
            }
        )
        return ToolExecutionOutcome(result="customer found", success=True)


class FakeStreamingToolRouter:
    async def execute(self, *, tool_name, tool_input, tool_use_id, state):
        await emit_turn_event(
            SSEEvent(
                event_type=SSEEventType.IMAGE_GENERATION_PARTIAL,
                content="Rendering image preview...",
                image_b64="abc123",
                image_mime_type="image/png",
            ),
            droppable=True,
        )
        return ToolExecutionOutcome(result="image generated", success=True)


class MultiStepProvider:
    def __init__(self):
        self.calls = 0

    async def stream_response(self, context, credentials, tools, model):
        self.calls += 1
        if self.calls == 1:
            yield FakeProviderEvent(
                type="tool_use",
                tool_name="create_epic",
                tool_input={"summary": "Agent Systems"},
                tool_use_id="tooluse_epic",
            )
            yield FakeProviderEvent(type="stop")
            return

        if self.calls == 2:
            assert _context_contains_text(context, POST_TOOL_CONTINUATION_PROMPT)
            yield FakeProviderEvent(
                type="tool_use",
                tool_name="create_task",
                tool_input={"summary": "Build Agent System", "parent": "KAN-6"},
                tool_use_id="tooluse_task",
            )
            yield FakeProviderEvent(type="stop")
            return

        yield FakeProviderEvent(type="text", content="Created the epic and task.")
        yield FakeProviderEvent(type="stop")


class ScriptedProvider:
    """Plays one scripted reply per model call and remembers what each call was given."""

    def __init__(self, *replies: list[FakeProviderEvent]):
        self.replies = list(replies)
        self.contexts: list[list[dict[str, Any]]] = []
        self.tools: list[list[Any]] = []

    async def stream_response(self, context, credentials, tools, model):
        self.contexts.append(copy.deepcopy(context))
        self.tools.append(list(tools))
        for event in self.replies.pop(0):
            yield event


def tool_call(tool_use_id: str) -> list[FakeProviderEvent]:
    return [
        FakeProviderEvent(type="tool_use", tool_name="lookup_customer", tool_input={}, tool_use_id=tool_use_id),
        FakeProviderEvent(type="stop", content="end_turn"),
    ]


def text(content: str, stop: str = "end_turn") -> list[FakeProviderEvent]:
    return [FakeProviderEvent(type="text", content=content), FakeProviderEvent(type="stop", content=stop)]


def silence(stop: str = "end_turn") -> list[FakeProviderEvent]:
    return [FakeProviderEvent(type="stop", content=stop)]


async def _run(provider, tools=("lookup_customer",)) -> list[Any]:
    return [
        event
        async for event in run_agentic_tool_loop(
            provider=provider,
            context=[],
            credentials={},
            tools=list(tools),
            model="test-model",
            tool_router=FakeToolRouter(),
            state=object(),
        )
    ]


async def test_agentic_loop_emits_tool_call_id_on_start_and_result():
    events = [
        event
        async for event in run_agentic_tool_loop(
            provider=FakeProvider(),
            context=[],
            credentials={},
            tools=[],
            model="test-model",
            tool_router=FakeToolRouter(),
            state=object(),
        )
    ]

    start = next(e for e in events if _type(e) == SSEEventType.TOOL_CALL_START)
    result = next(e for e in events if _type(e) == SSEEventType.TOOL_CALL_RESULT)

    assert start.tool_call_id == "tooluse_1"
    assert start.tool_name == "lookup_customer"
    assert result.tool_call_id == "tooluse_1"
    assert result.content == "customer found"


async def test_agentic_loop_prompts_model_to_continue_or_finish_after_tool_results():
    provider = MultiStepProvider()
    router = FakeToolRouter()

    events = [
        event
        async for event in run_agentic_tool_loop(
            provider=provider,
            context=[],
            credentials={},
            tools=[],
            model="test-model",
            tool_router=router,
            state=object(),
        )
    ]

    assert [call["tool_name"] for call in router.calls] == ["create_epic", "create_task"]
    assert isinstance(events[-1], TurnComplete)
    assert events[-1].full_text == "Created the epic and task."


async def test_a_model_silent_after_tools_is_asked_once_more_with_tools_off():
    provider = ScriptedProvider(tool_call("t1"), silence(), text("Customer found."))

    events = await _run(provider)

    # Without tools the model cannot answer with another call, typed or real, so it has to write.
    assert provider.tools[-1] == []
    assert _context_contains_text(provider.contexts[-1], FINAL_SUMMARY_PROMPT)
    assert events[-1] == TurnComplete(full_text="Customer found.", stop_reason="end_turn")


async def test_a_turn_silent_even_when_summarising_still_completes_with_its_stop_reason():
    provider = ScriptedProvider(tool_call("t1"), silence(), silence(stop="max_tokens"))

    events = await _run(provider)

    assert len(provider.contexts) == 3
    assert events[-1] == TurnComplete(full_text="", stop_reason="max_tokens")


async def test_a_long_run_keeps_one_continuation_nudge_on_the_latest_results():
    provider = ScriptedProvider(tool_call("t1"), tool_call("t2"), tool_call("t3"), text("All three done."))

    await _run(provider)

    final_context = provider.contexts[-1]
    nudges = [
        index for index, message in enumerate(final_context) if _message_has_text(message, POST_TOOL_CONTINUATION_PROMPT)
    ]
    assert nudges == [len(final_context) - 1]
    roles = [message["role"] for message in final_context]
    assert all(first != second for first, second in zip(roles, roles[1:]))


async def test_reaching_the_iteration_limit_still_ends_with_what_was_done(monkeypatch):
    monkeypatch.setattr("src.agents.agentic_loop.MAX_TOOL_ITERATIONS", 2)
    provider = ScriptedProvider(tool_call("t1"), tool_call("t2"), text("Did two of three."))

    events = await _run(provider)

    assert provider.tools[-1] == []
    assert _context_contains_text(provider.contexts[-1], ITERATION_LIMIT_SUMMARY_PROMPT)
    assert events[-1] == TurnComplete(full_text="Did two of three.", stop_reason="end_turn")


async def test_a_model_cut_off_before_answering_anything_says_why():
    events = await _run(ScriptedProvider(silence(stop="max_tokens")))

    assert _type(events[-1]) == SSEEventType.ERROR
    assert "output limit" in events[-1].content
    assert not any(isinstance(event, TurnComplete) for event in events)


async def test_a_large_tool_result_reaches_the_model_whole():
    class BigResultRouter(FakeToolRouter):
        async def execute(self, **kwargs):
            return ToolExecutionOutcome(result="x" * 250_000, success=True)

    provider = ScriptedProvider(tool_call("t1"), text("Read it all."))
    [
        event
        async for event in run_agentic_tool_loop(
            provider=provider,
            context=[],
            credentials={},
            tools=["lookup_customer"],
            model="test-model",
            tool_router=BigResultRouter(),
            state=object(),
        )
    ]

    results = [
        block["toolResult"]["content"][0]["text"]
        for message in provider.contexts[-1]
        for block in message["content"]
        if isinstance(block, dict) and "toolResult" in block
    ]
    assert results == ["x" * 250_000]


async def test_agentic_loop_preserves_provider_thought_signature_in_tool_context():
    provider = FakeThoughtSignatureProvider()

    events = [
        event
        async for event in run_agentic_tool_loop(
            provider=provider,
            context=[],
            credentials={},
            tools=[],
            model="test-model",
            tool_router=FakeToolRouter(),
            state=object(),
        )
    ]

    assert any(isinstance(event, TurnComplete) for event in events)
    second_call_context = provider.contexts[1]
    assistant_tool_use = second_call_context[0]["content"][0]["toolUse"]
    assert assistant_tool_use["thoughtSignature"] == b"gemini-signature"


async def test_agentic_loop_surfaces_runtime_events_during_tool_execution():
    events = [
        event
        async for event in run_agentic_tool_loop(
            provider=FakeProvider(),
            context=[],
            credentials={},
            tools=[],
            model="test-model",
            tool_router=FakeStreamingToolRouter(),
            state=object(),
        )
    ]

    runtime_event_index = next(
        index
        for index, event in enumerate(events)
        if _type(event) == SSEEventType.IMAGE_GENERATION_PARTIAL
    )
    result_index = next(
        index
        for index, event in enumerate(events)
        if _type(event) == SSEEventType.TOOL_CALL_RESULT
    )
    runtime_event = events[runtime_event_index]

    assert runtime_event_index < result_index
    assert runtime_event.event_type == SSEEventType.IMAGE_GENERATION_PARTIAL
    assert runtime_event.image_b64 == "abc123"


async def test_agentic_loop_records_token_usage_once_per_llm_iteration():
    provider = FakeProvider()
    token_usage_service = FakeTokenUsageService()
    state = _turn_state()

    events = [
        event
        async for event in run_agentic_tool_loop(
            provider=provider,
            context=[],
            credentials={},
            tools=[],
            model="claude-sonnet-4-5",
            tool_router=FakeToolRouter(),
            state=state,
            token_usage_service=token_usage_service,
        )
    ]

    assert isinstance(events[-1], TurnComplete)
    assert provider.calls == 2
    # record_usage must fire once per LLM iteration (twice here: one tool-call
    # round trip plus the final text response), not once per turn.
    assert len(token_usage_service.calls) == 2
    assert token_usage_service.calls[0] == {
        "owner_email": "owner@example.com",
        "agent_id": "agent-1",
        "llm_model": "claude-sonnet-4-5",
        "prompt_tokens": 10,
        "completion_tokens": 5,
    }
    assert token_usage_service.calls[1] == {
        "owner_email": "owner@example.com",
        "agent_id": "agent-1",
        "llm_model": "claude-sonnet-4-5",
        "prompt_tokens": 7,
        "completion_tokens": 3,
    }

    # A TOKEN_USAGE_UPDATE is streamed once per recorded call too, so the
    # client can show a live running total.
    usage_events = [e for e in events if _type(e) == SSEEventType.TOKEN_USAGE_UPDATE]
    assert len(usage_events) == 2
    assert [
        (e.llm_model, e.prompt_tokens, e.completion_tokens, e.total_tokens, e.call_count)
        for e in usage_events
    ] == [
        ("claude-sonnet-4-5", 10, 5, 15, 1),
        ("claude-sonnet-4-5", 17, 8, 25, 2),
    ]


async def test_agentic_loop_swallows_token_usage_recording_errors():
    """Best-effort telemetry: a broken/misconfigured token usage recorder
    must never break the user-facing turn."""

    class ExplodingTokenUsageService:
        def record_usage(self, **kwargs):
            raise RuntimeError("boom")

    events = [
        event
        async for event in run_agentic_tool_loop(
            provider=FakeProvider(),
            context=[],
            credentials={},
            tools=[],
            model="claude-sonnet-4-5",
            tool_router=FakeToolRouter(),
            state=_turn_state(),
            token_usage_service=ExplodingTokenUsageService(),
        )
    ]

    assert isinstance(events[-1], TurnComplete)
    assert events[-1].full_text == "done"


def _message_has_text(message: dict[Any, Any], expected_text: str) -> bool:
    return any(isinstance(block, dict) and block.get("text") == expected_text for block in message.get("content", []))


def _context_contains_text(context: list[dict[Any, Any]], expected_text: str) -> bool:
    return any(
        content.get("text") == expected_text
        for message in context
        for content in message.get("content", [])
        if isinstance(content, dict)
    )


class BurstThenReturnToolRouter:
    """Emits several events and returns immediately, with no await in between.

    The tool finishes in the same scheduling pass as its last emit, which is
    exactly the race where a runtime event can be dropped -- see
    api/docs/LLD-agent-runtime-refactor.md (P1.4).
    """

    async def execute(self, *, tool_name, tool_input, tool_use_id, state):
        for index in range(5):
            await emit_turn_event(
                SSEEvent(
                    event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
                    content=f"step-{index}",
                )
            )
        return ToolExecutionOutcome(result="done", success=True)


async def test_agentic_loop_loses_no_runtime_event_emitted_just_before_the_tool_returns():
    events = [
        event
        async for event in run_agentic_tool_loop(
            provider=FakeProvider(),
            context=[],
            credentials={},
            tools=[],
            model="test-model",
            tool_router=BurstThenReturnToolRouter(),
            state=object(),
        )
    ]

    notes = [
        event.content
        for event in events
        if _type(event) == SSEEventType.LIFECYCLE_NOTIFICATION
    ]
    result_index = next(
        index
        for index, event in enumerate(events)
        if _type(event) == SSEEventType.TOOL_CALL_RESULT
    )
    last_note_index = max(
        index
        for index, event in enumerate(events)
        if _type(event) == SSEEventType.LIFECYCLE_NOTIFICATION
    )

    assert notes == [f"step-{index}" for index in range(5)]
    assert last_note_index < result_index


class WrapperToolProvider:
    """Calls a wrapper tool whose real identity is nested in its arguments."""

    def __init__(self):
        self.calls = 0

    async def stream_response(self, context, credentials, tools, model):
        self.calls += 1
        if self.calls == 1:
            yield FakeProviderEvent(
                type="tool_use",
                tool_name="call_mcp_tool",
                tool_input={
                    "mcp_id": "atlassian",
                    "tool_name": "searchJiraIssuesUsingJql",
                    "arguments": {"jql": "project = KAN"},
                },
                tool_use_id="tooluse_mcp",
            )
            yield FakeProviderEvent(type="stop")
            return
        yield FakeProviderEvent(type="text", content="no issues found")
        yield FakeProviderEvent(type="stop")


async def test_the_loop_unwraps_a_wrapper_tools_real_identity_for_display():
    """The raw wrapper call still reaches the audit log; display fields carry
    the tool the user actually sees."""
    events = [
        event
        async for event in run_agentic_tool_loop(
            provider=WrapperToolProvider(),
            context=[],
            credentials={},
            tools=[],
            model="test-model",
            tool_router=FakeToolRouter(),
            state=_turn_state(),
        )
    ]

    start = next(e for e in events if _type(e) == SSEEventType.TOOL_CALL_START)
    result = next(e for e in events if _type(e) == SSEEventType.TOOL_CALL_RESULT)

    for event in (start, result):
        assert event.tool_name == "call_mcp_tool"
        assert event.display_tool_name == "searchJiraIssuesUsingJql"
        assert event.display_tool_args == {"jql": "project = KAN"}
