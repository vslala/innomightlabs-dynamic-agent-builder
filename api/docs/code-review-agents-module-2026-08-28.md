# Code Review: Agents Module

Date: 2026-08-28

Scope:

- `api/src/agents/`
- Agentic-loop behavior in `api/src/agents/agentic_loop.py`
- Direct collaborators needed to understand the loop: `api/src/tools/native/handlers.py`, `api/src/skills/service.py`, and provider message conversion under `api/src/llm/`

This review was performed against the current working tree. At review time, `api/src/agents/agentic_loop.py` and `api/src/agents/architectures/krishna_memgpt.py` already had local modifications.

## Executive Summary

The agents module is functional and has improved seams around prompt rendering, tool command registration, and loop testing. It is not a low-quality module. The main issue is that the orchestration surface has grown from a short chat loop into a production agent runtime without a matching runtime abstraction.

For short interactive turns, the implementation is acceptable. For long-running or autonomous agent work, it falls below the standard set by current agent frameworks:

- OpenAI Agents SDK models the run loop as a runner: model call, final output check, handoff/tool execution, append results, repeat, with max-turn exceptions and run configuration for tracing, tool errors, concurrency, and state.
- LangGraph treats persistence/checkpointing as core infrastructure for long-running stateful agents, interruptions, fault tolerance, and replay.
- LangChain human-in-the-loop middleware pauses before risky tool calls using persisted graph state and resumes later.
- CrewAI Flows and AutoGen both separate agent behavior from runtime/lifecycle concerns, with explicit state or runtime management.

The biggest code smell is not the presence of abstractions. It is that the most important abstraction, the agent run, is missing. As a result, `KrishnaMemGPTArchitecture.handle_message(...)` and `run_agentic_tool_loop(...)` carry too much lifecycle policy.

## External Baseline

Primary references checked:

- OpenAI Agents SDK running loop: https://openai.github.io/openai-agents-python/running_agents/
- OpenAI Agents SDK tools, timeouts, tool error handling: https://openai.github.io/openai-agents-python/tools/
- OpenAI Agents SDK tracing: https://openai.github.io/openai-agents-python/tracing/
- LangGraph persistence: https://langchain-5e9cc07a.mintlify.app/oss/python/langgraph/persistence
- LangChain human-in-the-loop: https://docs.langchain.com/oss/python/langchain/human-in-the-loop
- AutoGen runtime: https://microsoft.github.io/autogen/dev/user-guide/core-user-guide/framework/agent-and-agent-runtime.html
- CrewAI flow persistence: https://github.com/crewAIInc/crewAI/blob/main/docs/v1.15.12/en/concepts/flows.mdx

Common production-agent standards across those systems:

- A runner/runtime owns the loop, lifecycle, state, cancellation, and errors.
- Agent definitions or strategies configure instructions, tools, model settings, and optional behavior.
- Tool policy is explicit: timeout, error mode, concurrency, approval, and input/output validation.
- Long-running work is checkpointed or persisted; streaming is an attachment to the run, not the only owner of the run.
- Observability has structured run/model/tool spans or events.

## What Is Working Well

- `api/src/agents/tool_execution.py` is now a thin command-registry adapter. That is a reasonable use of the Command Pattern and avoids hardcoding every tool family in the loop.
- `api/src/agents/tool_runtime/commands.py` colocates provider-facing tool definitions with execution metadata. That is the right direction.
- `api/src/agents/architectures/krishna_memgpt_prompt.py` and Jinja templates keep prompt composition out of the main architecture file.
- `api/tests/test_agentic_loop.py`, `api/tests/test_async_tool_runtime.py`, and `api/tests/test_tool_execution_commands.py` cover key behavior: tool call ids, runtime events, internal marker filtering, prompt refresh, and async wait/check paths.
- The internal design docs already identify the correct direction, especially `api/docs/LLD-durable-agent-orchestration.md`.

## Findings

### High: The Agentic Loop Is An Overloaded State Machine

References:

- `api/src/agents/agentic_loop.py:103`
- `api/src/agents/agentic_loop.py:113`
- `api/src/agents/agentic_loop.py:133`
- `api/src/agents/agentic_loop.py:183`
- `api/src/agents/agentic_loop.py:267`
- `api/src/agents/agentic_loop.py:353`
- `api/src/agents/agentic_loop.py:374`

`run_agentic_tool_loop(...)` owns all of these concerns:

- provider streaming
- visible text filtering
- provider-context mutation
- tool batching
- tool execution
- runtime event draining
- async job tracking
- synthetic wait/check calls
- prompt-refresh signaling
- max-iteration behavior
- final response nudging
- completion payload construction

That violates Single Responsibility and makes the loop hard to reason about. OpenAI's runner loop is conceptually small: call model, classify output, execute handoff/tools, append results, repeat, fail on max turns. This code has the same core loop, but embeds several product policies inside it.

Impact:

- Adding cancellation, retries, tracing, or durable resume will require editing the loop instead of adding runtime policy around it.
- Small changes can alter termination behavior in surprising ways.
- The loop is difficult to test exhaustively because state is spread across local flags.

Recommendation:

Split the loop into small policy components without changing behavior first:

- `ModelTurnCollector`: streams provider events into `{text, tool_calls, stop_reason}`.
- `ToolBatchExecutor`: executes tool calls and emits runtime/tool events.
- `LoopContextAppender`: appends assistant tool-use and user tool-result messages.
- `AsyncJobSupervisor`: owns async job wait/check policy.
- `LoopTerminationPolicy`: owns max turns, final-response-after-tools, and async deadlines.

This is less ambitious than a full framework rewrite and creates natural tests for the tricky cases.

### High: Async Jobs Are Controlled Twice, By The Model And By Hidden Runtime Logic

References:

- `api/src/agents/agentic_loop.py:163`
- `api/src/agents/agentic_loop.py:244`
- `api/src/agents/agentic_loop.py:267`
- `api/src/agents/agentic_loop.py:404`
- `api/src/tools/native/handlers.py:122`
- `api/src/skills/service.py:434`
- `api/src/agents/tool_runtime/jobs/service.py:62`

The async flow asks the model to call `wait` and `check_tool_job`, but the loop also injects synthetic `wait` and `check_tool_job` events when the model does not. This creates two controllers for one state machine.

The `wait` tool also performs a real `asyncio.sleep(...)` inside the agent turn. With defaults and caps, one browser SSE request can intentionally remain open for minutes. The in-process background job starts via `asyncio.create_task(...)`, so a process restart can leave the job incomplete even though job state exists.

Impact:

- The loop depends on prompt compliance for part of control flow, then overrides the model with hidden control flow.
- Runtime-only synthetic tool calls can appear in tool timelines and audits as if the model requested them.
- Long waits consume an API worker/SSE connection and are fragile across deploys or disconnects.
- Failure handling is split between job status, loop exceptions, and architecture catch-all SSE errors.

Recommendation:

Move wait/check into deterministic runtime policy:

- Treat async start payloads as internal control data, not as a normal tool result.
- Let the runtime poll `ToolJobService` with a short sleep loop or end the turn with a durable pending run status.
- Only call the LLM after the job reaches `succeeded` or `failed`, or after a bounded "still running" response policy.
- Keep `wait` hidden or programmatic-only if it remains exposed to the model.

This aligns better with LangGraph-style persistence and OpenAI runner-style tool execution policy.

### High: There Is No Durable Agent Run Boundary

References:

- `api/src/agents/router.py:406`
- `api/src/agents/router.py:446`
- `api/src/agents/architectures/base.py:81`
- `api/src/agents/architectures/krishna_memgpt.py:249`
- `api/docs/LLD-durable-agent-orchestration.md:5`
- `api/docs/LLD-durable-agent-orchestration.md:90`

The streaming request currently owns the run. Automations and schedules consume the same stream through `handle_message_buffered(...)`. This means provider calls, partial text, tool starts/results, prompt refresh, and final status are not persisted as a coherent run.

Impact:

- Client disconnect loses the live execution path.
- Process restart loses loop state.
- There is no replayable event log for debugging.
- Partial output before failure is not modeled clearly.
- There is no run-level cancellation or heartbeat.

Recommendation:

Implement the existing `LLD-durable-agent-orchestration.md` direction in phases:

1. Add `AgentRun` and `AgentRunEvent` around the existing architecture stream.
2. Stream persisted events to dashboard/widget clients.
3. Move message persistence and provider/loop lifecycle into a shared run engine.
4. Turn `KrishnaMiniArchitecture` and `KrishnaMemGPTArchitecture` into preparation/refresh strategies.

This is the most important structural simplification. It removes lifecycle duplication and makes long-running work survivable.

### Medium: Max-Turn Behavior Silently Completes Instead Of Failing Explicitly

References:

- `api/src/common/constants.py:17`
- `api/src/agents/agentic_loop.py:120`
- `api/src/agents/agentic_loop.py:127`
- `api/src/agents/agentic_loop.py:359`
- `api/src/agents/agentic_loop.py:374`

The loop breaks when `model_iterations >= MAX_TOOL_ITERATIONS` and there is no active async job. It then emits `complete` with the accumulated text. In common agent runtimes, exceeding the turn budget is a distinct terminal condition, often an exception such as max-turns-exceeded.

Impact:

- A stuck tool loop can look like a successful completion.
- Callers cannot distinguish a normal final answer from a stopped runaway loop.
- Tests may miss degraded behavior because `complete` is emitted either way.

Recommendation:

Introduce a distinct terminal event or exception:

- `MaxToolIterationsExceeded`
- or `AgenticLoopEvent(kind="failed", payload={"reason": "max_tool_iterations"})`

Then decide at the architecture/run layer whether to surface it as an SSE error, a model-visible final fallback, or a retryable run failure.

### Medium: Tool Metadata Exists But Is Mostly Inert

References:

- `api/src/agents/tool_runtime/commands.py:25`
- `api/src/agents/tool_runtime/commands.py:28`
- `api/src/agents/tool_runtime/commands.py:30`
- `api/src/agents/tool_runtime/commands.py:31`
- `api/src/tools/native/specs.py:25`
- `api/src/agents/tool_runtime/skills.py:67`
- `api/src/agents/tool_execution.py:49`
- `api/src/agents/agentic_loop.py:211`

The code declares useful metadata: idempotency, timeout, and parallel safety. Today only `mutates_prompt_context` materially affects behavior. There is no timeout enforcement, no retry policy, and no metadata-aware parallel execution.

Impact:

- The metadata creates a false sense of safety.
- `execute_skill_action` and `call_mcp_tool` are classified as non-idempotent, but nothing prevents retries or clarifies uncertain execution state.
- Read-only calls marked `allow_parallel=True` still run sequentially.

Recommendation:

Make metadata operational before adding more metadata:

- Enforce `timeout_seconds` with `asyncio.wait_for(...)`.
- Add `timeout_behavior` or reuse the existing model-visible error policy.
- Use idempotency when implementing durable retry/resume.
- Either remove `allow_parallel` until used, or implement explicit `parallel_tools` as documented in `api/docs/LLD-tool-command-execution.md`.

### Medium: The Architecture Abstraction Is Too Broad

References:

- `api/src/agents/architectures/base.py:45`
- `api/src/agents/architectures/base.py:59`
- `api/src/agents/architectures/krishna_mini.py:64`
- `api/src/agents/architectures/krishna_memgpt.py:92`
- `api/src/agents/architectures/krishna_mini.py:90`
- `api/src/agents/architectures/krishna_memgpt.py:150`
- `api/src/agents/architectures/krishna_mini.py:161`
- `api/src/agents/architectures/krishna_memgpt.py:383`

`AgentArchitecture.handle_message(...)` is responsible for saving messages, building context, loading credentials, calling the provider, looping, translating events, and saving the assistant response. The abstract method is typed as a regular `def` returning `AsyncIterator`, while implementations are `async def` async generators and suppress Pyright override errors.

Impact:

- SOLID issue: the abstraction forces every architecture to own unrelated lifecycle concerns.
- Code duplication exists between Mini and MemGPT for user-message save, provider settings, provider calls, assistant save, stream completion, and error conversion.
- Type ignores hide a real contract mismatch.

Recommendation:

Make architecture a strategy instead of a lifecycle owner:

- `prepare_turn(request) -> AgentRunPlan`
- `refresh_prompt(plan, state) -> str`
- optional `loop_enabled` or `tools_for_state`

Move persistence, provider invocation, event translation, and final status into a run service/engine.

### Medium: Provider-Neutral Models Are Bypassed By Hand-Built Dict Protocols

References:

- `api/src/llm/messages.py:14`
- `api/src/llm/messages.py:19`
- `api/src/llm/messages.py:27`
- `api/src/agents/agentic_loop.py:185`
- `api/src/agents/agentic_loop.py:190`
- `api/src/agents/agentic_loop.py:236`
- `api/src/llm/providers/openai.py:110`
- `api/src/agents/agentic_loop.py:466`

The repo has `TextBlock`, `ToolUseBlock`, and `ToolResultBlock`, but the loop appends raw dicts using Bedrock-style keys (`toolUse`, `toolResult`, `toolUseId`). OpenAI then converts tool uses/results into text markers, and the loop filters those markers back out of streamed text.

Impact:

- Provider-specific wire format leaks into the provider-neutral loop.
- Internal marker filtering is a symptom that transport encoding has become visible to user text.
- Adding a new provider or changing OpenAI Responses input format requires touching loop behavior or filters.

Recommendation:

Have the loop append `ChatMessage`/content block objects or a single canonical dict shape with explicit `type` fields:

- `{"type": "tool_use", "id": ..., "name": ..., "input": ...}`
- `{"type": "tool_result", "tool_use_id": ..., "content": ...}`

Let providers translate that canonical representation at the edge.

### Medium: Hidden Ambient Runtime Coupling Through ContextVar

References:

- `api/src/agents/turn_runtime.py:16`
- `api/src/agents/turn_runtime.py:22`
- `api/src/agents/turn_runtime.py:66`
- `api/src/agents/agentic_loop.py:105`
- `api/src/agents/agentic_loop.py:433`

`AgentTurnRuntime` gives tools a way to emit progress events while a tool call is executing. That is useful. The smell is that tools depend on ambient context rather than an explicit event sink or runtime context.

Impact:

- Tool behavior changes depending on whether a context variable is set.
- Runtime events are not persisted and are not tied to a durable run id.
- Queue overflow handling is local and not visible to run status.

Recommendation:

Keep the queue short term, but pass an explicit `AgentRuntimeContext` or `EventSink` through `AgentTurnState`. In a durable run engine, the sink should persist events and optionally stream them.

### Medium: Multi-Value Returns Hide Meaning At Important Boundaries

References:

- `api/src/tools/native/handlers.py:142`
- `api/src/tools/native/handlers.py:154`
- `api/src/tools/native/handlers.py:155`
- `api/src/llm/messages.py:52`
- `api/src/llm/messages.py:62`
- `api/src/llm/providers/openai.py:36`
- `api/src/llm/providers/anthropic.py:19`
- `api/src/llm/providers/bedrock.py:206`
- `api/src/llm/providers/gemini.py:48`
- `api/src/agents/image_generation/storage.py:60`
- `api/src/agents/image_generation/service.py:511`
- `api/src/agents/repository.py:97`

Several methods return tuples such as `(system_prompt, messages)`, `(block_name, block_def, error)`, `(agent, conversation)`, `(bytes, content_type)`, and `(items, cursor)`. Python makes this easy, but these are not throwaway local computations. They cross module boundaries and carry domain meaning.

Impact:

- Call sites rely on positional unpacking instead of names.
- Adding a third or fourth return value becomes easy and opaque.
- Error-bearing tuples such as `(value, object, error)` mix success and failure paths.
- Reviewers must jump to the callee to remember tuple slot meaning.

Recommendation:

Adopt a convention: public methods, service methods, repository methods, provider adapters, and agent-loop helpers should return one named object. Use a frozen dataclass for internal runtime objects and Pydantic models for API/domain objects that need validation or serialization.

Tiny local functions used only as sort keys can remain tuple-based if they do not escape the local function. For example, `sort_key(...) -> tuple[int, str]` inside `api/src/llm/models.py` is not the same risk as a repository or provider method returning multiple values.

### Medium: Factory Instantiates Every Architecture For Each Lookup

References:

- `api/src/agents/architectures/factory.py:31`
- `api/src/agents/architectures/krishna_mini.py:56`
- `api/src/agents/architectures/krishna_memgpt.py:79`

`get_agent_architecture(...)` constructs both `KrishnaMiniArchitecture` and `KrishnaMemGPTArchitecture` before choosing one. These constructors create repositories and services.

Impact:

- Unneeded DynamoDB/service setup on every request.
- Future constructors with heavier dependencies will make this worse.
- It hides dependency failures for architectures that were not requested.

Recommendation:

Use a lazy mapping:

```python
factories = {
    "krishna-mini": KrishnaMiniArchitecture,
    "krishna-memgpt": KrishnaMemGPTArchitecture,
}
return factories[architecture_name](message_repository=message_repository)
```

### Low: NativeToolHandler Stores Per-Turn Context On A Mutable Handler Instance

References:

- `api/src/agents/architectures/krishna_memgpt.py:120`
- `api/src/agents/architectures/krishna_memgpt.py:121`
- `api/src/agents/architectures/krishna_memgpt.py:136`
- `api/src/tools/native/handlers.py:79`
- `api/src/tools/native/handlers.py:83`
- `api/src/tools/native/handlers.py:87`
- `api/src/tools/native/handlers.py:91`

The architecture sets conversation, user, and KB context on `NativeToolHandler` before execution. Because the current factory creates a new architecture per request, this is unlikely to race today. But the object shape invites future caching/reuse bugs.

Impact:

- If architectures or handlers become singletons, concurrent turns can leak context.
- Tests that monkeypatch instance state do not reveal concurrency hazards.

Recommendation:

Pass `AgentTurnState` into native tool execution and remove mutable context setters. The existing `NativeToolExecutorAdapter` already has access to `state`.

### Low: Catch-All Error Handling Makes Failures Recoverable By Default

References:

- `api/src/agents/tool_execution.py:63`
- `api/src/agents/architectures/krishna_mini.py:181`
- `api/src/agents/architectures/krishna_memgpt.py:417`
- `api/src/agents/router.py:460`

Returning model-visible tool errors is a good default for normal tool failures. The smell is that fatal runtime failures, validation bugs, provider failures, and cancellation are not strongly typed at the architecture boundary.

Impact:

- Product behavior depends on where an exception happens.
- Fatal orchestration errors can be reduced to `str(e)` in an SSE event.
- There is no consistent retry classification.

Recommendation:

Define error categories:

- recoverable tool error, returned as a tool result
- model/provider failure
- max-turn failure
- cancellation
- authorization/configuration failure
- persistence failure

Then map them to SSE/run status in one place.

## SOLID Assessment

Single Responsibility:

- Weak in `run_agentic_tool_loop(...)` and architecture classes.
- Stronger in prompt templates, tool registry, and job repository.

Open/Closed:

- Tool addition is reasonably extensible through `ToolCommandRegistry`.
- Loop policy is not open for extension; async, timeout, prompt refresh, and final response rules require editing the loop.

Liskov Substitution:

- The architecture interface has a typing mismatch. Implementations require `pyright: ignore[reportIncompatibleMethodOverride]`.

Interface Segregation:

- `AgentArchitecture` is too broad. Callers need a run, but implementations must provide an entire streaming lifecycle.

Dependency Inversion:

- Some dependencies are injectable (`message_repository`), but many are constructed inside architectures and services.
- Tool execution uses protocols well; native tools still rely on mutable setter context.

Return Shape:

- Important module-boundary methods should return one named object instead of tuples.
- Internal dataclasses are enough for loop/provider helper results; Pydantic is preferable when the object is persisted, serialized, or externally validated.

## Is It Over-Complicated?

Yes, but not evenly.

Appropriate complexity:

- Prompt templates and section loaders are justified.
- The tool command registry is justified because native, skill, and MCP tools have different backends.
- The job repository/service split is justified.

Over-complicated or misplaced complexity:

- Async job waiting is too agentic. It should be runtime-controlled.
- The loop is doing too many jobs directly.
- Tool metadata is more abstract than current behavior requires.
- The architecture abstraction is named as strategy but implemented as a full application service.
- Provider-neutral message support exists but the loop still hand-builds provider-shaped dicts.

Missing simplifying abstraction:

- `AgentRun` / `AgentRunEngine`.

## Recommended Refactor Path

Do not rewrite everything. The safest path is incremental.

1. Fix the architecture type contract.
   - Change `AgentArchitecture.handle_message(...)` to an async-generator-compatible abstract method shape or a Protocol.
   - Remove the Pyright ignores in `krishna_mini.py` and `krishna_memgpt.py`.

2. Make max-turn exhaustion explicit.
   - Add a `MaxToolIterationsExceeded` terminal path.
   - Add tests proving normal final output and max-turn failure are distinct.

3. Make tool metadata real.
   - Enforce per-tool timeouts.
   - Add a model-visible timeout result for recoverable tools.
   - Keep retry/idempotency inactive until a durable run boundary exists.

4. Extract loop helpers around existing behavior.
   - Start with context appenders and async job supervision.
   - Keep public event names unchanged.

5. Add a durable run log around the existing stream.
   - Follow `api/docs/LLD-durable-agent-orchestration.md`.
   - Persist SSE events before changing user-facing streaming behavior.

6. Collapse architecture classes into strategies.
   - `KrishnaMini` prepares a no-tool single-turn plan.
   - `KrishnaMemGPT` prepares memory/tools/prompt and refreshes prompt after memory mutation.
   - A shared engine owns persistence, provider calls, loop, and final status.

## Concrete Code Change Guide

The snippets below are intended as implementation guidance. They are not one atomic patch. Apply them in order, keep tests green after each phase, and preserve current SSE event names until the durable run layer is in place.

### Cross-Cutting Rule: Return One Named Object

Convention:

- Do not return multiple values from public methods, service methods, repository methods, provider adapters, architecture methods, or loop helpers.
- Return one named object: a frozen dataclass for internal runtime/helper results, or a Pydantic model for persisted/API/domain results.
- Avoid result shapes like `(value, error)`, `(object, cursor)`, `(system_prompt, messages)`, or `(agent, conversation)`.
- Prefer explicit success/failure models or exceptions over tuples that carry an error slot.

Good:

```python
@dataclass(frozen=True)
class MessageSplit:
    system_prompt: str | None
    conversation: list[ChatMessage]


def split_system_messages(messages: list[ChatMessage]) -> MessageSplit:
    system_chunks: list[str] = []
    conversation: list[ChatMessage] = []
    ...
    return MessageSplit(
        system_prompt="\n\n".join(system_chunks) or None,
        conversation=conversation,
    )
```

Avoid:

```python
def split_system_messages(messages: list[ChatMessage]) -> tuple[str | None, list[ChatMessage]]:
    ...
    return system_prompt, conversation
```

Call sites become self-documenting:

```python
split = split_system_messages(normalize_messages(messages))
request_body = provider.convert_messages(split.conversation)
instructions = split.system_prompt or DEFAULT_INSTRUCTIONS
```

Use Pydantic when the object is part of a repository/API contract:

```python
class PaginatedAgents(BaseModel):
    items: list[Agent]
    cursor: dict[str, Any] | None = None
```

Use dataclasses when the object is a private runtime helper:

```python
@dataclass(frozen=True)
class LoadedAgentConversation:
    agent: Agent
    conversation: Conversation
```

### Phase 1: Make Architecture Factory Lazy

Problem addressed:

- `get_agent_architecture(...)` constructs every architecture for every lookup.

Target file:

- `api/src/agents/architectures/factory.py`

Replace the eager dictionary with constructor references:

```python
from collections.abc import Callable

from .base import AgentArchitecture
from .krishna_mini import KrishnaMiniArchitecture
from .krishna_memgpt import KrishnaMemGPTArchitecture
from src.messages.repositories import MessageRepository


ArchitectureFactory = Callable[..., AgentArchitecture]


def get_agent_architecture(
    architecture_name: str,
    *,
    message_repository: MessageRepository | None = None,
) -> AgentArchitecture:
    factories: dict[str, ArchitectureFactory] = {
        "krishna-mini": KrishnaMiniArchitecture,
        "krishna-memgpt": KrishnaMemGPTArchitecture,
    }

    factory = factories.get(architecture_name)
    if not factory:
        supported = ", ".join(factories.keys())
        raise ValueError(
            f"Unknown architecture: '{architecture_name}'. Supported: {supported}"
        )

    return factory(message_repository=message_repository)
```

Expected tests:

```bash
cd api
uv run pytest tests/test_agent_architecture_base.py tests/test_agents_router.py
```

### Phase 2: Fix The Architecture Type Contract

Problem addressed:

- `AgentArchitecture.handle_message(...)` is declared as a normal abstract method returning `AsyncIterator`, while implementations are async generators and need Pyright ignores.

Target files:

- `api/src/agents/architectures/base.py`
- `api/src/agents/architectures/krishna_mini.py`
- `api/src/agents/architectures/krishna_memgpt.py`

Minimal low-churn option: make the base method an async generator shape by adding a dead `yield`. This lets subclasses remain async generators.

```python
class AgentArchitecture(ABC):
    @abstractmethod
    async def handle_message(
        self,
        agent: "Agent",
        conversation: "Conversation",
        user_message: str,
        owner_email: str,
        actor_email: str,
        actor_id: str,
        attachments: list["Attachment"] | None = None,
    ) -> AsyncIterator["SSEEvent"]:
        if False:
            yield SSEEvent(
                event_type=SSEEventType.ERROR,
                content="abstract method placeholder",
            )
        raise NotImplementedError
```

Then remove these suppressions:

```python
async def handle_message( # pyright: ignore[reportIncompatibleMethodOverride]
```

becomes:

```python
async def handle_message(
```

Cleaner later option: replace `AgentArchitecture` with a `Protocol` and move `handle_message_buffered(...)` to a separate helper/service. That fits the long-term run-engine direction better, but the dead-yield version is a small first step.

Expected tests:

```bash
cd api
uv run pytest tests/test_agent_architecture_base.py tests/test_krishna_memgpt_tool_audit.py
```

### Phase 3: Make Max-Turn Exhaustion Explicit

Problem addressed:

- The loop can hit `MAX_TOOL_ITERATIONS` and still emit a normal `complete` event.

Target files:

- `api/src/agents/agentic_loop.py`
- `api/src/agents/architectures/krishna_memgpt.py`
- `api/tests/test_agentic_loop.py`

Add a clear terminal event path:

```python
# api/src/agents/agentic_loop.py

MAX_ITERATIONS_REASON = "max_tool_iterations"


def _max_iterations_exceeded(
    *,
    model_iterations: int,
    active_async_jobs: dict[str, dict[str, Any]],
    needs_async_final_response: bool,
) -> bool:
    return (
        not active_async_jobs
        and not needs_async_final_response
        and model_iterations >= MAX_TOOL_ITERATIONS
    )
```

Use it in the loop instead of a plain `break`:

```python
if _max_iterations_exceeded(
    model_iterations=model_iterations,
    active_async_jobs=active_async_jobs,
    needs_async_final_response=needs_async_final_response,
):
    yield AgenticLoopEvent(
        kind="failed",
        payload={
            "reason": MAX_ITERATIONS_REASON,
            "message": (
                "Agent stopped because it reached the maximum tool iterations "
                f"({MAX_TOOL_ITERATIONS}) before producing a final answer."
            ),
        },
    )
    return
```

Handle that event in MemGPT:

```python
# api/src/agents/architectures/krishna_memgpt.py

elif loop_event.kind == "failed":
    yield SSEEvent(
        event_type=SSEEventType.ERROR,
        content=loop_event.payload.get("message", "Agent run failed"),
    )
    return
```

Add a focused test:

```python
class AlwaysToolProvider:
    async def stream_response(self, context, credentials, tools, model):
        yield FakeProviderEvent(
            type="tool_use",
            tool_name="lookup_customer",
            tool_input={"customer_id": "cus_123"},
            tool_use_id=f"tooluse_{len(context)}",
        )
        yield FakeProviderEvent(type="stop")


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
```

Expected tests:

```bash
cd api
uv run pytest tests/test_agentic_loop.py tests/test_async_tool_runtime.py
```

### Phase 4: Replace Tuple Returns With Named Objects

Problem addressed:

- Important methods return positional tuples instead of named objects.

Target files:

- `api/src/llm/messages.py`
- `api/src/llm/providers/openai.py`
- `api/src/llm/providers/anthropic.py`
- `api/src/llm/providers/bedrock.py`
- `api/src/llm/providers/gemini.py`
- `api/src/tools/native/handlers.py`
- `api/src/agents/repository.py`
- `api/src/agents/image_generation/service.py`
- `api/src/agents/image_generation/storage.py`
- `api/src/agents/image_generation/provider.py`

#### LLM message split

Before:

```python
def split_system_messages(messages: list[ChatMessage]) -> tuple[str | None, list[ChatMessage]]:
    ...
    return "\n\n".join(system_chunks) or None, conversation
```

After:

```python
@dataclass(frozen=True)
class MessageSplit:
    system_prompt: str | None
    conversation: list[ChatMessage]


def split_system_messages(messages: list[ChatMessage]) -> MessageSplit:
    system_chunks: list[str] = []
    conversation: list[ChatMessage] = []
    for message in messages:
        if message.role == "system":
            text = content_text(message.content).strip()
            if text:
                system_chunks.append(text)
        else:
            conversation.append(message)

    return MessageSplit(
        system_prompt="\n\n".join(system_chunks) or None,
        conversation=conversation,
    )
```

Provider call site:

```python
split = split_system_messages(normalize_messages(messages))
return split.system_prompt or "You are a helpful assistant.", split.conversation
```

Then make provider methods return named objects too:

```python
@dataclass(frozen=True)
class OpenAIRequestInput:
    instructions: str
    messages: list[ChatMessage]


def _extract_instructions_and_messages(self, messages: list[dict]) -> OpenAIRequestInput:
    split = split_system_messages(normalize_messages(messages))
    return OpenAIRequestInput(
        instructions=split.system_prompt or "You are a helpful assistant.",
        messages=split.conversation,
    )
```

OpenAI usage:

```python
request_input = self._extract_instructions_and_messages(messages)
body = self._request_body(
    model_id,
    request_input.instructions,
    request_input.messages,
    tools,
)
```

Anthropic usage:

```python
@dataclass(frozen=True)
class AnthropicRequestInput:
    system_prompt: str | None
    messages: list[dict[str, Any]]


def _extract_system_and_messages(self, messages: list[dict]) -> AnthropicRequestInput:
    split = split_system_messages(normalize_messages(messages))
    return AnthropicRequestInput(
        system_prompt=split.system_prompt,
        messages=self._convert_messages(split.conversation),
    )
```

#### Native memory block lookup

Before:

```python
def _get_block_or_error(
    self, args: dict, agent_id: str, user_id: str
) -> tuple[str, Optional[MemoryBlockDefinition], Optional[str]]:
    block_name = normalize_block_name(args["block"])
    block_def = self.memory_repo.get_block_definition(agent_id, user_id, block_name)
    if not block_def:
        return block_name, None, f"Error: Block [{block_name}] does not exist."
    return block_name, block_def, None
```

After:

```python
@dataclass(frozen=True)
class MemoryBlockLookup:
    block_name: str
    block_def: MemoryBlockDefinition | None = None
    error: str | None = None

    @property
    def found(self) -> bool:
        return self.block_def is not None and self.error is None


def _get_block_or_error(
    self,
    args: dict,
    agent_id: str,
    user_id: str,
) -> MemoryBlockLookup:
    block_name = normalize_block_name(args["block"])
    block_def = self.memory_repo.get_block_definition(agent_id, user_id, block_name)
    if not block_def:
        return MemoryBlockLookup(
            block_name=block_name,
            error=f"Error: Block [{block_name}] does not exist.",
        )
    return MemoryBlockLookup(block_name=block_name, block_def=block_def)
```

Call site:

```python
lookup = self._get_block_or_error(args, agent_id, user_id)
if lookup.error:
    return lookup.error

assert lookup.block_def is not None
memory = self.memory_repo.get_core_memory(agent_id, user_id, lookup.block_name)
```

Better still, after error categories are introduced, split success/failure instead of returning model-visible error strings from the lookup helper.

#### Repository pagination

Before:

```python
def list_agent2agent_enabled(...) -> tuple[list[Agent], Optional[dict]]:
    ...
    return agents[:bounded_limit], exclusive_start_key
```

After:

```python
class AgentPage(BaseModel):
    items: list[Agent]
    cursor: dict[str, Any] | None = None


def list_agent2agent_enabled(...) -> AgentPage:
    ...
    return AgentPage(
        items=agents[:bounded_limit],
        cursor=exclusive_start_key,
    )
```

Call site:

```python
page = repo.list_agent2agent_enabled(limit=limit, cursor=cursor)
return AgentDiscoveryResponse(items=page.items, cursor=page.cursor)
```

#### Image service loading

Before:

```python
def _load_agent_and_conversation(...) -> tuple[Agent, Conversation]:
    ...
    return agent, conversation
```

After:

```python
@dataclass(frozen=True)
class AgentConversationContext:
    agent: Agent
    conversation: Conversation


def _load_agent_and_conversation(...) -> AgentConversationContext:
    ...
    return AgentConversationContext(agent=agent, conversation=conversation)
```

#### Storage image payload

Before:

```python
def get_image(self, key: str) -> tuple[bytes, str]:
    ...
    return body, str(content_type)
```

After:

```python
@dataclass(frozen=True)
class StoredImage:
    body: bytes
    content_type: str


def get_image(self, key: str) -> StoredImage:
    ...
    return StoredImage(body=body, content_type=str(content_type))
```

Expected tests:

```bash
cd api
uv run pytest tests/test_openai_provider.py tests/test_anthropic_provider.py tests/test_bedrock_provider.py tests/test_gemini_provider.py tests/test_agents_repository.py tests/test_agent_image_generation_service.py
```

### Phase 5: Make Tool Timeout Metadata Real

Problem addressed:

- `ToolCommandMetadata.timeout_seconds` exists but is not enforced.

Target files:

- `api/src/agents/tool_execution.py`
- `api/src/agents/tool_runtime/commands.py`
- `api/src/tools/native/specs.py`
- `api/tests/test_tool_execution_commands.py`

Update router execution:

```python
# api/src/agents/tool_execution.py

import asyncio


class ToolExecutionRouter:
    async def execute(
        self,
        *,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str,
        state: AgentTurnState,
    ) -> ToolExecutionOutcome:
        try:
            command = self._registry.get(tool_name)
            request = ToolCommandRequest(
                tool_name=tool_name,
                tool_input=tool_input,
                tool_use_id=tool_use_id,
                state=state,
            )
            execution = command.execute(request)
            if command.metadata.timeout_seconds:
                outcome = await asyncio.wait_for(
                    execution,
                    timeout=command.metadata.timeout_seconds,
                )
            else:
                outcome = await execution

            if command.metadata.mutates_prompt_context and outcome.success:
                state.prompt_dirty = True
            return outcome

        except TimeoutError:
            log.warning(
                "Tool execution timed out: tool=%s tool_use_id=%s",
                tool_name,
                tool_use_id,
            )
            return ToolExecutionOutcome(
                result=f"Error: Tool '{tool_name}' timed out before completing.",
                success=False,
            )
        except Exception as e:
            log.error(
                "Tool execution error: tool=%s tool_use_id=%s err=%s",
                tool_name,
                tool_use_id,
                e,
                exc_info=True,
            )
            return ToolExecutionOutcome(result=f"Error: {str(e)}", success=False)
```

Important detail: only set `prompt_dirty` when the mutating command succeeds. The current code marks it after command execution even if a command returns a failed outcome from inside the command layer.

Add default metadata values that reflect actual runtime expectations:

```python
READ_ONLY_NATIVE = ToolCommandMetadata(
    category=ToolCommandCategory.NATIVE,
    idempotency=ToolIdempotency.READ_ONLY,
    timeout_seconds=30,
    allow_parallel=True,
)

IDEMPOTENT_MEMORY_WRITE = ToolCommandMetadata(
    category=ToolCommandCategory.NATIVE,
    idempotency=ToolIdempotency.IDEMPOTENT_WRITE,
    mutates_prompt_context=True,
    timeout_seconds=30,
)
```

For `wait`, use a longer explicit timeout or no timeout if the loop owns the async deadline:

```python
WAIT_METADATA = ToolCommandMetadata(
    category=ToolCommandCategory.NATIVE,
    idempotency=ToolIdempotency.READ_ONLY,
    timeout_seconds=ASYNC_TOOL_MAX_IN_TURN_WAIT_SECONDS + 5,
)
```

If importing the loop constant from native specs creates a cycle, define a local `WAIT_TOOL_TIMEOUT_SECONDS = 605` near native specs until the constants are moved to a shared runtime settings module.

Add tests:

```python
class SlowCommand:
    name = "slow_tool"
    definition = {"name": "slow_tool", "parameters": {"type": "object"}}
    metadata = ToolCommandMetadata(
        category=ToolCommandCategory.NATIVE,
        idempotency=ToolIdempotency.READ_ONLY,
        timeout_seconds=0.01,
    )

    async def execute(self, request):
        await asyncio.sleep(1)
        return ToolExecutionOutcome(result="late", success=True)


async def test_router_returns_failed_outcome_on_tool_timeout():
    registry = ToolCommandRegistry([SlowCommand()])
    router = ToolExecutionRouter(
        skill_runtime=FakeSkillRuntime(),
        native_tools=FakeNativeTools(),
        mcp_runtime=FakeMCPRuntime(),
        registry=registry,
    )

    outcome = await router.execute(
        tool_name="slow_tool",
        tool_input={},
        tool_use_id="tool-1",
        state=_state(),
    )

    assert outcome.success is False
    assert "timed out" in outcome.result
```

Expected tests:

```bash
cd api
uv run pytest tests/test_tool_execution_commands.py tests/test_async_tool_runtime.py
```

### Phase 6: Extract Context Appending From The Loop

Problem addressed:

- The loop hand-builds provider-shaped `toolUse` and `toolResult` blocks inline.

Target files:

- Add `api/src/agents/loop_context.py`
- Update `api/src/agents/agentic_loop.py`
- Add `api/tests/test_agentic_loop_context.py`

Create a small context helper first. Keep the current dict shape to avoid provider behavior changes in this phase:

```python
# api/src/agents/loop_context.py

from __future__ import annotations

from typing import Any


def append_assistant_tool_uses(
    context: list[dict[Any, Any]],
    *,
    iteration_text: str,
    tool_events: list[Any],
) -> None:
    assistant_content: list[dict[str, Any]] = []

    if iteration_text.strip():
        assistant_content.append({"text": iteration_text})

    for tool_event in tool_events:
        tool_use = {
            "toolUseId": tool_event.tool_use_id,
            "name": tool_event.tool_name,
            "input": tool_event.tool_input,
        }
        thought_signature = getattr(tool_event, "thought_signature", None)
        if thought_signature:
            tool_use["thoughtSignature"] = thought_signature
        assistant_content.append({"toolUse": tool_use})

    context.append({"role": "assistant", "content": assistant_content})


def tool_result_block(tool_use_id: str, result: str) -> dict[str, Any]:
    return {
        "toolResult": {
            "toolUseId": tool_use_id,
            "content": [{"text": result}],
        }
    }


def append_user_tool_results(
    context: list[dict[Any, Any]],
    tool_results: list[dict[str, Any]],
) -> None:
    context.append({"role": "user", "content": tool_results})
```

Then replace the inline block in `run_agentic_tool_loop(...)`:

```python
from src.agents.loop_context import (
    append_assistant_tool_uses,
    append_user_tool_results,
    tool_result_block,
)


if pending_tool_calls:
    append_assistant_tool_uses(
        context,
        iteration_text=iteration_text,
        tool_events=pending_tool_calls,
    )

    tool_results: list[dict[str, Any]] = []
    ...
    tool_results.append(tool_result_block(tool_event.tool_use_id, outcome.result))
    ...
    append_user_tool_results(context, tool_results)
```

Tests should assert exact context shape for:

- assistant text plus tool use
- tool use with `thoughtSignature`
- user tool result

This is intentionally boring. It makes later canonical-message migration much safer.

### Phase 7: Move Async Job Polling Into A Runtime Supervisor

Problem addressed:

- Async wait/check is split between model prompt instructions and hidden synthetic tool calls.

Target files:

- Add `api/src/agents/async_jobs.py`
- Update `api/src/agents/agentic_loop.py`
- Update `api/tests/test_async_tool_runtime.py`

First extraction should preserve behavior. The loop should ask a helper what synthetic calls are required.

```python
# api/src/agents/async_jobs.py

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any


@dataclass
class SyntheticToolEvent:
    tool_name: str
    tool_input: dict[str, Any]
    tool_use_id: str


@dataclass
class AsyncJobSupervisor:
    max_wait_seconds: int
    wait_seconds: int = 20
    active_jobs: dict[str, dict[str, Any]] = field(default_factory=dict)
    wait_cycles: int = 0
    deadline_at: float | None = None

    def track_tool_result(self, result: str) -> bool:
        payload = self._extract_status(result)
        if not payload:
            return False
        if payload.get("status") in {"queued", "running"}:
            self.active_jobs[str(payload["job_id"])] = payload
            self.deadline_at = self.deadline_at or time.monotonic() + self.max_wait_seconds
            return True
        return False

    def mark_checked(self, job_id: str, result: str) -> bool:
        payload = self._extract_status(result)
        if payload and payload.get("status") in {"succeeded", "failed"}:
            self.active_jobs.pop(job_id, None)
            return True
        return False

    def next_wait_call_if_needed(self, *, has_pending_model_tool_calls: bool) -> SyntheticToolEvent | None:
        if has_pending_model_tool_calls or not self.active_jobs:
            return None
        return SyntheticToolEvent(
            tool_name="wait",
            tool_input={
                "seconds": self.wait_seconds,
                "reason": "waiting for async tool job completion",
            },
            tool_use_id=f"auto_wait_{self.wait_cycles + 1}",
        )

    def check_calls_after_wait(self) -> list[SyntheticToolEvent]:
        self.wait_cycles += 1
        return [
            SyntheticToolEvent(
                tool_name="check_tool_job",
                tool_input={"job_id": job_id},
                tool_use_id=f"auto_check_{job_id}_{self.wait_cycles}",
            )
            for job_id in list(self.active_jobs)
        ]

    def deadline_expired(self) -> bool:
        return self.deadline_at is not None and time.monotonic() >= self.deadline_at

    @staticmethod
    def _extract_status(result: str) -> dict[str, Any] | None:
        try:
            payload = json.loads(result)
        except Exception:
            return None
        if not isinstance(payload, dict):
            return None
        if payload.get("async") is True and payload.get("status") and payload.get("job_id"):
            return payload
        return None
```

Then simplify the loop local variables:

```python
async_jobs = AsyncJobSupervisor(
    max_wait_seconds=ASYNC_TOOL_MAX_IN_TURN_WAIT_SECONDS,
)
```

Replace these scattered variables:

```python
active_async_jobs
async_wait_cycles
async_deadline_at
```

with supervisor calls:

```python
if async_jobs.active_jobs and async_jobs.deadline_expired():
    raise AsyncToolJobStillRunningError(...)

wait_event = async_jobs.next_wait_call_if_needed(
    has_pending_model_tool_calls=bool(pending_tool_calls),
)
if wait_event:
    pending_tool_calls.append(wait_event)
    has_tool_calls = True
    yield _tool_call_start_event(wait_event)

...

if async_jobs.track_tool_result(outcome.result):
    async_job_starts.append(json.loads(outcome.result))

...

if tool_event.tool_name == "wait" and async_jobs.active_jobs:
    for check_event in async_jobs.check_calls_after_wait():
        ...
        terminal = async_jobs.mark_checked(
            str(check_event.tool_input["job_id"]),
            check_outcome.result,
        )
        needs_async_final_response = needs_async_final_response or terminal
```

This phase still keeps synthetic calls. A later phase can replace `wait` tool execution with deterministic polling:

```python
async def poll_until_terminal(
    *,
    job_service: ToolJobService,
    jobs: dict[str, dict[str, Any]],
    state: AgentTurnState,
    deadline_at: float,
    poll_interval_seconds: float = 2.0,
) -> list[dict[str, Any]]:
    while jobs and time.monotonic() < deadline_at:
        await asyncio.sleep(poll_interval_seconds)
        for job_id in list(jobs):
            status = job_service.check_job_for_agent(
                job_id=job_id,
                owner_email=state.owner_email,
                actor_email=state.actor_email,
                agent_id=state.agent_id,
                conversation_id=state.conversation_id,
            )
            if status["status"] in {"succeeded", "failed"}:
                jobs.pop(job_id, None)
                yield status
```

Expected tests:

```bash
cd api
uv run pytest tests/test_async_tool_runtime.py tests/test_agentic_loop.py
```

### Phase 8: Pass Native Tool Context Explicitly

Problem addressed:

- `NativeToolHandler` stores per-turn context on mutable instance attributes.

Target files:

- `api/src/agents/tool_runtime/executors.py`
- `api/src/tools/native/handlers.py`
- `api/src/agents/architectures/krishna_memgpt.py`

Add an explicit state-based execution path:

```python
# api/src/tools/native/handlers.py

from src.agents.runtime_state import AgentTurnState


class NativeToolHandler:
    async def execute_with_state(
        self,
        tool_name: str,
        arguments: dict,
        state: AgentTurnState,
    ) -> str:
        handler = getattr(self, f"_handle_{tool_name}", None)
        if not handler:
            raise ValueError(f"Unknown tool: {tool_name}")

        if tool_name.startswith(self.MEMORY_TOOL_PREFIXES):
            return await handler(arguments, state.agent_id, state.actor_id)

        if tool_name == "recall_conversation":
            return await self._handle_recall_conversation_with_conversation_id(
                arguments,
                state.agent_id,
                state.conversation_id,
            )

        if tool_name == "knowledge_base_search":
            return await self._handle_knowledge_base_search_with_kb_ids(
                arguments,
                state.agent_id,
                state.linked_kb_ids,
            )

        return await handler(arguments, state.agent_id)
```

Then update the adapter:

```python
# api/src/agents/tool_runtime/executors.py

class NativeToolExecutorAdapter:
    async def execute(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        state: AgentTurnState,
    ) -> str:
        if hasattr(self._native_tools, "execute_with_state"):
            return await self._native_tools.execute_with_state(
                tool_name,
                tool_input,
                state,
            )
        return await self._native_tools.execute(tool_name, tool_input, state.agent_id)
```

After all native handlers use explicit state, remove:

```python
self.tool_handler.set_conversation_context(conversation.conversation_id)
self.tool_handler.set_user_context(actor_id)
self.tool_handler.set_knowledge_base_context(state.linked_kb_ids)
```

and remove the mutable fields from `NativeToolHandler`.

Expected tests:

```bash
cd api
uv run pytest tests/test_tool_execution_commands.py tests/test_async_tool_runtime.py tests/test_krishna_memgpt_tool_audit.py
```

### Phase 9: Add A Durable Run Wrapper Before Rewriting The Loop

Problem addressed:

- SSE currently owns the run lifecycle.

Target files to add:

- `api/src/agents/runs/models.py`
- `api/src/agents/runs/repository.py`
- `api/src/agents/runs/service.py`
- `api/src/agents/runs/events.py`

Start with a wrapper around the existing stream. This gives persistence and replay without changing the current loop.

```python
# api/src/agents/runs/models.py

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


class AgentRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class AgentRun(BaseModel):
    run_id: str = Field(default_factory=lambda: f"agentrun_{uuid4().hex}")
    agent_id: str
    conversation_id: str
    owner_email: str
    actor_email: str
    actor_id: str
    architecture_name: str
    provider_name: str
    model_name: str | None = None
    user_message: str
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    response_text: str = ""
    status: AgentRunStatus = AgentRunStatus.PENDING
    error: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None


class AgentRunEvent(BaseModel):
    run_id: str
    sequence: int
    event_type: str
    content: str = ""
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
```

Service wrapper:

```python
# api/src/agents/runs/service.py

class AgentRunService:
    def create_run(
        self,
        *,
        agent: Agent,
        conversation: Conversation,
        user_message: str,
        owner_email: str,
        actor_email: str,
        actor_id: str,
    ) -> AgentRun:
        run = AgentRun(
            agent_id=agent.agent_id,
            conversation_id=conversation.conversation_id,
            owner_email=owner_email,
            actor_email=actor_email,
            actor_id=actor_id,
            architecture_name=agent.agent_architecture,
            provider_name=agent.agent_provider,
            model_name=agent.agent_model,
            user_message=user_message,
        )
        return self.repository.save_run(run)

    async def execute_existing_architecture_stream(
        self,
        run: AgentRun,
        *,
        architecture: AgentArchitecture,
        agent: Agent,
        conversation: Conversation,
        attachments: list[Attachment],
    ) -> AgentRun:
        self.repository.mark_running(run.run_id)
        try:
            async for event in architecture.handle_message(
                agent=agent,
                conversation=conversation,
                user_message=run.user_message,
                owner_email=run.owner_email,
                actor_email=run.actor_email,
                actor_id=run.actor_id,
                attachments=attachments,
            ):
                self.repository.append_event(run.run_id, event)
                self.repository.apply_sse_event(run.run_id, event)

            return self.repository.mark_succeeded(run.run_id)
        except Exception as exc:
            return self.repository.mark_failed(run.run_id, str(exc))
```

Route shape after wrapper:

```python
run = run_service.create_run(
    agent=agent,
    conversation=conversation,
    user_message=body.content,
    owner_email=user_email,
    actor_email=user_email,
    actor_id=user_id,
)

asyncio.create_task(
    run_service.execute_existing_architecture_stream(
        run,
        architecture=architecture,
        agent=agent,
        conversation=conversation,
        attachments=cast(list[Attachment], body.attachments or []),
    )
)

return StreamingResponse(
    run_service.stream_events(run.run_id),
    media_type="text/event-stream",
    headers={"Cache-Control": "no-cache", "Connection": "keep-alive"},
)
```

This still uses in-process execution initially. The value is that event persistence and run status become visible before the larger engine rewrite.

Expected tests:

```bash
cd api
uv run pytest tests/test_agents_router.py tests/test_widget.py tests/test_automations_runner.py
```

### Phase 10: Collapse Architectures Into Turn Strategies

Problem addressed:

- Architecture classes own lifecycle instead of describing architecture-specific behavior.

Target files after durable wrapper exists:

- `api/src/agents/runs/engine.py`
- `api/src/agents/architectures/base.py`
- `api/src/agents/architectures/krishna_mini.py`
- `api/src/agents/architectures/krishna_memgpt.py`

New strategy contract:

```python
@dataclass
class AgentRunPlan:
    context: list[dict[str, Any]]
    credentials: dict[str, Any]
    tools: list[dict[str, Any]]
    state: AgentTurnState
    loop_enabled: bool


class AgentArchitectureStrategy(Protocol):
    name: str

    async def prepare_turn(
        self,
        *,
        agent: Agent,
        conversation: Conversation,
        user_message: str,
        owner_email: str,
        actor_email: str,
        actor_id: str,
        attachments: list[Attachment],
    ) -> AgentRunPlan:
        ...

    async def refresh_prompt(
        self,
        *,
        plan: AgentRunPlan,
    ) -> str:
        ...
```

Shared engine lifecycle:

```python
class AgentRunEngine:
    async def execute(self, run_id: str) -> AgentRun:
        run = self.repository.mark_running(run_id)
        agent, conversation = self._load_inputs(run)
        strategy = self.strategy_factory.get(agent.agent_architecture)

        user_msg = self.message_service.save_user_message(run)
        self.repository.set_user_message_id(run_id, user_msg.message_id)

        plan = await strategy.prepare_turn(
            agent=agent,
            conversation=conversation,
            user_message=run.user_message,
            owner_email=run.owner_email,
            actor_email=run.actor_email,
            actor_id=run.actor_id,
            attachments=run.attachments,
        )

        if plan.loop_enabled:
            result = await self.loop_runner.run(plan, event_sink=self.event_sink)
        else:
            result = await self.single_turn_runner.run(plan, event_sink=self.event_sink)

        assistant_msg = self.message_service.save_assistant_message(
            run,
            result.full_text,
        )
        return self.repository.mark_succeeded(
            run_id,
            assistant_message_id=assistant_msg.message_id,
            response_text=result.full_text,
        )
```

After this phase:

- routes no longer call `architecture.handle_message(...)`
- automations no longer buffer an SSE stream
- the loop no longer owns persistence
- architectures no longer save messages

This is the final simplification target.

## Implementation Rules For Follow-Up Agents

- Preserve SSE event names until a frontend migration explicitly changes them.
- Return one named object from public/service/repository/provider/helper boundaries; do not introduce new multi-value tuple returns.
- Keep the agentic loop and router generic. Do not add `if tool_name == ...` dependency wiring in callers.
- Every default tool command must declare an input model, output model, and context type on its `ToolSpec`.
- Add new per-family context objects through `ToolContextResolver`; do not add broad optional fields to `AgentTurnState` just because one tool needs them.
- Do not remove tool audit messages until a durable `AgentRunStep` replacement exists.
- Keep tool exceptions model-visible unless the failure is a runtime/persistence/cancellation failure.
- Do not retry `execute_skill_action` or `call_mcp_tool` automatically until idempotency is enforced.
- Keep OpenAI/Anthropic/Bedrock/Gemini provider conversion at the provider edge. The loop should not learn new provider wire formats.
- Add tests in the same phase as each behavior change. Do not batch all tests at the end.
- When changing async job behavior, prove these three cases: queued/running, succeeded, failed.
- When adding durability, first wrap the existing stream, then move ownership into the engine.

## Suggested Tests To Add

- Max iteration exceeded emits/fails distinctly and does not report normal completion.
- Tool timeout returns a model-visible timeout result for recoverable tools.
- Non-idempotent tool interrupted during durable retry does not re-execute automatically.
- Provider error after partial text records partial output but marks run failed.
- Synthetic wait/check calls are not saved as model-requested tool audits, if runtime polling remains hidden.
- Concurrent MemGPT turns do not share native handler context.
- OpenAI marker text from prior tool calls cannot leak into user-visible stream.

## Implemented Phase: Explicit Tool Contracts

The implementation now keeps callers generic while making each default tool declare its own input, output, and context contract:

```python
ToolSpec(WAIT, READ_ONLY_NATIVE, WaitInput, NativeToolContext)
```

The router still receives the same generic call:

```python
await router.execute(
    tool_name=tool_name,
    tool_input=tool_input,
    tool_use_id=tool_use_id,
    state=state,
)
```

The command adapter validates input and resolves context based on the selected command spec:

```python
parsed_input = request.parse_input(self._spec.input_model)
context = request.resolve_context(self._spec.context_type)
```

Built-in tools currently return model-visible text, so their output contract is the shared `ToolTextOutput` model before the router wraps it in `ToolExecutionOutcome`:

```python
output = self._spec.output_model.model_validate({"result": result})
return ToolExecutionOutcome(result=output.result, success=True)
```

The dependency map lives behind `ToolContextResolver`, not in the loop:

```python
resolver.register(
    NativeToolContext,
    lambda: NativeToolContext(
        agent_id=state.agent_id,
        user_id=state.actor_id,
        conversation_id=state.conversation_id,
        linked_kb_ids=list(state.linked_kb_ids),
    ),
)
```

This gives future tool authors a clear extension rule:

- add a Pydantic input model for the tool arguments
- add a Pydantic output model for the tool result
- add or reuse a narrow context type
- register the context factory centrally
- attach the contracts to `ToolSpec`
- keep the agentic loop unchanged

## Bottom Line

The module is near a tipping point. The command registry and prompt split are good local improvements, but the agentic loop and architecture classes have absorbed too much runtime responsibility. The next high-value move is not another design pattern around tools. It is a durable agent-run boundary and a smaller deterministic loop policy.
