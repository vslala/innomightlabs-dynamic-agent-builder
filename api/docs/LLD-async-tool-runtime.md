# Low Level Design: Async Tool Runtime

Date: 2026-06-28  
Status: Draft  
Owner: InnomightLabs API

## Summary

Extend the existing agent tool runtime so any skill action can be started asynchronously when the caller passes `async: true` to `execute_skill_action`.

The goal is to prevent long-running skills, such as HTML report generation, from blocking the agentic loop and the browser SSE request while still preserving the current "tool result goes back to the agent" behavior.

The implementation should not add a separate top-level platform module. It should live under the existing tool runtime and skill runtime boundaries:

- `api/src/agents/tool_runtime/`
- `api/src/agents/agentic_loop.py`
- `api/src/skills/service.py`

The runtime will persist async tool jobs in DynamoDB with a seven-day TTL, run the skill action in the background, and keep the agentic loop alive through an internal wait/check cycle until the final tool result can be passed back to the agent.

## Railway Constraint

Railway public networking supports long-lived HTTP traffic, but the documented public HTTP request max duration is still 15 minutes. SSE is an HTTP response stream, so it should not be treated as unlimited.

Railway docs source: `https://docs.railway.com/networking/public-networking/specs-and-limits`

Relevant documented limits:

- HTTP/1.1 supported.
- WebSockets over HTTP/1.1 supported.
- Proxy keep-alive timeout: 60 seconds.
- Max duration: 15 minutes for HTTP requests.

Design implication: the same SSE connection can show progress, but the platform should not depend on a single request staying open until a long job finishes. The agent loop should wait for a bounded period, surface progress, and allow later checks.

## Current Behavior

Today the loop is synchronous from the tool runtime's perspective:

1. `run_agentic_tool_loop(...)` receives provider tool calls.
2. `_execute_tool_with_runtime_events(...)` creates a task for `tool_router.execute(...)`.
3. The loop waits until that task completes.
4. The result is appended as a `toolResult`.
5. The next LLM iteration sees the final tool result.

Current file references:

- `api/src/agents/agentic_loop.py`
- `api/src/agents/tool_execution.py`
- `api/src/agents/tool_runtime/commands.py`
- `api/src/agents/tool_runtime/executors.py`
- `api/src/agents/tool_runtime/skills.py`
- `api/src/skills/service.py`
- `api/src/skills/registry.py`

This is clean for short tools, but long skill actions can hold the request open for too long.

## Design Goals

- Any skill action can run async if the agent or automation passes `async: true`.
- Keep this as an extension of the existing tool runtime, not a separate product module.
- Preserve current synchronous behavior when `async` is omitted or false.
- Persist job id, status, progress, and final skill return value in DynamoDB.
- Store exactly the skill/tool return payload as the job result, serialized as JSON/string like current tool results.
- Let the agent check job status inside the same agentic loop without ending the SSE response after a pending status.
- Keep in-turn waiting bounded so SSE does not rely on an unlimited request lifetime.
- Use DynamoDB TTL to delete job records after seven days.
- Keep jobs hidden from the UI for v1.
- Make the same primitive usable by automations later.

## Non-Goals

- No user-facing jobs page in v1.
- No separate marketplace/workflow feature.
- No new standalone "async jobs" domain module.
- No frontend polling requirement for the agent chat path.
- No requirement to make every background job survive every deploy in v1, though the persistence model should allow a worker later.

## Separate Worker Clarification

A separate worker means a separate long-running process or Railway service that claims queued jobs from DynamoDB and executes them outside the web API process.

Examples:

- `api-web`: FastAPI service handling user requests and SSE.
- `api-worker`: worker service polling/claiming async tool jobs and executing skill actions.

Benefits:

- Jobs can continue even if the original HTTP request disconnects.
- Web workers are not tied up by long-running report generation.
- Scaling web and job execution can be tuned independently.

V1 can start with an in-process background task because it is simpler. The repository/state contract should be designed so a dedicated worker can be added without changing agent/tool behavior.

## Public Tool Contract

Extend `execute_skill_action` parameters with an optional `async` flag:

```json
{
  "skill_id": "league_insights_report",
  "action": "generate_match_report",
  "arguments": {
    "game_name": "Demon Simon",
    "tag_line": "messi"
  },
  "async": true
}
```

Internal start payload:

```json
{
  "ok": true,
  "async": true,
  "job_id": "tooljob_01J...",
  "status": "queued",
  "message": "Started generate_match_report. The runtime will keep checking this job until it succeeds or fails.",
  "check_tool": "check_tool_job",
  "wait_tool": "wait"
}
```

This payload is not treated as the final user-facing tool result. It is loop control data. The loop should inject a synthetic message so the model can decide whether to tell the user the job is still running, wait, or check status.

Add an internal job-status runtime tool:

```json
{
  "name": "check_tool_job",
  "description": "Check the status and result of an asynchronous tool job.",
  "parameters": {
    "type": "object",
    "properties": {
      "job_id": {"type": "string"}
    },
    "required": ["job_id"],
    "additionalProperties": false
  }
}
```

Add a native wait tool:

```json
{
  "name": "wait",
  "description": "Wait for a bounded duration before continuing the current task.",
  "parameters": {
    "type": "object",
    "properties": {
      "seconds": {
        "type": "integer",
        "minimum": 1,
        "maximum": 600,
        "description": "Optional number of seconds to wait before returning control to the agent. Defaults to 20 and is capped at 600."
      },
      "reason": {
        "type": "string",
        "description": "Short reason for the wait, usually because an async tool job is still running."
      }
    },
    "required": [],
    "additionalProperties": false
  }
}
```

`wait` returns:

```json
{
  "ok": true,
  "waited_seconds": 10,
  "message": "Wait complete."
}
```

Result while running:

```json
{
  "ok": true,
  "async": true,
  "job_id": "tooljob_01J...",
  "status": "running",
  "progress_message": "Generating the report HTML...",
  "started_at": "2026-06-28T12:00:00Z"
}
```

Result when complete:

```json
{
  "ok": true,
  "async": true,
  "job_id": "tooljob_01J...",
  "status": "succeeded",
  "result": {
    "ok": true,
    "artifact_id": "artifact_...",
    "view_url": "https://..."
  }
}
```

Failure:

```json
{
  "ok": false,
  "async": true,
  "job_id": "tooljob_01J...",
  "status": "failed",
  "error": "Riot API rejected the configured API key. Check that the key is valid and not expired."
}
```

## Tool Job Model, Repository, and Service

Split the job implementation into dedicated files under the existing tool runtime:

- `api/src/agents/tool_runtime/jobs/models.py`
- `api/src/agents/tool_runtime/jobs/repository.py`
- `api/src/agents/tool_runtime/jobs/service.py`

This is still part of the existing tool runtime, not a separate platform module.

### Model

`models.py` owns serialization, status enums, key construction, TTL calculation, and response shaping.

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from enum import Enum
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field

TOOL_JOB_TTL_DAYS = 7


class ToolJobStatus(str, Enum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    EXPIRED = "expired"


class ToolJob(BaseModel):
    job_id: str
    owner_email: str
    actor_email: str
    actor_id: str
    agent_id: str | None = None
    conversation_id: str | None = None
    user_message_id: str | None = None
    automation_id: str | None = None
    automation_run_id: str | None = None
    automation_node_id: str | None = None
    tool_name: str
    skill_id: str | None = None
    installed_skill_id: str | None = None
    action: str | None = None
    arguments: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
    context: dict[str, Any] = Field(default_factory=dict)
    status: ToolJobStatus = ToolJobStatus.QUEUED
    progress_message: str | None = None
    result: Any | None = None
    error: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    ttl: int

    @staticmethod
    def new_job_id() -> str:
        return f"tooljob_{uuid4().hex}"

    @staticmethod
    def ttl_from_now() -> int:
        return int((datetime.now(timezone.utc) + timedelta(days=TOOL_JOB_TTL_DAYS)).timestamp())

    @property
    def pk(self) -> str:
        return f"USER#{self.owner_email}"

    @property
    def sk(self) -> str:
        return f"TOOL_JOB#{self.job_id}"

    @property
    def gsi1pk(self) -> str:
        return f"TOOL_JOB#{self.job_id}"

    @property
    def gsi1sk(self) -> str:
        return f"TOOL_JOB#{self.job_id}"

    def to_dynamo_item(self) -> dict[str, Any]:
        payload = self.model_dump(mode="json")
        payload.update(
            {
                "PK": self.pk,
                "SK": self.sk,
                "GSI1PK": self.gsi1pk,
                "GSI1SK": self.gsi1sk,
                "entity_type": "tool_job",
            }
        )
        return payload
```

Single-table keys:

```text
pk = User#{owner_email}
sk = ToolJob#{job_id}
gsi2_pk = ToolJob#{job_id}
gsi2_sk = ToolJob#{job_id}
```

The direct job-id lookup is important because `check_tool_job` should not scan. Authorization still checks `owner_email`, `actor_email`, or the conversation context after loading.

TTL:

```python
ttl = int((datetime.now(timezone.utc) + timedelta(days=7)).timestamp())
```

### Repository

`repository.py` is the only layer that knows DynamoDB expressions and conditional updates.

Required methods:

```python
class ToolJobRepository:
    def create(self, job: ToolJob) -> ToolJob:
        ...

    def find_by_id(self, job_id: str) -> ToolJob | None:
        ...

    def mark_running(self, job_id: str, progress_message: str | None = None) -> ToolJob:
        ...

    def update_progress(self, job_id: str, progress_message: str) -> ToolJob:
        ...

    def mark_succeeded(self, job_id: str, result: Any) -> ToolJob:
        ...

    def mark_failed(self, job_id: str, error: str) -> ToolJob:
        ...

    def claim_queued(self, job_id: str, worker_id: str) -> ToolJob | None:
        ...
```

Notes:

- `find_by_id` should query `GSI1PK = TOOL_JOB#{job_id}`.
- `claim_queued` should use a conditional update so a future worker can safely claim a queued job.
- `mark_succeeded` stores the exact skill/tool response payload.
- `mark_failed` stores a bounded human-readable error.

### Service

`service.py` owns authorization, runtime behavior, result shaping, and orchestration.

Required methods:

```python
class ToolJobService:
    def create_skill_action_job(
        self,
        *,
        owner_email: str,
        actor_email: str,
        actor_id: str,
        agent_id: str | None,
        conversation_id: str | None,
        user_message_id: str | None,
        skill_id: str,
        installed_skill_id: str,
        action: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> ToolJob:
        ...

    async def execute_skill_action_job(self, job_id: str) -> None:
        ...

    def check_job(self, *, job_id: str, state: AgentTurnState) -> dict[str, Any]:
        ...

    def authorize(self, job: ToolJob, state: AgentTurnState) -> None:
        ...
```

The service should reload skill runtime config during execution instead of persisting decrypted config in the job record.

## Tool Runtime Execution Flow

### Synchronous Path

If `execute_skill_action.async` is absent or false:

1. `SkillToolExecutor.execute(...)`
2. `SkillRuntimeService.handle_tool_call(...)`
3. `SkillRegistry.execute_action(...)`
4. Return result exactly as today.

### Async Start Path

If `execute_skill_action.async == true`:

1. `SkillToolExecutor` forwards request to `SkillRuntimeService`.
2. `SkillRuntimeService.handle_tool_call(...)` validates the installed skill and action like today.
3. Instead of awaiting `SkillRegistry.execute_action(...)`, it creates a `ToolJob`.
4. It persists the full runtime execution payload:
   - resolved `skill_id`
   - `installed_skill_id`
   - action name
   - arguments
   - non-secret execution context
   - context
5. It schedules execution.
6. It returns the immediate job payload to the loop as control data.
7. The loop keeps the turn open by appending a synthetic message and allowing the agent to call `wait` and `check_tool_job`.

Recommended method split:

```python
class SkillRuntimeService:
    async def handle_tool_call(...) -> str:
        ...

    async def _execute_skill_action_sync(...) -> Any:
        ...

    async def _start_skill_action_job(...) -> dict[str, Any]:
        ...
```

### Job Execution

V1 in-process background execution:

```python
class ToolJobExecutor:
    async def start_job(self, job: ToolJob) -> None:
        asyncio.create_task(self.execute_job(job.job_id))

    async def execute_job(self, job_id: str) -> None:
        job = repository.get(job_id)
        repository.mark_running(job_id, "Starting skill action...")
        try:
            result = await registry.execute_action(...)
            repository.mark_succeeded(job_id, result)
        except Exception as exc:
            repository.mark_failed(job_id, human_error(exc))
```

Future worker mode:

- Web API creates job only.
- Worker claims queued jobs using a conditional update from `queued` to `running`.
- Worker executes and writes result.
- No agent or skill contract changes.

## Agentic Loop Behavior

The agent should not receive a queued/running payload as the final tool result. If it does, it will naturally tell the user that the job is running and the agentic flow will end, which closes the SSE stream.

```mermaid
sequenceDiagram
    autonumber
    participant UI as Browser SSE
    participant Loop as Agentic Loop
    participant LLM as Agent Model
    participant Router as Tool Router
    participant Skills as Skill Runtime
    participant Jobs as Tool Job Service
    participant Store as DynamoDB
    participant Worker as Job Executor

    UI->>Loop: User message opens SSE stream
    Loop->>LLM: Stream context + tools
    LLM-->>Loop: tool_use execute_skill_action(async=true)
    Loop->>Router: Execute tool call
    Router->>Skills: handle_tool_call(...)
    Skills->>Jobs: create_skill_action_job(...)
    Jobs->>Store: Persist queued ToolJob with 7-day TTL
    Jobs-->>Worker: Start background execution
    Worker->>Store: Mark job running
    Worker->>Skills: Execute original skill action
    Skills-->>Loop: Async start control payload(job_id, status=queued)
    Loop->>Loop: Append synthetic wait/check instruction
    Loop->>LLM: Continue same agentic turn
    LLM-->>UI: Optional progress text
    LLM-->>Loop: tool_use wait(seconds)
    Loop->>Router: Execute wait
    Router-->>Loop: Wait complete
    Loop->>LLM: Continue same turn
    LLM-->>Loop: tool_use check_tool_job(job_id)
    Loop->>Router: Execute check_tool_job
    Router->>Jobs: check_job(...)
    Jobs->>Store: Read ToolJob
    alt Job still running
        Jobs-->>Loop: status=running
        Loop->>LLM: Continue same turn with running status
        LLM-->>UI: Optional progress update
        LLM-->>Loop: tool_use wait(seconds)
    else Job succeeded
        Worker->>Store: Mark job succeeded with exact skill result
        Jobs-->>Loop: status=succeeded + result
        Loop->>LLM: Final effective tool result
        LLM-->>UI: Final answer with skill result
        Loop-->>UI: SSE stream completes
    else Job failed
        Worker->>Store: Mark job failed with human-readable error
        Jobs-->>Loop: status=failed + error
        Loop->>LLM: Final failed tool result
        LLM-->>UI: Explain failure
        Loop-->>UI: SSE stream completes
    end
```

Instead, async execution is a loop-control behavior:

1. The skill action starts a job.
2. The loop appends an internal synthetic message.
3. The model can send a user-visible progress note.
4. The model calls `wait`.
5. After the wait tool returns, the model calls `check_tool_job`.
6. If the job is still running, repeat from step 3.
7. Once the job succeeds or fails, the final job result is passed back as the effective tool result.

For the model, the long-running tool still feels like a normal tool call whose final response eventually arrives.

Recommended constants:

```python
ASYNC_TOOL_IN_TURN_WAIT_SECONDS = 20
ASYNC_TOOL_POLL_INTERVAL_SECONDS = 2
```

When the tool runtime returns control data:

```json
{"async": true, "job_id": "...", "status": "queued"}
```

The loop should not finish the turn. It should append a synthetic user message to context:

```text
The async tool job tooljob_... has started for execute_skill_action.
Do not finish the conversation yet.
You may briefly tell the user that the job is running.
Then call wait with a short delay.
After the wait returns, call check_tool_job with job_id tooljob_....
If the job is still running, repeat the wait/check cycle.
When the job succeeds, use the returned result as the skill result.
```

This preserves agent control while preventing the pending payload from ending the stream.

### Native Wait Tool

`wait` is a native tool, not a skill action. It lets the model intentionally keep the agentic loop alive without frontend polling or hidden frontend re-invocation.

Implementation:

```python
class WaitTool:
    async def execute(self, tool_name: str, tool_input: dict[str, Any], state: AgentTurnState) -> str:
        seconds = clamp(int(tool_input.get("seconds") or DEFAULT_WAIT_SECONDS), 1, MAX_WAIT_SECONDS)
        await asyncio.sleep(seconds)
        return json.dumps({"ok": True, "waited_seconds": seconds, "message": "Wait complete."})
```

Register it as a native tool in `api/src/tools/native/specs.py` or the existing native tool registry path.

### Loop Guardrails

The wait tool must be bounded so the agent cannot keep the SSE request open forever.

Recommended constants:

```python
DEFAULT_WAIT_SECONDS = 20
MAX_WAIT_SECONDS = 600
MAX_ASYNC_JOB_IN_TURN_SECONDS = 600
```

With these values, the agent waits 20 seconds by default, can request a longer wait up to 10 minutes, and the full turn still cannot exceed ten minutes of deliberate async waiting. This stays below Railway's documented 15-minute request duration.

This async self-check loop must not depend on `MAX_TOOL_ITERATIONS`. `MAX_TOOL_ITERATIONS` should continue to protect normal reasoning/tool loops, but once an async job is active the loop may continue wait/check cycles until `MAX_ASYNC_JOB_IN_TURN_SECONDS` is reached. When `check_tool_job` returns a terminal `succeeded` or `failed` state, the loop should allow one final model invocation even if the normal iteration limit has already been exceeded, so the agent can consume the job result and respond properly.

When the limit is reached and the job is still running, the loop should stop waiting and fail the turn with a controlled runtime error instead of emitting a normal completion event. The normal completion event should only happen after the agent has received a terminal job payload and had one final chance to respond with that result.

### Effective Tool Result

When `check_tool_job` returns `succeeded`, the loop should treat this payload as the final effective result of the original async skill action:

```json
{
  "ok": true,
  "async": true,
  "job_id": "tooljob_01J...",
  "status": "succeeded",
  "result": {
    "ok": true,
    "artifact_id": "artifact_...",
    "view_url": "https://..."
  }
}
```

The agent can then continue naturally and tell the user the final answer.

## Prompt Guidance

Update `SkillRuntimeService.build_system_prompt_addendum(...)` with:

```text
For long-running skill actions, call execute_skill_action with async: true.
When an async tool job starts, do not finish the response after the queued/running state.
Use wait to wait briefly, then use check_tool_job to check status.
If the job is still queued or running, you may briefly tell the user it is still running, then wait and check again.
If the job succeeded, use the returned result exactly like a normal skill result.
```

Do not expose `check_tool_job` or `wait` to users as product features. They are runtime tools for the agent.

## Automation Behavior

Automations should support the same flag in `SkillActionConfig`:

```python
class SkillActionConfig(BaseModel):
    action_type: AutomationActionType = AutomationActionType.SKILL_ACTION
    skill_id: str | None = None
    installed_skill_id: str | None = None
    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    async_: bool = Field(default=False, alias="async")
```

For v1, automation behavior can be:

- `async=false`: current behavior.
- `async=true`: start job, then use the tool-job service to wait/check without duplicating skill execution logic.
- If job finishes within the automation node timeout, node output is final result.
- If still running after the node timeout, node output is a durable job payload and downstream branches can check `status`.

Later, automation runner can persist a suspended node and resume on completion. That is more complex and not required for the first agent-focused implementation.

## Runtime Events

Extend `AgentTurnRuntime` event usage with:

```json
{
  "type": "tool_job_started",
  "job_id": "tooljob_...",
  "tool_name": "execute_skill_action",
  "skill_id": "league_insights_report",
  "action": "generate_match_report"
}
```

```json
{
  "type": "tool_job_progress",
  "job_id": "tooljob_...",
  "status": "running",
  "progress_message": "Generating report HTML..."
}
```

```json
{
  "type": "tool_job_completed",
  "job_id": "tooljob_...",
  "status": "succeeded"
}
```

The UI can show progress in the chat stream without starting its own polling loop.

When `wait` is called, the SSE stream remains open because the agentic loop is still executing a tool. The UI may receive heartbeat/progress runtime events during this period, but it does not need to poll or secretly call the agent again.

## Error Handling

Expected skill failures should be stored in the job as:

```json
{
  "status": "failed",
  "error": "human readable message"
}
```

`check_tool_job` should return `ok: false` for failed jobs, not raise, so the agent can explain the failure.

Configuration errors during job creation should still raise immediately:

- skill not installed
- action missing
- invalid argument shape
- user not authorized

## Security

- The job record is owned by `owner_email`.
- `check_tool_job` must verify the current agent/user context can access the job.
- Skill config may include decrypted secrets. Storing full decrypted config in DynamoDB is risky.

Recommended secret-safe approach:

- Store `installed_skill_id`, not decrypted secret values.
- At execution time, load current runtime config from `AgentSkillRepository`.
- For automation-installed skills, load config from the automation skill repository.
- Store non-secret action arguments as provided.

If execution must snapshot config, encrypt secret fields before storing. Prefer reloading runtime config to avoid persisting decrypted secrets.

## File Plan

Add:

- `api/src/agents/tool_runtime/jobs/__init__.py`
- `api/src/agents/tool_runtime/jobs/models.py`
- `api/src/agents/tool_runtime/jobs/repository.py`
- `api/src/agents/tool_runtime/jobs/service.py`
- `api/tests/test_async_tool_runtime.py`

Update:

- `api/src/agents/tool_runtime/skills.py`
  - Add optional `async` property to `execute_skill_action`.
  - Add `check_tool_job` spec.
- `api/src/tools/native/specs.py`
  - Add `wait` native tool spec.
- Native tool executor implementation
  - Add bounded sleep behavior for `wait`.
- `api/src/agents/tool_runtime/factory.py`
  - Register the new job-status runtime command with the existing skill executor.
- `api/src/agents/tool_runtime/executors.py`
  - Route `check_tool_job` to `ToolJobService`.
- `api/src/agents/tool_runtime/commands.py`
  - Add metadata if needed, but avoid changing the provider-facing command contract unless necessary.
- `api/src/skills/service.py`
  - Start async skill jobs when `async: true`.
  - Return async start control payloads to the loop.
- `api/src/agents/agentic_loop.py`
  - Recognize async start control payloads.
  - Append the synthetic wait/check instruction.
  - Enforce the max in-turn async wait time independently from the normal agent iteration cap.
- `api/src/automations/models.py`
  - Add `async` flag to `SkillActionConfig`.
- `api/src/automations/runner.py`
  - Pass `async` into skill action execution and optionally use bounded wait.

## Tests

Add tests for:

- `execute_skill_action` without `async` preserves current behavior.
- `execute_skill_action` with `async: true` creates a persisted job and returns `job_id`.
- Async start payload is not treated as the final assistant-visible result.
- Agentic loop appends synthetic wait/check context after async start.
- `wait` sleeps for a bounded duration and returns a tool result.
- `wait` clamps excessive values to `MAX_WAIT_SECONDS`.
- `check_tool_job` returns queued/running state.
- Successful job stores exact skill return payload.
- Failed job stores human-readable error and returns `ok:false`.
- Job records include seven-day TTL.
- Unauthorized job lookup is rejected.
- Decrypted secret config is not stored in the job record.
- Agentic loop emits job progress runtime events.
- Agentic loop allows async wait/check beyond the normal iteration cap.
- Agentic loop enforces max in-turn async wait time.
- Automation skill action can pass `async: true`.

Run:

```bash
cd api
uv run pytest -v
```

## Implementation Steps

1. Add `ToolJob`, status enum, and serialization helpers in `api/src/agents/tool_runtime/jobs/models.py`.
2. Add DynamoDB persistence in `api/src/agents/tool_runtime/jobs/repository.py`.
3. Add authorization, async execution, and response shaping in `api/src/agents/tool_runtime/jobs/service.py`.
4. Extend `execute_skill_action` tool schema with optional `async`.
5. Add `check_tool_job` tool schema.
6. Add the native `wait` tool.
7. Extend `SkillRuntimeService` with sync execution and async start methods.
8. Add in-process job execution that runs skill actions and writes status/result.
9. Add async start handling in `agentic_loop.py` that injects synthetic wait/check context.
10. Add loop guardrails for max in-turn async wait time, independent of normal max agent iterations.
11. Add runtime events for job started/progress/completed.
12. Add automation model support for `async`.
13. Add tests.
14. Run the API test suite.

## Open Decisions

1. Initial execution backend:
   - V1 in-process background task.
   - Later optional worker that claims queued jobs.

2. Agent loop behavior:
   - Model-driven wait/check using `wait` and `check_tool_job`.
   - Hardcoded runtime polling.

Recommendation: implement model-driven wait/check with runtime guardrails. It keeps the design agentic, avoids frontend polling, and prevents pending async payloads from ending the SSE stream.
