"""Agentic tool loop: LLM -> tool calls -> tool results -> LLM.

The loop streams `SSEEvent`s straight through, so the architecture consuming it
does not have to translate a parallel event vocabulary back into SSE. Two
control signals are not events and so have their own types: `PromptRefreshNeeded`
and `TurnComplete`.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional, Protocol

from src.agents.async_jobs import extract_async_job_status
from src.agents.loop_context import (
    append_assistant_tool_uses,
    append_user_tool_results,
    tool_result_block,
)
from src.agents.tool_display import derive_display_tool
from src.agents.tool_runtime.commands import ToolExecutionOutcome
from src.agents.turn_runtime import AgentTurnRuntime, emit_turn_event, use_turn_runtime
from src.common import MAX_TOOL_ITERATIONS
from src.llm.events import SSEEvent, SSEEventType
from src.token_usage.models import TokenUsageRecord
from src.token_usage.service import TokenUsageService

log = logging.getLogger(__name__)

INTERNAL_TOOL_MARKER_PREFIXES = ("[tool_call ", "[tool_result]")

#: How long the loop will wait, in total, for one async tool job to finish.
ASYNC_TOOL_MAX_IN_TURN_WAIT_SECONDS = 10 * 60
ASYNC_JOB_POLL_SECONDS = 2

POST_TOOL_CONTINUATION_PROMPT = (
    "Review the original user request and the latest tool result. "
    "If any requested work remains, call the next required tool now. "
    "Only provide a final answer when all requested work is complete. "
    "Do not say you will do something next unless you call the tool for it in this response."
)
EMPTY_POST_TOOL_RETRY_PROMPT = (
    "The previous response after receiving tool results was empty. "
    "Continue from the latest tool result now. "
    "Call another tool if required; otherwise provide the final answer."
)
MAX_ITERATIONS_MESSAGE = (
    "Agent stopped because it reached the maximum tool iterations "
    f"({MAX_TOOL_ITERATIONS}) before producing a final answer."
)
ASYNC_JOB_TIMEOUT_MESSAGE = (
    "Async tool job is still running after the maximum in-turn wait time. "
    "The response was not completed because the agent has not received the final tool result."
)


class AsyncToolJobStillRunningError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromptRefreshNeeded:
    """Tools mutated core memory; rebuild the system prompt before the next call."""


@dataclass(frozen=True)
class TurnComplete:
    """The model has finished. `full_text` is everything it said to the user."""

    full_text: str


#: Everything `run_agentic_tool_loop` can yield.
LoopYield = SSEEvent | PromptRefreshNeeded | TurnComplete


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
    ) -> ToolExecutionOutcome:
        ...


class TokenUsageRecorder(Protocol):
    def record_usage(
        self,
        *,
        owner_email: str,
        agent_id: str,
        llm_model: str,
        prompt_tokens: int,
        completion_tokens: int,
    ) -> "TokenUsageRecord":
        ...


async def run_agentic_tool_loop(
    *,
    provider: LLMProvider,
    context: list[dict[Any, Any]],
    credentials: dict[Any, Any],
    tools: list[dict[Any, Any]],
    model: str,
    tool_router: ToolRouter,
    state: Any,
    token_usage_service: Optional[TokenUsageRecorder] = None,
) -> AsyncIterator[LoopYield]:
    """Call the model, run whatever tools it asks for, repeat until it stops.

    The caller owns persisting the assistant message; everything streamed here
    is ready to hand to a client as-is.
    """
    full_response = ""
    text_filter = UserVisibleTextFilter()
    usage_service: TokenUsageRecorder = token_usage_service or TokenUsageService()
    runtime = AgentTurnRuntime()
    awaiting_post_tool_response = False
    empty_post_tool_retry_used = False
    model_iterations = 0

    with use_turn_runtime(runtime):
        while True:
            if model_iterations >= MAX_TOOL_ITERATIONS:
                yield SSEEvent(event_type=SSEEventType.ERROR, content=MAX_ITERATIONS_MESSAGE)
                return

            model_iterations += 1
            pending_tool_calls: list[Any] = []
            iteration_text = ""
            is_post_tool_response = awaiting_post_tool_response
            awaiting_post_tool_response = False
            usage_event: Any = None

            async for event in provider.stream_response(context, credentials, tools, model):
                if event.type == "text":
                    visible_content = text_filter.feed(event.content)
                    if visible_content:
                        full_response += visible_content
                        iteration_text += visible_content
                        yield _text_event(visible_content)

                elif event.type == "tool_use":
                    pending_tool_calls.append(event)
                    yield _tool_call_start_event(event)

                elif event.type == "usage":
                    usage_event = event

            if usage_event is not None:
                usage = await _record_token_usage(usage_service, state, usage_event)
                if usage is not None:
                    yield usage

            visible_tail = text_filter.flush()
            if visible_tail:
                full_response += visible_tail
                iteration_text += visible_tail
                yield _text_event(visible_tail)

            if pending_tool_calls:
                append_assistant_tool_uses(
                    context,
                    iteration_text=iteration_text,
                    tool_events=pending_tool_calls,
                )

                tool_results: list[dict[str, Any]] = []
                for tool_event in pending_tool_calls:
                    result = None
                    async for item in _run_tool(
                        runtime=runtime,
                        tool_router=tool_router,
                        tool_event=tool_event,
                        state=state,
                    ):
                        if isinstance(item, _ToolFinished):
                            result = item
                            continue
                        yield item
                    if result is None:
                        raise RuntimeError(f"Tool execution did not complete: {tool_event.tool_name}")

                    yield _tool_call_result_event(tool_event, result)
                    tool_results.append(tool_result_block(tool_event.tool_use_id, result.result))

                append_user_tool_results(context, tool_results)

                # If tools mutated core memory, ask for a prompt refresh before
                # the next call, at most once per batch.
                if getattr(state, "prompt_dirty", False):
                    yield PromptRefreshNeeded()
                    state.prompt_dirty = False

                context.append({"role": "user", "content": [{"text": POST_TOOL_CONTINUATION_PROMPT}]})
                awaiting_post_tool_response = True
                continue

            if (
                is_post_tool_response
                and not iteration_text.strip()
                and not empty_post_tool_retry_used
            ):
                empty_post_tool_retry_used = True
                awaiting_post_tool_response = True
                context.append({"role": "user", "content": [{"text": EMPTY_POST_TOOL_RETRY_PROMPT}]})
                continue

            break

    yield TurnComplete(full_text=full_response)


def _text_event(content: str) -> SSEEvent:
    return SSEEvent(event_type=SSEEventType.AGENT_RESPONSE_TO_USER, content=content)


def _tool_call_start_event(tool_event: Any) -> SSEEvent:
    display_name, display_args = derive_display_tool(tool_event.tool_name, tool_event.tool_input)
    return SSEEvent(
        event_type=SSEEventType.TOOL_CALL_START,
        content=f"Calling {tool_event.tool_name}...",
        tool_call_id=tool_event.tool_use_id,
        tool_name=tool_event.tool_name,
        tool_args=tool_event.tool_input,
        display_tool_name=display_name,
        display_tool_args=display_args,
    )


def _tool_call_result_event(tool_event: Any, finished: "_ToolFinished") -> SSEEvent:
    display_name, display_args = derive_display_tool(tool_event.tool_name, tool_event.tool_input)
    return SSEEvent(
        event_type=SSEEventType.TOOL_CALL_RESULT,
        content=finished.result,
        tool_call_id=tool_event.tool_use_id,
        tool_name=tool_event.tool_name,
        success=finished.success,
        display_tool_name=display_name,
        display_tool_args=display_args,
    )


async def _record_token_usage(
    usage_service: TokenUsageRecorder,
    state: Any,
    usage_event: Any,
) -> SSEEvent | None:
    """Once per LLM call, so a turn with several round trips records each one.

    Best-effort telemetry: never let it break the user-facing turn.
    """
    try:
        # Offloaded to a thread so a slow DynamoDB round trip never blocks the
        # shared event loop's other concurrent requests.
        day_record: Optional[TokenUsageRecord] = await asyncio.to_thread(
            usage_service.record_usage,
            owner_email=state.owner_email,
            agent_id=state.agent_id,
            llm_model=state.model_name,
            prompt_tokens=usage_event.prompt_tokens,
            completion_tokens=usage_event.completion_tokens,
        )
    except Exception:
        log.exception("Failed to record token usage for agent turn")
        return None

    if day_record is None:
        return None
    return SSEEvent(
        event_type=SSEEventType.TOKEN_USAGE_UPDATE,
        content="",
        llm_model=day_record.llm_model,
        prompt_tokens=day_record.prompt_tokens,
        completion_tokens=day_record.completion_tokens,
        total_tokens=day_record.total_tokens,
        call_count=day_record.call_count,
    )


@dataclass(frozen=True)
class _ToolFinished:
    result: str
    success: bool


async def _run_tool(
    *,
    runtime: AgentTurnRuntime,
    tool_router: ToolRouter,
    tool_event: Any,
    state: Any,
) -> AsyncIterator[SSEEvent | _ToolFinished]:
    """Execute one tool call, settling an async job before reporting a result."""

    async def execute() -> _ToolFinished:
        outcome = await tool_router.execute(
            tool_name=tool_event.tool_name,
            tool_input=tool_event.tool_input,
            tool_use_id=tool_event.tool_use_id,
            state=state,
        )
        job = extract_async_job_status(outcome.result)
        if job is None or not job.pending:
            return _ToolFinished(result=outcome.result, success=outcome.success)

        # The job runs as an in-process task and the loop already knows its id,
        # so wait for it here. Asking the model to drive a wait/check cycle cost
        # extra LLM round trips and put synthetic tool calls in the timeline.
        settled = await _await_async_job(
            job_id=job.job_id, tool_router=tool_router, state=state
        )
        return _ToolFinished(result=settled, success=outcome.success)

    async for item in _with_runtime_events(runtime, execute()):
        yield item


async def _await_async_job(*, job_id: str, tool_router: ToolRouter, state: Any) -> str:
    """Poll one tool job until it reaches a terminal state.

    Raises AsyncToolJobStillRunningError if it outlives the in-turn budget: the
    turn cannot produce an honest answer without the job's result.
    """
    deadline = time.monotonic() + ASYNC_TOOL_MAX_IN_TURN_WAIT_SECONDS
    attempt = 0

    while True:
        await asyncio.sleep(ASYNC_JOB_POLL_SECONDS)
        attempt += 1
        outcome = await tool_router.execute(
            tool_name="check_tool_job",
            tool_input={"job_id": job_id},
            tool_use_id=f"job_wait_{job_id}_{attempt}",
            state=state,
        )

        job = extract_async_job_status(outcome.result)
        if job is None or not job.pending:
            return outcome.result

        if time.monotonic() >= deadline:
            raise AsyncToolJobStillRunningError(ASYNC_JOB_TIMEOUT_MESSAGE)

        await emit_turn_event(
            SSEEvent(
                event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
                content=job.progress_message or "Still working on it...",
            ),
            droppable=True,
        )


async def _with_runtime_events(
    runtime: AgentTurnRuntime,
    awaitable: Any,
) -> AsyncIterator[Any]:
    """Run `awaitable`, interleaving the turn-runtime events it emits.

    Yields each runtime event as it arrives, then the awaitable's result last.
    Races the two rather than polling: a 50ms poll woke the shared event loop
    20 times a second for as long as a tool ran.
    """
    task = asyncio.create_task(awaitable)
    next_event = asyncio.ensure_future(runtime.next_event())

    try:
        while True:
            done, _ = await asyncio.wait({task, next_event}, return_when=asyncio.FIRST_COMPLETED)
            if next_event in done:
                yield next_event.result()
                next_event = asyncio.ensure_future(runtime.next_event())
            if task in done:
                break

        result = await task
        # Cancelling a *done* future discards its result, so hand over anything
        # already in flight before draining the rest.
        if next_event.done() and not next_event.cancelled():
            yield next_event.result()
        for event in runtime.drain_available():
            yield event
        yield result
    finally:
        next_event.cancel()
        if not task.done():
            task.cancel()


class UserVisibleTextFilter:
    """Remove internal tool transcript markers while preserving normal streaming text.

    The markers come from the OpenAI provider, which flattens tool blocks into
    text when encoding a request; the model then imitates them in its output.
    """

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
        return any(
            prefix.startswith(stripped) or stripped.startswith(prefix)
            for prefix in INTERNAL_TOOL_MARKER_PREFIXES
        )
