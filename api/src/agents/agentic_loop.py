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
from dataclasses import dataclass, field, replace
from enum import Enum, auto
from typing import Any, AsyncIterator, Optional, Protocol

from src.agents.async_jobs import extract_async_job_status
from src.agents.runtime_state import AgentTurnState
from src.agents.loop_context import (
    append_assistant_tool_uses,
    append_user_tool_results,
    tool_result_block,
)
from src.agents.tool_display import derive_display_tool
from src.agents.tool_runtime import ToolExecutionOutcome
from src.agents.turn_runtime import AgentTurnRuntime, emit_turn_event, use_turn_runtime
from src.common import MAX_TOOL_ITERATIONS
from src.llm.events import SSEEvent, SSEEventType
from src.llm.providers.base import LLMEvent
from src.token_usage.models import TokenUsageRecord
from src.token_usage.service import TokenUsageService

log = logging.getLogger(__name__)

#: How long the loop will wait, in total, for one async tool job to finish.
ASYNC_TOOL_MAX_IN_TURN_WAIT_SECONDS = 10 * 60
ASYNC_JOB_POLL_SECONDS = 2

POST_TOOL_CONTINUATION_PROMPT = (
    "Review the original user request and the latest tool result. "
    "If any requested work remains, call the next required tool now. "
    "Only provide a final answer when all requested work is complete. "
    "Do not say you will do something next unless you call the tool for it in this response."
)
FINAL_SUMMARY_PROMPT = (
    "Tool use is finished for this turn. Using only the tool results above, tell the user what was done, "
    "what was found, and anything that failed or still needs their input."
)
ITERATION_LIMIT_SUMMARY_PROMPT = (
    f"This turn has reached its limit of {MAX_TOOL_ITERATIONS} model calls, so no more tools can run. "
    "Using only the tool results above, tell the user what was done, what was found, and what is still left to do."
)
#: What to tell the user when the model was kept from answering and no tool had run.
STOPPED_MESSAGES: dict[str, str] = {
    "max_tokens": "The model reached its output limit before it could answer. Try asking for a shorter answer.",
    "content_filter": "The model's provider blocked this response with its content filter.",
}
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
    #: Why the model last stopped (a `StopReason`): a normal end, or a limit that kept it from answering.
    stop_reason: str = "end_turn"


#: Everything `run_agentic_tool_loop` can yield.
LoopYield = SSEEvent | PromptRefreshNeeded | TurnComplete


class LLMProvider(Protocol):
    def stream_response(
        self,
        context: list[dict[Any, Any]],
        credentials: dict[Any, Any],
        tools: Optional[list[dict[Any, Any]]] = None,
        model: Optional[str] = None,
    ) -> AsyncIterator[LLMEvent]:
        ...


class ToolRouter(Protocol):
    async def execute(
        self,
        *,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str,
        state: AgentTurnState,
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
        api_key_id: Optional[str] = None,
    ) -> "TokenUsageRecord":
        ...


class Step(Enum):
    """Where a turn is. Only the driver in `run_agentic_tool_loop` moves a turn from one step to the next."""

    ASK_MODEL = auto()
    RUN_TOOLS = auto()
    SUMMARISE = auto()
    DONE = auto()
    STOPPED = auto()


@dataclass
class _ModelCall:
    """What one model call produced. Each call gets a fresh one, so nothing carries over by accident."""

    text: str = ""
    tool_calls: list[LLMEvent] = field(default_factory=list)
    stop_reason: str = "end_turn"


def next_step_after_call(call: _ModelCall, *, tools_ran: bool) -> Step:
    """Tool calls win over text, text over silence. Silence after tools asks for a summary."""
    if call.tool_calls:
        return Step.RUN_TOOLS
    if call.text.strip():
        return Step.DONE
    if tools_ran:
        return Step.SUMMARISE
    if call.stop_reason in STOPPED_MESSAGES:
        return Step.STOPPED
    # Nothing said and no tool ran: the turn answered some other way, such as by generating an image.
    return Step.DONE


async def run_agentic_tool_loop(
    *,
    provider: LLMProvider,
    context: list[dict[Any, Any]],
    credentials: dict[Any, Any],
    tools: list[dict[Any, Any]],
    model: str,
    tool_router: ToolRouter,
    state: AgentTurnState,
    token_usage_service: Optional[TokenUsageRecorder] = None,
) -> AsyncIterator[LoopYield]:
    """Call the model, run whatever tools it asks for, repeat until it answers.

    The caller owns persisting the assistant message; everything streamed here
    is ready to hand to a client as-is.
    """
    turn = _Turn(
        provider=provider,
        context=context,
        credentials=credentials,
        tools=tools,
        model=model,
        tool_router=tool_router,
        state=state,
        usage_service=token_usage_service or TokenUsageService(),
    )
    step, call = Step.ASK_MODEL, _ModelCall()
    summary_prompt = FINAL_SUMMARY_PROMPT

    with use_turn_runtime(turn.runtime):
        while step not in (Step.DONE, Step.STOPPED):
            match step:
                case Step.ASK_MODEL if turn.model_calls >= MAX_TOOL_ITERATIONS:
                    # A long run that hits the limit still tells the user what it did.
                    summary_prompt = ITERATION_LIMIT_SUMMARY_PROMPT
                    step = Step.SUMMARISE
                case Step.ASK_MODEL:
                    call = _ModelCall()
                    async for item in turn.call_model(call, step):
                        yield item
                    step = next_step_after_call(call, tools_ran=turn.tools_ran)
                case Step.RUN_TOOLS:
                    async for item in turn.run_tools(call):
                        yield item
                    step = Step.ASK_MODEL
                case Step.SUMMARISE:
                    # With tools off, the only thing the model can do is answer.
                    turn.nudge(summary_prompt)
                    call = _ModelCall()
                    async for item in turn.call_model(call, step):
                        yield item
                    # Even silence ends the turn here: the caller then records which tools ran.
                    step = Step.DONE

        if step is Step.STOPPED:
            yield SSEEvent(event_type=SSEEventType.ERROR, content=STOPPED_MESSAGES[call.stop_reason])
            return

    yield TurnComplete(full_text=turn.full_text, stop_reason=call.stop_reason)


@dataclass
class _Turn:
    """One user turn's collaborators, and the few facts that span its model calls."""

    provider: LLMProvider
    context: list[dict[Any, Any]]
    credentials: dict[Any, Any]
    tools: list[dict[Any, Any]]
    model: str
    tool_router: ToolRouter
    state: AgentTurnState
    usage_service: TokenUsageRecorder
    runtime: AgentTurnRuntime = field(default_factory=AgentTurnRuntime)

    model_calls: int = 0
    full_text: str = ""
    tools_ran: bool = False
    #: The one instruction riding on the latest tool results, so the context never fills with copies.
    _nudge: tuple[dict[Any, Any], dict[str, str]] | None = None

    async def call_model(self, call: _ModelCall, step: Step) -> AsyncIterator[SSEEvent]:
        """Stream one model call into `call`. A summary call offers no tools and ignores any it is sent."""
        answer_only = step is Step.SUMMARISE
        self.model_calls += 1
        usage_event: LLMEvent | None = None

        tools = [] if answer_only else self.tools
        async for event in self.provider.stream_response(self.context, self.credentials, tools, self.model):
            if event.type == "text" and event.content:
                call.text += event.content
                self.full_text += event.content
                yield _text_event(event.content)

            elif event.type == "tool_use":
                if answer_only:
                    log.warning("Ignoring tool call %s made while tools were off", event.tool_name)
                    continue
                call.tool_calls.append(event)
                yield _tool_call_start_event(event)

            elif event.type == "usage":
                usage_event = event

            elif event.type == "stop":
                call.stop_reason = event.content or "end_turn"

        log.info(
            "Agent loop call=%d step=%s stop=%s text_chars=%d tool_calls=%d context_messages=%d context_chars=%d",
            self.model_calls,
            step.name,
            call.stop_reason,
            len(call.text),
            len(call.tool_calls),
            len(self.context),
            _context_chars(self.context),
        )

        if usage_event is not None:
            usage = await _record_token_usage(self.usage_service, self.state, usage_event)
            if usage is not None:
                yield usage

    async def run_tools(self, call: _ModelCall) -> AsyncIterator[LoopYield]:
        """Run the call's tools one after another, in the order the model asked for them."""
        append_assistant_tool_uses(self.context, iteration_text=call.text, tool_events=call.tool_calls)

        tool_results: list[dict[str, Any]] = []
        refresh_prompt = False
        for tool_event in call.tool_calls:
            task = asyncio.create_task(self._execute_and_settle(tool_event))
            async for event in self.runtime.stream_while(task):
                yield event
            outcome = task.result()

            refresh_prompt = refresh_prompt or outcome.refresh_prompt
            yield _tool_call_result_event(tool_event, outcome)
            tool_results.append(tool_result_block(tool_event.tool_use_id, outcome.result))

        append_user_tool_results(self.context, tool_results)
        self.tools_ran = True
        self.nudge(POST_TOOL_CONTINUATION_PROMPT)

        if refresh_prompt:
            yield PromptRefreshNeeded()

    def nudge(self, text: str) -> None:
        """Put `text` on the latest tool results, taking it off wherever it rode before."""
        if self._nudge is not None:
            message, block = self._nudge
            message["content"].remove(block)
        block = {"text": text}
        self.context[-1]["content"].append(block)
        self._nudge = (self.context[-1], block)

    async def _execute_and_settle(self, tool_event: LLMEvent) -> ToolExecutionOutcome:
        """Run one tool call, waiting out an async job so the model gets its real result."""
        outcome = await self.tool_router.execute(
            tool_name=tool_event.tool_name,
            tool_input=tool_event.tool_input,
            tool_use_id=tool_event.tool_use_id,
            state=self.state,
        )
        job = extract_async_job_status(outcome.result)
        if job is None or not job.pending:
            return outcome

        # The job runs as an in-process task and the loop already knows its id,
        # so wait for it here. Asking the model to drive a wait/check cycle cost
        # extra LLM round trips and put synthetic tool calls in the timeline.
        settled = await _await_async_job(job_id=job.job_id, tool_router=self.tool_router, state=self.state)
        # The start's success flag stands, whatever the job reports. See LLD-agent-core-readability.md §3.
        return replace(settled, success=outcome.success, refresh_prompt=outcome.refresh_prompt or settled.refresh_prompt)


def _context_chars(context: list[dict[Any, Any]]) -> int:
    """Roughly how much the model reads on this call, so a runaway context shows up in the logs."""
    return len(repr(context))


def _text_event(content: str) -> SSEEvent:
    return SSEEvent(event_type=SSEEventType.AGENT_RESPONSE_TO_USER, content=content)


def _tool_call_start_event(tool_event: LLMEvent) -> SSEEvent:
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


def _tool_call_result_event(tool_event: LLMEvent, outcome: ToolExecutionOutcome) -> SSEEvent:
    display_name, display_args = derive_display_tool(tool_event.tool_name, tool_event.tool_input)
    return SSEEvent(
        event_type=SSEEventType.TOOL_CALL_RESULT,
        content=outcome.result,
        tool_call_id=tool_event.tool_use_id,
        tool_name=tool_event.tool_name,
        success=outcome.success,
        display_tool_name=display_name,
        display_tool_args=display_args,
    )


async def _record_token_usage(
    usage_service: TokenUsageRecorder,
    state: AgentTurnState,
    usage_event: LLMEvent,
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
            api_key_id=state.api_key_id,
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


async def _await_async_job(*, job_id: str, tool_router: ToolRouter, state: AgentTurnState) -> ToolExecutionOutcome:
    """Poll one tool job until it reaches a terminal state, returning that poll's outcome.

    Raises AsyncToolJobStillRunningError if it outlives the in-turn budget: the
    turn cannot produce an honest answer without the job's result.
    """
    deadline = time.monotonic() + ASYNC_TOOL_MAX_IN_TURN_WAIT_SECONDS
    attempt = 0
    refresh_prompt = False

    while True:
        await asyncio.sleep(ASYNC_JOB_POLL_SECONDS)
        attempt += 1
        outcome = await tool_router.execute(
            tool_name="check_tool_job",
            tool_input={"job_id": job_id},
            tool_use_id=f"job_wait_{job_id}_{attempt}",
            state=state,
        )
        refresh_prompt = refresh_prompt or outcome.refresh_prompt

        job = extract_async_job_status(outcome.result)
        if job is None or not job.pending:
            return replace(outcome, refresh_prompt=refresh_prompt)

        if time.monotonic() >= deadline:
            raise AsyncToolJobStillRunningError(ASYNC_JOB_TIMEOUT_MESSAGE)

        await emit_turn_event(
            SSEEvent(
                event_type=SSEEventType.LIFECYCLE_NOTIFICATION,
                content=job.progress_message or "Still working on it...",
            ),
            droppable=True,
        )
