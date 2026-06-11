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

import asyncio
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional, Protocol

from src.common import MAX_TOOL_ITERATIONS
from src.agents.turn_runtime import AgentTurnRuntime, use_turn_runtime

INTERNAL_TOOL_MARKER_PREFIXES = ("[tool_call ", "[tool_result]")


class LLMProvider(Protocol):
    def stream_response(
        self,
        context: list[dict[Any, Any]],
        credentials: dict[Any, Any],
        tools: Optional[list[dict[Any, Any]]] = None,
        model: Optional[str] = None,
    ) -> AsyncIterator[Any]:
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
    context: list[dict[Any, Any]],
    credentials: dict[Any, Any],
    tools: list[dict[Any, Any]],
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
    text_filter = UserVisibleTextFilter()
    runtime = AgentTurnRuntime()

    with use_turn_runtime(runtime):
        for _iteration in range(MAX_TOOL_ITERATIONS):
            has_tool_calls = False
            pending_tool_calls: list[Any] = []
            iteration_text = ""

            async for event in provider.stream_response(context, credentials, tools, model):
                if event.type == "text":
                    visible_content = text_filter.feed(event.content)
                    if visible_content:
                        full_response += visible_content
                        iteration_text += visible_content
                        yield AgenticLoopEvent(kind="text", payload={"content": visible_content})

                elif event.type == "tool_use":
                    has_tool_calls = True
                    pending_tool_calls.append(event)
                    yield AgenticLoopEvent(
                        kind="tool_call_start",
                        payload={
                            "tool_call_id": event.tool_use_id,
                            "tool_name": event.tool_name,
                            "tool_args": event.tool_input,
                        },
                    )

                elif event.type == "stop":
                    # Provider stop token
                    pass

            visible_tail = text_filter.flush()
            if visible_tail:
                full_response += visible_tail
                iteration_text += visible_tail
                yield AgenticLoopEvent(kind="text", payload={"content": visible_tail})

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
                    outcome = None
                    async for execution_event in _execute_tool_with_runtime_events(
                        runtime=runtime,
                        tool_router=tool_router,
                        tool_event=tool_event,
                        state=state,
                    ):
                        if execution_event.kind == "tool_execution_complete":
                            outcome = execution_event.payload["outcome"]
                            continue
                        yield execution_event
                    if outcome is None:
                        raise RuntimeError(f"Tool execution did not complete: {tool_event.tool_name}")

                    yield AgenticLoopEvent(
                        kind="tool_call_result",
                        payload={
                            "tool_call_id": tool_event.tool_use_id,
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

                # If tools mutated core memory, request a prompt refresh before the next iteration.
                if getattr(state, "prompt_dirty", False):
                    yield AgenticLoopEvent(kind="prompt_refresh_needed", payload={})
                    # Clear here so we refresh at most once per tool batch.
                    state.prompt_dirty = False

            if not has_tool_calls:
                break

    yield AgenticLoopEvent(kind="complete", payload={"full_text": full_response})


async def _execute_tool_with_runtime_events(
    *,
    runtime: AgentTurnRuntime,
    tool_router: ToolRouter,
    tool_event: Any,
    state: Any,
) -> AsyncIterator[AgenticLoopEvent]:
    tool_task = asyncio.create_task(
        tool_router.execute(
            tool_name=tool_event.tool_name,
            tool_input=tool_event.tool_input,
            tool_use_id=tool_event.tool_use_id,
            state=state,
        )
    )

    try:
        while not tool_task.done():
            try:
                event = await asyncio.wait_for(runtime.next_event(), timeout=0.05)
            except TimeoutError:
                continue
            yield AgenticLoopEvent(kind="runtime_event", payload={"event": event})

        outcome = await tool_task
        for event in runtime.drain_available():
            yield AgenticLoopEvent(kind="runtime_event", payload={"event": event})
        yield AgenticLoopEvent(kind="tool_execution_complete", payload={"outcome": outcome})
    finally:
        if not tool_task.done():
            tool_task.cancel()


class UserVisibleTextFilter:
    """Remove internal tool transcript markers while preserving normal streaming text."""

    def __init__(self) -> None:
        self._pending = ""

    def feed(self, chunk: str) -> str:
        if not chunk:
            return ""

        self._pending += chunk
        output: list[str] = []

        while "\n" in self._pending:
            line, separator, remainder = self._pending.partition("\n")
            self._pending = remainder
            sanitized = self._sanitize_line(line + separator)
            if sanitized:
                output.append(sanitized)

        if self._pending and not self._could_be_internal_marker(self._pending):
            output.append(self._pending)
            self._pending = ""

        return "".join(output)

    def flush(self) -> str:
        pending = self._pending
        self._pending = ""
        return self._sanitize_line(pending)

    def _sanitize_line(self, line: str) -> str:
        return "" if self._is_internal_marker(line) else line

    def _is_internal_marker(self, text: str) -> bool:
        stripped = text.lstrip()
        return any(stripped.startswith(prefix) for prefix in INTERNAL_TOOL_MARKER_PREFIXES)

    def _could_be_internal_marker(self, text: str) -> bool:
        stripped = text.lstrip()
        return any(prefix.startswith(stripped) or stripped.startswith(prefix) for prefix in INTERNAL_TOOL_MARKER_PREFIXES)
