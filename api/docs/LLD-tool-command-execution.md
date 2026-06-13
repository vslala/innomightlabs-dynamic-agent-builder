# Tool Command Execution

## Problem

The current tool execution layer is intentionally small, but it is starting to collect responsibilities in one router:

- `api/src/agents/tool_execution.py` decides whether a tool is a skill, MCP tool, or native tool.
- It contains MCP argument validation and result formatting.
- It marks `state.prompt_dirty` for memory write tools.
- It owns the recoverable tool error policy.
- `api/src/agents/agentic_loop.py` assumes each model tool call maps to one sequential router call.

This works today, but adding more tool categories, retries, parallel execution, idempotency, timeouts, and auditing will make the router harder to maintain.

The goal is to improve tool execution architecture first, without redesigning the whole agent run lifecycle.

## Recommendation

Use a focused Command Pattern, but keep the current public surface stable:

```python
await tool_router.execute(
    tool_name=tool_event.tool_name,
    tool_input=tool_event.tool_input,
    tool_use_id=tool_event.tool_use_id,
    state=state,
)
```

Internally, `ToolExecutionRouter` should become a thin adapter over a `ToolCommandRegistry`.

This gives us:

- isolated execution logic per command
- metadata per tool, not scattered conditionals
- a single place for common error handling, timing, and future retry policy
- a natural home for `parallel_tools` as another registered native command
- no immediate provider or agentic-loop rewrite

## Current Code

Current dispatch lives here:

- `api/src/agents/tool_execution.py`
  - `ToolExecutionRouter.execute(...)`
  - `_execute_mcp_tool(...)`
  - `ToolExecutionOutcome`

Current call site:

- `api/src/agents/agentic_loop.py`
  - `_execute_tool_with_runtime_events(...)`
  - currently executes pending tool calls sequentially

Current tool sources:

- `api/src/tools/native/definitions.py`
  - native and knowledge tool schemas
- `api/src/tools/native/handlers.py`
  - memory, recall, and KB behavior
- `api/src/skills/service.py`
  - `load_skill` and `execute_skill_action`
- `api/src/connectors/mcp/runtime_tools.py`
  - MCP runtime tool schemas and names

## Design

### Command Interface

Add a small command interface under `api/src/agents/tool_runtime/`.

```python
class ToolCommand(Protocol):
    @property
    def name(self) -> str:
        ...

    @property
    def definition(self) -> dict[str, Any]:
        ...

    @property
    def metadata(self) -> ToolCommandMetadata:
        ...

    async def execute(self, request: ToolCommandRequest) -> ToolExecutionOutcome:
        ...
```

The important design choice is that every tool family should expose a consistent execution shape, similar to `NativeToolHandler.execute(...)`. Skill and MCP execution should be adapted to the same shape instead of leaking family-specific method signatures into the command layer.

Request and metadata:

```python
class ToolCommandRequest(BaseModel):
    tool_name: str
    tool_input: dict[str, Any]
    tool_use_id: str
    state: AgentTurnState


class ToolCommandCategory(str, Enum):
    NATIVE = "native"
    KNOWLEDGE = "knowledge"
    SKILL = "skill"
    MCP = "mcp"


class ToolIdempotency(str, Enum):
    READ_ONLY = "read_only"
    IDEMPOTENT_WRITE = "idempotent_write"
    NON_IDEMPOTENT_WRITE = "non_idempotent_write"


class ToolCommandMetadata(BaseModel):
    category: ToolCommandCategory
    idempotency: ToolIdempotency
    mutates_prompt_context: bool = False
    timeout_seconds: int | None = None
    allow_parallel: bool = False


class ToolSpec(BaseModel):
    definition: dict[str, Any]
    metadata: ToolCommandMetadata
```

The command returns the existing `ToolExecutionOutcome` so the first refactor preserves behavior.

`ToolSpec` is the unit of organization: provider-facing schema and execution metadata should live together. Family modules own their specs:

- `api/src/tools/native/specs.py`
- `api/src/agents/tool_runtime/skills.py`
- `api/src/agents/tool_runtime/mcp.py`

### Tool Executors

Use one executor protocol for native, skill, and MCP tools:

```python
class ToolExecutor(Protocol):
    async def execute(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        state: AgentTurnState,
    ) -> str:
        ...
```

`NativeToolHandler` already has almost this shape:

```python
await native_tools.execute(tool_name, tool_input, state.agent_id)
```

The refactor should add small adapters for skill and MCP tools so command implementations remain uniform:

```python
class SkillToolExecutor:
    async def execute(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        state: AgentTurnState,
    ) -> str:
        return await self._skill_runtime.handle_tool_call(
            tool_name=tool_name,
            tool_input=tool_input,
            agent_id=state.agent_id,
            owner_email=state.owner_email,
            actor_email=state.actor_email,
            actor_id=state.actor_id,
            conversation_id=state.conversation_id,
            user_message_id=state.user_message_id,
        )
```

```python
class MCPToolExecutor:
    async def execute(
        self,
        tool_name: str,
        tool_input: dict[str, Any],
        state: AgentTurnState,
    ) -> str:
        ...
```

This keeps command code consistent: a command validates policy/metadata and calls a uniform executor. It also keeps family-specific plumbing near the family adapter rather than in the router.

### Registry

Add a registry that maps tool names to commands.

```python
class ToolCommandRegistry:
    def register(self, command: ToolCommand) -> None:
        ...

    def get(self, tool_name: str) -> ToolCommand:
        ...

    def definitions(self) -> list[dict[str, Any]]:
        ...
```

The architecture can eventually build `state.tools` from the registry instead of manually concatenating lists. Phase one can leave existing `state.tools` construction in `krishna_memgpt.py` unchanged.

### Router

`ToolExecutionRouter` becomes an error-handling adapter:

```python
class ToolExecutionRouter:
    async def execute(
        self,
        *,
        tool_name: str,
        tool_input: dict[str, Any],
        tool_use_id: str,
        state: AgentTurnState,
    ) -> ToolExecutionOutcome:
        command = self._registry.get(tool_name)
        request = ToolCommandRequest(
            tool_name=tool_name,
            tool_input=tool_input,
            tool_use_id=tool_use_id,
            state=state,
        )
        outcome = await command.execute(request)
        if command.metadata.mutates_prompt_context:
            state.prompt_dirty = True
        return outcome
```

The router should keep the existing catch-all recoverable tool error behavior:

```python
except Exception as exc:
    log.error(...)
    return ToolExecutionOutcome(result=f"Error: {str(exc)}", success=False)
```

This is important because the model can often recover from tool failures in the next iteration.

## Commands

### ExecutorToolCommand

Most tools can use the same concrete command class because execution is delegated to a uniform executor.

```python
class ExecutorToolCommand:
    def __init__(
        self,
        *,
        spec: ToolSpec,
        executor: ToolExecutor,
    ):
        ...

    async def execute(self, request: ToolCommandRequest) -> ToolExecutionOutcome:
        result = await self._executor.execute(
            request.tool_name,
            request.tool_input,
            request.state,
        )
        return ToolExecutionOutcome(result=result, success=True)
```

Native tools use this command with a `NativeToolExecutorAdapter`. Skill tools use it with a `SkillToolExecutor`. MCP tools use it with an `MCPToolExecutor`. Tools that coordinate other commands, such as `parallel_tools`, can implement `ToolCommand` directly while still being registered and exposed like any other native tool.

Memory write tools set `mutates_prompt_context=True` through metadata instead of hardcoding names in the router.

Initial metadata:

```python
{
    "core_memory_read": READ_ONLY,
    "core_memory_list_blocks": READ_ONLY,
    "archival_memory_search": READ_ONLY,
    "recall_conversation": READ_ONLY,
    "knowledge_base_search": READ_ONLY,
    "core_memory_append": IDEMPOTENT_WRITE + mutates_prompt_context,
    "core_memory_replace": IDEMPOTENT_WRITE + mutates_prompt_context,
    "core_memory_delete": IDEMPOTENT_WRITE + mutates_prompt_context,
    "archival_memory_insert": IDEMPOTENT_WRITE,
}
```

### Skill Tools

Do not create a special command shape for skills. Add `SkillToolExecutor` as an adapter around `SkillRuntimeService.handle_tool_call(...)`, then register `load_skill` and `execute_skill_action` as normal `ExecutorToolCommand` instances.

Two registered command instances are enough:

- `load_skill`
- `execute_skill_action`

`load_skill` is read-only. `execute_skill_action` should default to `NON_IDEMPOTENT_WRITE` until skill action manifests explicitly declare idempotency.

### MCP Tools

Do not create a special command shape for MCP either. Add `MCPToolExecutor` as an adapter around `MCPConnectorService`, then register two normal `ExecutorToolCommand` instances:

- `list_mcp_tools`
- `call_mcp_tool`

`list_mcp_tools` is read-only. `call_mcp_tool` should default to `NON_IDEMPOTENT_WRITE`.

This removes MCP-specific branching from the router while keeping the MCP-specific validation in MCP commands.

## Parallel Tool Command

`parallel_tools` should be treated as just another registered native tool. It is not a special path in the agent loop and it should not require separate router behavior.

```python
PARALLEL_TOOLS = {
    "name": "parallel_tools",
    "description": (
        "Execute multiple independent read-only or parallel-safe tools concurrently "
        "and return an aggregated result. Use only when calls do not depend on each other."
    ),
    "parameters": {
        "type": "object",
        "properties": {
            "calls": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "tool_name": {"type": "string"},
                        "arguments": {"type": "object"},
                    },
                    "required": ["tool_name", "arguments"],
                },
            }
        },
        "required": ["calls"],
    },
}
```

Execution behavior:

```python
class ParallelToolsCommand:
    async def execute(self, request: ToolCommandRequest) -> ToolExecutionOutcome:
        calls = parse_calls(request.tool_input)
        commands = [self._registry.get(call.tool_name) for call in calls]
        self._validate_parallel_safe(commands)
        results = await asyncio.gather(
            *[
                command.execute(
                    request_for_child_call(request, call)
                )
                for command, call in zip(commands, calls)
            ],
            return_exceptions=True,
        )
        return ToolExecutionOutcome(
            result=json.dumps(aggregate(results), ensure_ascii=True),
            success=all_result_successes(results),
        )
```

This command can be implemented directly because it coordinates other commands, but it still satisfies the same `ToolCommand` interface and is registered in the same `ToolCommandRegistry`.

Safety rules:

- Only allow commands where `metadata.allow_parallel=True`.
- Default `allow_parallel=True` for read-only native, knowledge, `load_skill`, and `list_mcp_tools`.
- Default `allow_parallel=False` for memory writes, `execute_skill_action`, `call_mcp_tool`, and image generation.
- Reject nested `parallel_tools` calls.
- Preserve input order in the aggregated response.
- Return per-call success/error objects so the model can recover from partial failures.

Aggregated result shape:

```json
{
  "results": [
    {
      "tool_name": "knowledge_base_search",
      "success": true,
      "result": "..."
    },
    {
      "tool_name": "archival_memory_search",
      "success": false,
      "result": "Error: ..."
    }
  ]
}
```

Why this is better than making the loop execute all provider-emitted tool calls in parallel immediately:

- The model explicitly asks for parallelism when calls are independent.
- The command can reject unsafe tools.
- The existing loop and prompt refresh semantics remain stable.
- We avoid accidental parallel memory writes or third-party side effects.

Later, after metadata is mature, `agentic_loop.py` can parallelize multiple provider-emitted tool calls automatically when all are marked parallel-safe. That should be a later phase, not the first change.

## File Layout

Suggested first-pass files:

```text
api/src/agents/tool_runtime/
+-- __init__.py
+-- commands.py          # Protocols, ToolSpec, request/metadata models
+-- registry.py          # ToolCommandRegistry
+-- router.py            # ToolExecutionRouter adapter, or keep existing file importing it
+-- executors.py         # Uniform executor protocol and adapters
+-- skills.py            # Skill ToolSpec ownership
+-- mcp.py               # MCP ToolSpec ownership
+-- parallel.py          # ParallelToolsCommand

api/src/tools/native/
+-- definitions.py       # Native/knowledge provider-facing schemas
+-- handlers.py          # Native/knowledge execution behavior
+-- specs.py             # Native/knowledge ToolSpec ownership
```

To minimize churn, `api/src/agents/tool_execution.py` can remain as the public import path and re-export or instantiate the new router.

## Migration Plan

### Phase 1: Command Interface With No Behavior Change

Add command models and registry.

Change `ToolExecutionRouter.execute(...)` to:

1. find a command by `tool_name`
2. execute it
3. apply `mutates_prompt_context`
4. preserve current error handling

Do not change `agentic_loop.py` yet.

Tests:

- `load_skill` routes through a skill command.
- `execute_skill_action` routes through a skill command.
- `list_mcp_tools` and `call_mcp_tool` route through MCP commands.
- unknown tool returns current-style error outcome.
- core memory write sets `state.prompt_dirty=True`.
- native read does not set `state.prompt_dirty`.

### Phase 2: Metadata-Driven Tool Definitions

Create command factories for native, skill, MCP, and knowledge commands. Skill and MCP factories should register normal `ExecutorToolCommand` instances backed by their executor adapters.

Update `krishna_memgpt.py` to build tool definitions from the registry where practical:

```python
state.tools = registry.definitions_for_state(state)
```

Keep the existing exposed tools identical.

Tests:

- tool names exposed to the provider are unchanged for the same agent state.
- KB tools are exposed only when KBs are linked.
- skill tools are exposed only when skills are enabled.
- MCP tools are exposed only when MCP connections are enabled.

### Phase 3: Add `parallel_tools`

Add the native `parallel_tools` command and expose it when at least two parallel-safe commands are available.

Tests:

- executes two read-only commands concurrently and aggregates in input order.
- rejects memory write tools.
- rejects `execute_skill_action`.
- rejects `call_mcp_tool` by default.
- converts per-child exceptions into per-child error results.
- does not set `state.prompt_dirty` unless a future allowed command explicitly mutates prompt context.

### Phase 4: Optional Loop-Level Parallelism

After command metadata is trusted, consider changing `agentic_loop.py` to automatically execute provider-emitted pending tool calls concurrently when every pending command is `allow_parallel=True`.

This phase is optional. The explicit `parallel_tools` command already gives the agent a safe way to request concurrent work.

## Prompt Guidance

If `parallel_tools` is exposed, add a concise prompt section:

```text
Use parallel_tools when you need multiple independent read-only lookups at the same time.
Do not use it for memory writes, destructive actions, external side effects, or calls where one result is needed to form the next call.
```

This should live with the MemGPT prompt/tool section, not inside the command implementation.

## Why Not A Bigger Tool Framework

A full plugin-style executor framework is not needed yet. The useful abstraction is small:

- command interface
- metadata
- registry
- native `parallel_tools` command
- unchanged router contract

This is enough to isolate tool behavior from the agent loop and gives room for durable execution later without forcing that larger migration now.

## Deferred Decisions

1. Expose `parallel_tools` only after the base command pattern is implemented and stable.
2. Keep skill actions conservative for now. Action-level `allow_parallel=True` can come later as a safety feature.
3. Keep command metadata with the tool definitions for now. Move policy into a central registry only if auditability or duplication becomes a real issue.
