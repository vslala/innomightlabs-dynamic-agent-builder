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
import json
import time
from dataclasses import dataclass
from typing import Any, AsyncIterator, Optional, Protocol

from src.common import MAX_TOOL_ITERATIONS
from src.agents.turn_runtime import AgentTurnRuntime, use_turn_runtime

INTERNAL_TOOL_MARKER_PREFIXES = ("[tool_call ", "[tool_result]")
ASYNC_TOOL_MAX_IN_TURN_WAIT_SECONDS = 10 * 60


class AsyncToolJobStillRunningError(RuntimeError):
    pass


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


@dataclass(frozen=True)
class _SyntheticToolEvent:
    tool_name: str
    tool_input: dict[str, Any]
    tool_use_id: str


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
    active_async_jobs: dict[str, dict[str, Any]] = {}
    async_wait_cycles = 0
    async_deadline_at: float | None = None
    needs_async_final_response = False
    model_iterations = 0

    with use_turn_runtime(runtime):
        while True:
            if active_async_jobs and _async_deadline_expired(async_deadline_at):
                raise AsyncToolJobStillRunningError(
                    "Async tool job is still running after the maximum in-turn wait time. "
                    "The response was not completed because the agent has not received the final tool result."
                )
            if (
                not active_async_jobs
                and not needs_async_final_response
                and model_iterations >= MAX_TOOL_ITERATIONS
            ):
                break

            model_iterations += 1
            has_tool_calls = False
            pending_tool_calls: list[Any] = []
            iteration_text = ""
            needs_async_final_response = False

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

            if not pending_tool_calls and active_async_jobs:
                wait_event = _SyntheticToolEvent(
                    tool_name="wait",
                    tool_input={
                        "seconds": 20,
                        "reason": "waiting for async tool job completion",
                    },
                    tool_use_id=f"auto_wait_{async_wait_cycles + 1}",
                )
                pending_tool_calls.append(wait_event)
                has_tool_calls = True
                yield AgenticLoopEvent(
                    kind="tool_call_start",
                    payload={
                        "tool_call_id": wait_event.tool_use_id,
                        "tool_name": wait_event.tool_name,
                        "tool_args": wait_event.tool_input,
                    },
                )

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
                async_job_starts: list[dict[str, Any]] = []
                completed_wait = False
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
                    async_job = _extract_async_job_start(outcome.result)
                    if async_job:
                        async_job_starts.append(async_job)
                        active_async_jobs[str(async_job["job_id"])] = async_job
                        async_deadline_at = _ensure_async_deadline(async_deadline_at)
                    if tool_event.tool_name == "wait":
                        completed_wait = True

                context.append({"role": "user", "content": tool_results})
                if async_job_starts:
                    context.append(
                        {
                            "role": "user",
                            "content": [
                                {
                                    "text": _build_async_job_followup_instruction(
                                        async_job_starts,
                                        max_wait_seconds=ASYNC_TOOL_MAX_IN_TURN_WAIT_SECONDS,
                                    )
                                }
                            ],
                        }
                    )
                if completed_wait and active_async_jobs:
                    async_wait_cycles += 1
                    checked_results: list[dict[str, Any]] = []
                    checked_tool_uses: list[dict[str, Any]] = []
                    for job_id in list(active_async_jobs):
                        check_event = _SyntheticToolEvent(
                            tool_name="check_tool_job",
                            tool_input={"job_id": job_id},
                            tool_use_id=f"auto_check_{job_id}_{async_wait_cycles}",
                        )
                        yield AgenticLoopEvent(
                            kind="tool_call_start",
                            payload={
                                "tool_call_id": check_event.tool_use_id,
                                "tool_name": check_event.tool_name,
                                "tool_args": check_event.tool_input,
                            },
                        )
                        check_outcome = None
                        async for execution_event in _execute_tool_with_runtime_events(
                            runtime=runtime,
                            tool_router=tool_router,
                            tool_event=check_event,
                            state=state,
                        ):
                            if execution_event.kind == "tool_execution_complete":
                                check_outcome = execution_event.payload["outcome"]
                                continue
                            yield execution_event
                        if check_outcome is None:
                            raise RuntimeError("Tool execution did not complete: check_tool_job")

                        yield AgenticLoopEvent(
                            kind="tool_call_result",
                            payload={
                                "tool_call_id": check_event.tool_use_id,
                                "tool_name": check_event.tool_name,
                                "result": check_outcome.result,
                                "success": check_outcome.success,
                            },
                        )
                        checked_results.append(
                            {
                                "toolResult": {
                                    "toolUseId": check_event.tool_use_id,
                                    "content": [{"text": check_outcome.result}],
                                }
                            }
                        )
                        checked_tool_uses.append(
                            {
                                "toolUse": {
                                    "toolUseId": check_event.tool_use_id,
                                    "name": check_event.tool_name,
                                    "input": check_event.tool_input,
                                }
                            }
                        )
                        status = _extract_async_job_status(check_outcome.result)
                        if status and status.get("status") in {"succeeded", "failed"}:
                            active_async_jobs.pop(job_id, None)
                            needs_async_final_response = True

                    if checked_results:
                        context.append(
                            {
                                "role": "assistant",
                                "content": checked_tool_uses,
                            }
                        )
                        context.append({"role": "user", "content": checked_results})
                        if active_async_jobs:
                            context.append(
                                {
                                    "role": "user",
                                    "content": [
                                        {
                                            "text": _build_async_job_followup_instruction(
                                                list(active_async_jobs.values()),
                                                max_wait_seconds=ASYNC_TOOL_MAX_IN_TURN_WAIT_SECONDS,
                                            )
                                        }
                                    ],
                                }
                            )

                # If tools mutated core memory, request a prompt refresh before the next iteration.
                if getattr(state, "prompt_dirty", False):
                    yield AgenticLoopEvent(kind="prompt_refresh_needed", payload={})
                    # Clear here so we refresh at most once per tool batch.
                    state.prompt_dirty = False

            if not has_tool_calls:
                break

    if active_async_jobs:
        raise AsyncToolJobStillRunningError(
            "Async tool job is still running after the maximum in-turn wait time. "
            "The response was not completed because the agent has not received the final tool result."
        )

    yield AgenticLoopEvent(kind="complete", payload={"full_text": full_response})


def _extract_async_job_start(result: str) -> dict[str, Any] | None:
    payload = _extract_async_job_status(result)
    if not payload:
        return None
    if payload.get("status") in {"queued", "running"}:
        return payload
    return None


def _extract_async_job_status(result: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(result)
    except Exception:
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("async") is True and payload.get("status") and payload.get("job_id"):
        return payload
    return None


def _build_async_job_followup_instruction(
    jobs: list[dict[str, Any]],
    *,
    max_wait_seconds: int,
) -> str:
    lines = [
        "An async tool job has started. Do not finish the conversation after this queued/running status.",
        "Briefly tell the user that the job is running if useful.",
        "Then call wait. After wait returns, call check_tool_job for the job_id.",
        "If the job is still queued or running, repeat the wait/check cycle.",
        "When the job succeeds or fails, use the returned job payload as the final tool result.",
        f"Do not wait longer than {max_wait_seconds} seconds total in this turn.",
        "Jobs:",
    ]
    for job in jobs:
        lines.append(f"- job_id={job['job_id']} status={job.get('status', 'queued')}")
    return "\n".join(lines)


def _ensure_async_deadline(current_deadline: float | None) -> float:
    if current_deadline is not None:
        return current_deadline
    return time.monotonic() + ASYNC_TOOL_MAX_IN_TURN_WAIT_SECONDS


def _async_deadline_expired(deadline_at: float | None) -> bool:
    return deadline_at is not None and time.monotonic() >= deadline_at


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
