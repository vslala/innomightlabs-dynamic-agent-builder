"""Agentic tool loop.

This isolates the iterative "LLM -> tool calls -> tool results -> LLM" pattern so
architectures stay readable.

Design constraints (for now):
- preserve current behavior
- keep provider interface unchanged
- keep context format unchanged

We can evolve this to emit richer structured errors and metrics later.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, AsyncIterator, Protocol

from src.common import MAX_TOOL_ITERATIONS


class ProviderStreamEvent(Protocol):
    type: str
    content: str
    tool_name: str
    tool_input: dict[str, Any]
    tool_use_id: str


class LLMProvider(Protocol):
    def stream_response(
        self,
        context: list[dict[str, Any]],
        credentials: dict[str, Any],
        tools: list[dict[str, Any]],
        model: str,
    ) -> AsyncIterator[ProviderStreamEvent]:
        ...


class ToolRouter(Protocol):
    async def execute(
        self,
        *,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str,
        state: Any,
    ):
        ...


@dataclass(frozen=True)
class AgenticLoopEvent:
    """Normalized events emitted by the loop."""

    kind: str
    payload: dict[str, Any]


@dataclass(frozen=True)
class AgenticLoopResult:
    full_text: str


async def run_agentic_tool_loop(
    *,
    provider: LLMProvider,
    context: list[dict[str, Any]],
    credentials: dict[str, Any],
    tools: list[dict[str, Any]],
    model: str,
    tool_router: ToolRouter,
    state: Any,
) -> AsyncIterator[AgenticLoopEvent]:
    """Run the agentic loop.

    Yields:
      - text chunks as they arrive
      - tool call start notifications
      - tool results
      - final completion marker (no persistence)

    The caller owns:
      - converting loop events to SSE events
      - persisting the assistant message
    """

    full_response = ""

    for _iteration in range(MAX_TOOL_ITERATIONS):
        has_tool_calls = False
        pending_tool_calls: list[ProviderStreamEvent] = []
        iteration_text = ""

        async for event in provider.stream_response(context, credentials, tools, model):
            if event.type == "text":
                full_response += event.content
                iteration_text += event.content
                yield AgenticLoopEvent(kind="text", payload={"content": event.content})

            elif event.type == "tool_use":
                has_tool_calls = True
                pending_tool_calls.append(event)
                yield AgenticLoopEvent(
                    kind="tool_call_start",
                    payload={
                        "tool_name": event.tool_name,
                        "tool_args": event.tool_input,
                    },
                )

            elif event.type == "stop":
                # Provider stop token
                pass

        if pending_tool_calls:
            # Add assistant response to context (text + tool use)
            assistant_content: list[dict[str, Any]] = []

            if iteration_text.strip():
                assistant_content.append({"text": iteration_text})

            for tool_event in pending_tool_calls:
                assistant_content.append(
                    {
                        "toolUse": {
                            "toolUseId": tool_event.tool_use_id,
                            "name": tool_event.tool_name,
                            "input": tool_event.tool_input,
                        }
                    }
                )

            context.append({"role": "assistant", "content": assistant_content})

            # Execute tools and collect results
            tool_results: list[dict[str, Any]] = []
            for tool_event in pending_tool_calls:
                outcome = await tool_router.execute(
                    tool_name=tool_event.tool_name,
                    tool_input=tool_event.tool_input,
                    tool_use_id=tool_event.tool_use_id,
                    state=state,
                )

                yield AgenticLoopEvent(
                    kind="tool_call_result",
                    payload={
                        "tool_name": tool_event.tool_name,
                        "result": outcome.result,
                        "success": outcome.success,
                    },
                )

                tool_results.append(
                    {
                        "toolResult": {
                            "toolUseId": tool_event.tool_use_id,
                            "content": [{"text": outcome.result}],
                        }
                    }
                )

            context.append({"role": "user", "content": tool_results})

        if not has_tool_calls:
            break

    yield AgenticLoopEvent(kind="complete", payload={"full_text": full_response})
