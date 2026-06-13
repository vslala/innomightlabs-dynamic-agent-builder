# Durable Agent Orchestration

## Problem

The `api/src/agents` module has grown around a streaming `AgentArchitecture.handle_message(...)` contract. That contract works for short dashboard and widget chats, but it is now also used by automations and scheduled wakeups through `handle_message_buffered(...)`.

The result is that long-running autonomous work is coupled to an in-process async iterator and, for interactive callers, an open HTTP/SSE request. This makes one-hour agent runs fragile:

- If the HTTP client disconnects, the run has no durable owner.
- If the API process exits, the loop state is lost.
- Tool calls, tool results, partial assistant text, prompt refreshes, and runtime events are not replayable from a single run log.
- Automations and schedules buffer the same stream in memory instead of invoking a durable run primitive.
- The current loop stops only by `MAX_TOOL_ITERATIONS`; there is no explicit wall-clock budget, heartbeat, cancellation, lease, checkpoint, or resume contract.

The goal is to simplify orchestration by moving common turn/run behavior into one durable invocation engine while preserving current use cases:

- Dashboard chat SSE.
- Widget chat SSE and widget `generate_text`.
- Scheduled agent messages.
- Automation `invoke_agent` nodes.
- Krishna Mini direct response behavior.
- Krishna MemGPT memory, knowledge base, skill, MCP, image generation runtime events, tool audit messages, and prompt refresh on memory mutation.

## Current State

### Entry Points

- Dashboard streaming: `api/src/agents/router.py`
  - `POST /agents/{agent_id}/{conversation_id}/send-message`
  - Loads agent and conversation, then streams `architecture.handle_message(...)`.
- Widget streaming: `api/src/widget/router.py`
  - `POST /widget/conversations/{conversation_id}/messages`
  - Builds a `Conversation` shim and streams the same architecture contract.
- Widget text generation: `api/src/widget/router.py`
  - Calls `architecture.handle_message_buffered(...)`.
- Automations: `api/src/automations/runner.py`
  - `AutomationRunner._execute_node(...)` calls `handle_message_buffered(...)`.
- Scheduler: `api/src/scheduler/executors.py`
  - `AgentScheduledMessageExecutor.execute(...)` calls `handle_message_buffered(...)`.

### Architecture Implementations

- `api/src/agents/architectures/krishna_mini.py`
  - Saves user message.
  - Loads provider credentials.
  - Builds a fixed-window conversation context.
  - Streams a single provider response.
  - Saves assistant message.
- `api/src/agents/architectures/krishna_memgpt.py`
  - Loads linked KBs, enabled skills, enabled MCP connections, provider credentials, and core memory.
  - Builds a system prompt through `krishna_memgpt_prompt.py` and Jinja templates.
  - Builds conversation context with `FixedWindowStrategy`.
  - Builds tools from native tools, knowledge tools, skills, and MCP runtime tools.
  - Runs `run_agentic_tool_loop(...)`.
  - Converts loop events to SSE.
  - Saves tool audit messages as `Message(role="system")`.
  - Emits UI form events when skill results contain a form payload.
  - Rebuilds the system prompt after core-memory writes.
  - Saves final assistant text as one message.

### Loop and Tool Boundaries

- `api/src/agents/agentic_loop.py`
  - Owns the iterative `LLM -> tool calls -> tool results -> LLM` pattern.
  - Keeps `full_response`, provider context, pending tool calls, runtime events, and text filtering in memory.
  - Executes tool calls sequentially.
  - Emits `prompt_refresh_needed` when `state.prompt_dirty` is set.
- `api/src/agents/tool_execution.py`
  - Routes `load_skill` / `execute_skill_action` to `SkillRuntimeService`.
  - Routes MCP runtime tools to `MCPConnectorService`.
  - Routes everything else to `NativeToolHandler`.
  - Converts exceptions into tool result strings.
- `api/src/agents/turn_runtime.py`
  - Provides a turn-local event queue through `ContextVar`.
  - Used by tools such as image generation to emit runtime SSE events while the tool call is running.
- `api/src/tools/native/handlers.py`
  - Implements memory, recall, and KB tools.
  - Core-memory writes are mostly idempotent and should be preserved.

### Provider Constraints

- `api/src/llm/providers/openai.py`
  - Uses streaming HTTP with `httpx.AsyncClient(timeout=60.0)`.
  - Sends `store=False`.
  - Converts prior tool calls/results into text markers for OpenAI Responses input.
- `api/src/llm/providers/anthropic.py`
  - Uses streaming Anthropic messages.
  - Emits text, tool use, and stop events.

Provider streams are not a durable execution record. The application must own run state.

## Design Goals

1. Make an agent invocation durable enough to run for up to one hour without an attached human client.
2. Keep dashboard/widget streaming UX by streaming from persisted run events, not from ephemeral orchestration state.
3. Make scheduled and automation agent calls use the same invocation primitive as chat.
4. Preserve current behavior before simplifying internals.
5. Make every externally visible side effect observable, retry-aware, and replayable.
6. Keep architecture-specific behavior in small strategy objects, not in route handlers.
7. Avoid adding a generic framework that obscures the current domains: memory, tools, providers, messages, skills, MCP, automations.

## Proposed Architecture

Introduce a durable invocation engine under `api/src/agents/runs/`.

```text
api/src/agents/
+-- runs/
|   +-- models.py          # AgentRun, AgentRunEvent, AgentRunStep, enums
|   +-- repository.py      # DynamoDB persistence and conditional updates
|   +-- service.py         # create/start/cancel/get/list/replay run APIs
|   +-- engine.py          # durable orchestration loop
|   +-- context.py         # system prompt + conversation + checkpoint context
|   +-- checkpoints.py     # compacted provider context and resume state
|   +-- events.py          # event sink, SSE replay helpers
|   +-- worker.py          # async Lambda/local worker entrypoint
+-- architectures/
|   +-- base.py            # slim architecture strategy interface
|   +-- krishna_mini.py
|   +-- krishna_memgpt.py
+-- agentic_loop.py        # eventually reduced or folded into engine.py
+-- tool_execution.py
+-- runtime_state.py
+-- turn_runtime.py
```

The main simplification is a single owner for the invocation lifecycle:

```text
Route / Scheduler / Automation / Widget
        |
        v
AgentRunService.create_run(...)
        |
        +--> interactive caller attaches to persisted event stream
        |
        +--> background worker calls AgentRunEngine.execute(run_id)
```

`KrishnaMiniArchitecture` and `KrishnaMemGPTArchitecture` should become strategies that describe how to prepare a turn, not classes that own message persistence, provider streaming, event conversion, and final run status.

## Data Model

Store run records in the existing DynamoDB single-table design.

### AgentRun

```python
class AgentRunStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    WAITING_FOR_INPUT = "waiting_for_input"
    CANCELLING = "cancelling"
    CANCELLED = "cancelled"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"


class AgentRunMode(str, Enum):
    INTERACTIVE = "interactive"
    BACKGROUND = "background"
    AUTOMATION = "automation"
    SCHEDULED = "scheduled"
    WIDGET = "widget"


class AgentRun(BaseModel):
    run_id: str
    agent_id: str
    conversation_id: str
    owner_email: str
    actor_email: str
    actor_id: str
    mode: AgentRunMode
    status: AgentRunStatus = AgentRunStatus.PENDING
    architecture_name: str
    provider_name: str
    model_name: str | None = None
    user_message: str
    user_message_id: str | None = None
    assistant_message_id: str | None = None
    response_text: str = ""
    request: dict[str, Any] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    lease_owner: str | None = None
    lease_expires_at: datetime | None = None
    heartbeat_at: datetime | None = None
    max_runtime_seconds: int = 3600
    max_tool_iterations: int
    iteration_count: int = 0
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    updated_at: datetime | None = None
```

Suggested keys:

```text
pk = AGENT_RUN#{run_id}
sk = METADATA

GSI owner runs:
gsi1pk = USER#{owner_email}
gsi1sk = AGENT_RUN#{created_at}#{run_id}

GSI conversation runs:
gsi2pk = CONVERSATION#{conversation_id}
gsi2sk = AGENT_RUN#{created_at}#{run_id}
```

If adding GSIs is too much for phase one, store only `pk/sk` and query through known run ids from conversations/automation outputs. Add list endpoints later.

### AgentRunEvent

Persist every streamable event and every important internal transition.

```python
class AgentRunEvent(BaseModel):
    run_id: str
    sequence: int
    event_type: SSEEventType | str
    content: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
```

Keys:

```text
pk = AGENT_RUN#{run_id}
sk = EVENT#{sequence:012d}
```

The sequence must be allocated atomically. The simplest implementation is a conditional counter on `AgentRun.state["next_event_sequence"]`, or a repository method that updates the run record then writes the event.

### AgentRunStep

Use steps for durable tool/provider attempts. This is separate from user-visible events.

```python
class AgentRunStepStatus(str, Enum):
    STARTED = "started"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    RETRYING = "retrying"
    SKIPPED = "skipped"


class AgentRunStep(BaseModel):
    run_id: str
    step_id: str
    sequence: int
    kind: Literal["provider_call", "tool_call", "prompt_refresh", "checkpoint"]
    name: str
    status: AgentRunStepStatus
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None
    attempt: int = 1
    idempotency_key: str | None = None
    started_at: datetime
    completed_at: datetime | None = None
```

Keys:

```text
pk = AGENT_RUN#{run_id}
sk = STEP#{sequence:012d}#{step_id}
```

## Public API

### Start Run

Add an internal service method first:

```python
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
        mode: AgentRunMode,
        attachments: list[Attachment] | None = None,
        max_runtime_seconds: int = 3600,
    ) -> AgentRun:
        ...
```

Then route behavior can evolve without changing every caller at once.

Dashboard and widget streaming routes should:

1. Validate ownership synchronously.
2. Create an `AgentRun`.
3. Start async execution.
4. Return an SSE stream that reads `AgentRunEvent` records by sequence.

Automation and scheduler callers should:

1. Create a run with `mode=AUTOMATION` or `mode=SCHEDULED`.
2. Start async execution.
3. Poll or await completion through `AgentRunService.wait_for_terminal(...)` only when the caller itself is already a background worker.

### Get Run

```http
GET /agents/runs/{run_id}
```

Returns run metadata, status, message ids, response text, error, and timestamps.

### Replay Events

```http
GET /agents/runs/{run_id}/events?after_sequence=123
```

Returns persisted events. Streaming clients can reconnect and resume from the last sequence they received.

### Cancel Run

```http
POST /agents/runs/{run_id}/cancel
```

Sets `status=CANCELLING`. The engine checks cancellation before provider calls, before tool calls, after tool calls, and between iterations.

## Engine Contract

The durable engine owns the lifecycle:

```python
class AgentRunEngine:
    async def execute(self, run_id: str) -> AgentRun:
        run = self.repository.acquire_lease(run_id, owner=self.worker_id)
        try:
            await self._mark_running(run)
            plan = await self._prepare(run)
            result = await self._run_loop(run, plan)
            return await self._complete_success(run, result)
        except CancelledRun:
            return await self._complete_cancelled(run)
        except ExpiredRun:
            return await self._complete_expired(run)
        except Exception as exc:
            return await self._complete_failed(run, exc)
        finally:
            self.repository.release_lease(run_id, owner=self.worker_id)
```

The engine should use one event sink:

```python
class AgentRunEventSink:
    async def emit_sse(self, run_id: str, event: SSEEvent) -> None: ...
    async def emit_internal(self, run_id: str, event_type: str, payload: dict[str, Any]) -> None: ...
```

Routes only serialize persisted events. Architectures and tools do not call `yield` directly.

## Architecture Strategy Interface

Replace the current broad `handle_message(...)` responsibility with a smaller strategy surface:

```python
class AgentArchitectureStrategy(Protocol):
    name: str

    async def prepare(self, request: AgentRunRequest) -> AgentRunPlan:
        ...

    async def refresh_prompt(self, plan: AgentRunPlan, state: AgentTurnState) -> str:
        ...
```

`AgentRunPlan` contains already-loaded state:

```python
class AgentRunPlan(BaseModel):
    system_prompt: str | None = None
    context: list[dict[str, Any]]
    credentials: dict[str, Any]
    tools: list[dict[str, Any]]
    turn_state: AgentTurnState
    loop_enabled: bool
```

Krishna Mini:

- `loop_enabled=False`
- no tools
- system prompt from persona and timestamp

Krishna MemGPT:

- `loop_enabled=True`
- native tools always
- knowledge tools when KB links exist
- skill tools when skills are enabled
- MCP tools when MCP connections are enabled
- prompt refresh uses existing core-memory snapshot logic

This keeps architecture-specific decisions local while removing duplicated persistence and stream handling.

## Durable Loop Behavior

The first engine version can preserve the existing provider context format:

```python
for iteration in range(run.max_tool_iterations):
    self._check_runtime_budget(run)
    self._check_cancelled(run)
    provider_result = await self._call_provider_and_persist_events(...)
    if not provider_result.tool_calls:
        break
    for tool_call in provider_result.tool_calls:
        self._check_cancelled(run)
        outcome = await self._execute_tool_with_step(...)
        context.append(tool_result_block(outcome))
    if state.prompt_dirty:
        context[0]["content"] = await strategy.refresh_prompt(...)
        state.prompt_dirty = False
    await self._checkpoint(...)
```

Important changes:

- Persist text chunks as `AgentRunEvent`.
- Append text chunks to `AgentRun.response_text` periodically, not only at the end.
- Persist tool call starts/results as both events and steps.
- Persist runtime events from `AgentTurnRuntime` through the event sink.
- Heartbeat during provider streaming and tool execution.
- Save a checkpoint after each provider iteration and after each tool batch.
- Enforce `max_runtime_seconds`, defaulting to 3600 for autonomous runs.
- Use `MAX_TOOL_ITERATIONS` as one stop condition, not the only stop condition.

## Checkpoints and Resume

For phase one, checkpoint enough to make failure visible and replayable:

```python
class AgentRunCheckpoint(BaseModel):
    run_id: str
    sequence: int
    iteration_count: int
    context: list[dict[str, Any]]
    response_text: str
    turn_state: dict[str, Any]
    created_at: datetime
```

Keys:

```text
pk = AGENT_RUN#{run_id}
sk = CHECKPOINT#{sequence:012d}
```

Resume policy:

- If a worker dies before a tool step starts, retry from the last checkpoint.
- If a worker dies during a tool step, retry only when the tool declares an idempotency policy.
- If a tool is not retry-safe, mark the run `FAILED` with a clear recovery message.

Phase two should add tool-level idempotency metadata:

```python
class ToolIdempotency(str, Enum):
    READ_ONLY = "read_only"
    IDEMPOTENT_WRITE = "idempotent_write"
    NON_IDEMPOTENT_WRITE = "non_idempotent_write"
```

Known current classification:

- `core_memory_read`, `core_memory_list_blocks`, `archival_memory_search`, `recall_conversation`, `knowledge_base_search`: `READ_ONLY`
- `core_memory_append`, `core_memory_replace`, `core_memory_delete`, `archival_memory_insert`: mostly `IDEMPOTENT_WRITE`
- `execute_skill_action`: depends on action manifest and should default to `NON_IDEMPOTENT_WRITE`
- `call_mcp_tool`: default `NON_IDEMPOTENT_WRITE`
- image generation actions: default `NON_IDEMPOTENT_WRITE` unless request idempotency is added

This avoids silently repeating external side effects such as sending email, deleting files, or posting to a third-party service.

## Worker and Lease Model

Reuse the existing async job pattern documented in `api/docs/LLD-async-automation-test-run.md`.

Add a Lambda/local worker event:

```json
{
  "agent_run": {
    "run_id": "..."
  }
}
```

Repository lease rules:

- `acquire_lease(run_id, owner, ttl_seconds)` succeeds only when:
  - status is `pending` or `running`, and
  - no lease exists or `lease_expires_at < now`.
- Worker extends lease every 15-30 seconds.
- If `heartbeat_at` is stale and lease has expired, another worker may resume.
- A run cannot exceed `max_runtime_seconds`.

For AWS Lambda, one invocation can run up to 15 minutes. To support one-hour runs, the worker must be able to continue itself before timeout:

```python
if lambda_remaining_time_ms < 60_000 and not run_terminal:
    await checkpoint()
    await requeue_agent_run(run_id)
    return
```

The worker should re-invoke itself asynchronously with the same `run_id`. The next worker resumes from the latest checkpoint.

## Streaming UX

SSE should become an attachment to the run log.

Interactive route flow:

```python
run = run_service.create_run(...)
run_service.dispatch_async(run.run_id)
return StreamingResponse(run_service.stream_events(run.run_id))
```

`stream_events(...)` should:

- Query events after the last emitted sequence.
- Yield them in order.
- Sleep briefly when no event is available and the run is non-terminal.
- Stop when a terminal run status is observed and all events are emitted.
- Support reconnect through `after_sequence` or `Last-Event-ID`.

This preserves the current UI event stream while making disconnects harmless.

## Message Persistence

Current behavior saves:

- user message at the start
- tool audit messages as `role="system"`
- assistant message at the end if non-empty

Keep this behavior, but move ownership to the engine:

1. On run start, save the user `Message` and set `run.user_message_id`.
2. During each tool result, save the existing audit message format and persist ids in step output if useful.
3. During response streaming, append to `run.response_text`.
4. On success, save one assistant `Message` with final text and set `run.assistant_message_id`.
5. If the run fails after partial text, do not save a normal assistant message unless product wants partial answers in chat history. Persist partial text on the run either way.

Open question: whether failed or cancelled runs with partial assistant text should create a visible assistant message.

## Runtime Events

Keep `AgentTurnRuntime` initially, but route it into the durable event sink:

- `IMAGE_GENERATION_STARTED`
- `IMAGE_GENERATION_PARTIAL`
- `IMAGE_GENERATION_COMPLETE`
- future progress events

The queue remains useful for tool-local progress, but it should no longer be the only event path. The engine drains it and persists each event.

## Tool Execution Policy

Extend tool routing with metadata:

```python
class ToolSpec(BaseModel):
    name: str
    schema: dict[str, Any]
    executor: ToolExecutor
    idempotency: ToolIdempotency
    timeout_seconds: int = 120
    retry_policy: RetryPolicy = RetryPolicy.none()
```

Phase one can wrap existing definitions instead of rewriting every tool:

- Native tools: metadata map in `api/src/tools/native/definitions.py`.
- Skills: derive metadata from skill manifest; default action idempotency to non-idempotent unless manifest says otherwise.
- MCP: default to non-idempotent.

Tool result policy:

- Tool exceptions continue returning model-visible error strings for recoverable tool failures.
- Engine failures such as checkpoint write failure, lease loss, cancellation, or expired run should stop the run.
- Tool timeouts should return a tool result if the agent can recover; repeated timeouts should fail the run.

## Context and Compaction

Current `FixedWindowStrategy` should remain the initial conversation strategy. Add run-context compaction separately from chat history:

- Conversation context: user/assistant messages selected by `FixedWindowStrategy`.
- Run context: provider messages, tool calls, tool results, and checkpoint summaries generated during a long autonomous run.
- Core memory: existing memory snapshot in system prompt.
- Archival memory and recall tools: existing tools.

When checkpoint context grows too large:

1. Summarize older provider/tool transcript into a compact checkpoint message.
2. Preserve recent tool calls/results verbatim.
3. Preserve unresolved goals, known constraints, current plan, completed work, pending work, and external side effects.

There is already a template compaction strategy in `api/src/messages/repositories/compaction.py`; reuse the pattern but create an agent-run-specific template so compaction does not masquerade as a user chat message.

## Migration Plan

### Phase 1: Durable Run Log Around Existing Architectures

Add:

- `api/src/agents/runs/models.py`
- `api/src/agents/runs/repository.py`
- `api/src/agents/runs/service.py`
- `api/src/agents/runs/events.py`

Wrap existing `architecture.handle_message(...)`:

- Create `AgentRun`.
- Execute current architecture in a background worker.
- Persist every yielded `SSEEvent` as `AgentRunEvent`.
- Update run status and response text.
- Stream persisted events to dashboard/widget.

This gives reconnect/replay/status without changing the loop internals yet.

Tests:

- Run creation persists metadata.
- Streaming event replay returns ordered events.
- Failed architecture marks run failed.
- Dashboard route still emits existing SSE event types.
- Widget route still emits existing SSE event types.

### Phase 2: Shared Engine Owns Persistence

Move message save, provider config, event conversion, response accumulation, and final status out of `krishna_mini.py` and `krishna_memgpt.py` into `AgentRunEngine`.

Change architectures into prepare/refresh strategies.

Tests:

- Krishna Mini saves user and assistant messages as before.
- Krishna MemGPT emits tool start/result events as before.
- Tool audit messages are saved as before.
- UI form render event behavior is unchanged.
- Prompt refresh after core-memory write is unchanged.
- `handle_message_buffered(...)` compatibility still works or delegates to runs.

### Phase 3: Worker Lease, Heartbeat, Cancellation, Runtime Budget

Add:

- lease acquire/extend/release
- heartbeat
- cancellation endpoint
- max runtime enforcement
- Lambda self-continuation before timeout

Tests:

- Second worker cannot acquire an active lease.
- Expired lease can be acquired.
- Cancellation stops before the next provider/tool call.
- Run expires after runtime budget.
- Worker requeues before Lambda timeout when run is not terminal.

### Phase 4: Checkpoints and Resume

Persist checkpoints after each loop iteration and tool batch.

Add resume from latest checkpoint.

Tests:

- Provider failure before a tool can resume from checkpoint.
- Read-only tool can be retried.
- Non-idempotent tool in-progress failure marks run failed unless the tool provides idempotency.
- Response text is not duplicated after resume.
- Event sequence remains monotonic after resume.

### Phase 5: Tool Metadata and Retry Policy

Add tool idempotency, timeout, and retry policy metadata.

Tests:

- Native memory write idempotency classification.
- Skill action defaults to non-idempotent.
- MCP call defaults to non-idempotent.
- Tool timeout returns model-visible error or fails according to policy.

## Files Most Likely To Change

- `api/src/agents/architectures/base.py`
  - Add or adapt strategy interface.
- `api/src/agents/architectures/krishna_mini.py`
  - Reduce to prepare strategy after phase 2.
- `api/src/agents/architectures/krishna_memgpt.py`
  - Reduce to prepare/refresh strategy after phase 2.
- `api/src/agents/agentic_loop.py`
  - Move durable loop mechanics into `runs/engine.py` or have the engine call a refactored loop.
- `api/src/agents/tool_execution.py`
  - Add metadata-aware outcomes and retry/idempotency hooks.
- `api/src/agents/runtime_state.py`
  - Add serializable fields required for checkpoint/resume.
- `api/src/agents/router.py`
  - Create runs and stream run events.
- `api/src/widget/router.py`
  - Create runs and stream run events.
- `api/src/automations/runner.py`
  - Use `AgentRunService` for invoke-agent nodes.
- `api/src/scheduler/executors.py`
  - Use `AgentRunService` for scheduled agent messages.
- `api/src/llm/providers/openai.py`
  - Consider configurable timeout and provider call metadata; do not rely on `store=True` for application durability.
- `api/src/tools/native/definitions.py`
  - Add native tool metadata.
- `api/src/skills/models.py`
  - Later: add action idempotency/timeout metadata to skill manifests.

## Clarifying Questions

1. Should failed or cancelled runs with partial assistant text create a visible assistant chat message, or should partial text live only on the run record?
2. Is one hour the desired hard maximum for all autonomous runs, or should it be configurable per agent, schedule, automation node, or user plan?
3. For external side-effect tools such as Gmail, Google Drive, and MCP, should the first durable version fail on uncertain retry state, or should we add idempotency keys to selected actions immediately?
4. Do we want long-running interactive dashboard/widget requests to keep an open SSE stream when possible, or should the frontend switch to a run-status page with polling/reconnect as the primary UX?

## Recommendation

Implement phase 1 first. It gives immediate reliability improvements with low behavioral risk because the current architecture still runs underneath. Then implement phase 2 to get the real simplification: one run engine that owns persistence, event streaming, provider calls, loop progress, and final status for every caller.

Do not start by rewriting the tool layer. The current native tool idempotency and prompt refresh behavior are valuable. The safer path is to put durable orchestration around them, then add tool metadata where retry/resume semantics require it.
