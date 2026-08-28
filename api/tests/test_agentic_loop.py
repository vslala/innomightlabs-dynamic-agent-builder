from dataclasses import dataclass
from typing import Any

from src.agents.agentic_loop import run_agentic_tool_loop
from src.agents.turn_runtime import emit_turn_event
from src.agents.tool_execution import ToolExecutionOutcome
from src.llm.events import SSEEvent, SSEEventType


@dataclass
class FakeProviderEvent:
    type: str
    content: str = ""
    tool_name: str = ""
    tool_input: dict[str, Any] | None = None
    tool_use_id: str = ""
    thought_signature: bytes | None = None


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
            yield FakeProviderEvent(type="stop")
            return

        yield FakeProviderEvent(type="text", content="done")
        yield FakeProviderEvent(type="stop")


class FakeMarkerProvider:
    def __init__(self):
        self.calls = 0

    async def stream_response(self, context, credentials, tools, model):
        self.calls += 1
        if self.calls == 1:
            yield FakeProviderEvent(type="text", content="I will check that.\n")
            yield FakeProviderEvent(
                type="text",
                content='[tool_call name=call_mcp_tool] {"mcp_id":"jira"}',
            )
            yield FakeProviderEvent(
                type="tool_use",
                tool_name="call_mcp_tool",
                tool_input={"mcp_id": "jira"},
                tool_use_id="tooluse_1",
            )
            yield FakeProviderEvent(type="stop")
            return

        yield FakeProviderEvent(type="text", content="Here are the tickets.")
        yield FakeProviderEvent(type="stop")


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
    async def execute(self, *, tool_name, tool_input, tool_use_id, state):
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


class AlwaysToolProvider:
    async def stream_response(self, context, credentials, tools, model):
        yield FakeProviderEvent(
            type="tool_use",
            tool_name="lookup_customer",
            tool_input={"customer_id": "cus_123"},
            tool_use_id=f"tooluse_{len(context)}",
        )
        yield FakeProviderEvent(type="stop")


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

    start = next(event for event in events if event.kind == "tool_call_start")
    result = next(event for event in events if event.kind == "tool_call_result")

    assert start.payload["tool_call_id"] == "tooluse_1"
    assert start.payload["tool_name"] == "lookup_customer"
    assert result.payload["tool_call_id"] == "tooluse_1"
    assert result.payload["result"] == "customer found"


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

    assert next(event for event in events if event.kind == "complete")
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
        index for index, event in enumerate(events) if event.kind == "runtime_event"
    )
    result_index = next(
        index for index, event in enumerate(events) if event.kind == "tool_call_result"
    )
    runtime_event = events[runtime_event_index].payload["event"]

    assert runtime_event_index < result_index
    assert runtime_event.event_type == SSEEventType.IMAGE_GENERATION_PARTIAL
    assert runtime_event.image_b64 == "abc123"


async def test_agentic_loop_filters_internal_tool_markers_but_streams_status_text():
    events = [
        event
        async for event in run_agentic_tool_loop(
            provider=FakeMarkerProvider(),
            context=[],
            credentials={},
            tools=[],
            model="test-model",
            tool_router=FakeToolRouter(),
            state=object(),
        )
    ]

    streamed_text = "".join(
        event.payload["content"] for event in events if event.kind == "text"
    )
    complete = next(event for event in events if event.kind == "complete")

    assert "I will check that." in streamed_text
    assert "Here are the tickets." in streamed_text
    assert "[tool_call name=call_mcp_tool]" not in streamed_text
    assert "[tool_call name=call_mcp_tool]" not in complete.payload["full_text"]


async def test_agentic_loop_reports_max_iterations_as_failure(monkeypatch):
    monkeypatch.setattr("src.agents.agentic_loop.MAX_TOOL_ITERATIONS", 1)

    events = [
        event
        async for event in run_agentic_tool_loop(
            provider=AlwaysToolProvider(),
            context=[],
            credentials={},
            tools=[],
            model="test-model",
            tool_router=FakeToolRouter(),
            state=object(),
        )
    ]

    assert events[-1].kind == "failed"
    assert events[-1].payload["reason"] == "max_tool_iterations"
    assert not any(event.kind == "complete" for event in events)
