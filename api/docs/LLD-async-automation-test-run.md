# Async Automation Test Run

## Problem

`POST /automations/{automation_id}/test-run` executes the automation synchronously inside the HTTP request:

```python
# api/src/automations/router.py
run = await runner.run_test(graph, body.trigger_id, body.input, user_email)
return run.to_response()
```

Long-running automations can exceed API Gateway's synchronous integration timeout. Lambda may continue and eventually save a successful run, but the browser receives `503 Service Unavailable`.

Observed production behavior for automation `6906ae79-049b-4aaf-819e-cfc9d3f69c6e`:

- API Gateway returned `503` to the client around the gateway timeout.
- Lambda continued running.
- Lambda later logged `POST /automations/.../test-run 200` after roughly 57-60 seconds.

Increasing Lambda timeout does not solve this because the API Lambda already uses `timeout = 900` in `terraform/lambda.tf`, which is Lambda's 15-minute maximum. The HTTP request is bounded by API Gateway, not Lambda.

## Existing Run Persistence

The code already stores automation runs and node results in DynamoDB.

Relevant files:

- `api/src/automations/models.py`
  - `AutomationRun`
  - `AutomationRunNodeResult`
  - `AutomationRunStatus`
  - `AutomationRunDetailResponse`
- `api/src/automations/repository.py`
  - `save_run(run)`
  - `find_runs_by_automation(automation_id, limit, cursor)`
  - `find_run_by_id(run_id, user_email)`
  - `save_node_result(result)`
  - `find_node_results(run_id)`
- `api/src/automations/router.py`
  - `GET /automations/{automation_id}/runs`
  - `GET /automations/{automation_id}/runs/{run_id}`
- `api/src/automations/runner.py`
  - `AutomationRunner.run_test(...)` creates an `AutomationRun`, saves it, executes nodes, saves node results, and updates final status.

Current storage shape:

```python
class AutomationRun(BaseModel):
    run_id: str = Field(default_factory=lambda: str(uuid4()))
    automation_id: str
    trigger_id: Optional[str] = None
    conversation_id: Optional[str] = None
    status: AutomationRunStatus = AutomationRunStatus.PENDING
    context: dict[str, Any] = Field(default_factory=dict)
    error: Optional[str] = None
    created_by: str
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
```

The existing polling endpoint already returns the status, context, and node results:

```http
GET /automations/{automation_id}/runs/{run_id}
```

Response model:

```python
class AutomationRunDetailResponse(BaseModel):
    run: AutomationRunResponse
    context: dict[str, Any] = Field(default_factory=dict)
    node_results: list[AutomationRunNodeResultResponse] = Field(default_factory=list)
```

## Proposed API Behavior

Change `POST /automations/{automation_id}/test-run` from synchronous execution to asynchronous launch.

New behavior:

1. Validate automation ownership and graph synchronously.
2. Create and persist an `AutomationRun` with `status="pending"` or `status="running"`.
3. Return immediately with `202 Accepted` and the run response, including `run_id`.
4. Invoke the Lambda asynchronously to execute that run.
5. SPA polls `GET /automations/{automation_id}/runs/{run_id}` until status is terminal.

Terminal statuses:

- `succeeded`
- `failed`
- `cancelled`

Suggested HTTP response:

```http
HTTP/1.1 202 Accepted
Content-Type: application/json

{
  "run_id": "...",
  "automation_id": "...",
  "status": "pending",
  ...
}
```

The response can remain `AutomationRunResponse`, so the frontend type does not need a new response shape.

## Backend Design

### 1. Split Run Creation From Execution

`AutomationRunner.run_test(...)` currently creates the run and executes it. For async launch, introduce two methods:

```python
class AutomationRunner:
    def create_test_run(
        self,
        graph: AutomationGraph,
        trigger_id: str | None,
        input_data: dict[str, Any],
        user_email: str,
    ) -> AutomationRun:
        ...

    async def execute_run(
        self,
        run_id: str,
        user_email: str,
    ) -> AutomationRun:
        ...
```

`create_test_run(...)` should:

- select the trigger
- create `AutomationRun`
- create `AutomationConversation`
- set `conversation_id`
- save the run
- not execute any nodes

`execute_run(...)` should:

- load the run by `run_id` and owner email
- load and validate the automation graph
- set `status=running` and `started_at` if not already set
- execute the same node loop currently inside `run_test(...)`
- save node results and context exactly as today
- set final status and `completed_at`

To keep risk low, the current loop can be moved to a private helper:

```python
async def _execute_run_graph(
    self,
    graph: AutomationGraph,
    run: AutomationRun,
    user_email: str,
) -> AutomationRun:
    ...
```

Then `run_test(...)` can remain as a compatibility wrapper for tests/local callers:

```python
async def run_test(...):
    run = self.create_test_run(...)
    return await self._execute_run_graph(graph, run, user_email)
```

### 2. Add Async Lambda Event

The project already has an async self-invoke pattern for crawl jobs in `main.py`:

```python
if "crawl_job" in event:
    return _handle_crawl_job(event["crawl_job"], context)
```

Extend it with an automation run event:

```python
if "automation_run" in event:
    return _handle_automation_run(event["automation_run"], context)
```

Payload:

```json
{
  "automation_run": {
    "run_id": "...",
    "automation_id": "...",
    "user_email": "..."
  }
}
```

Handler sketch:

```python
def _handle_automation_run(payload: dict, context):
    import asyncio

    run_id = payload.get("run_id")
    user_email = payload.get("user_email")
    if not all([run_id, user_email]):
        return {"statusCode": 400, "body": "Invalid automation_run payload"}

    from src.automations.runner import AutomationRunner

    run = asyncio.run(AutomationRunner().execute_run(run_id, user_email))
    return {
        "statusCode": 200,
        "body": f"Automation run {run.run_id} completed with status {run.status.value}",
    }
```

The existing Terraform self-invoke permission already allows this Lambda to invoke itself:

```hcl
resource "aws_iam_role_policy" "lambda_self_invoke" {
  action = ["lambda:InvokeFunction"]
  Resource = aws_lambda_function.api.arn
}
```

### 3. Launch Async Run From Router

Add a helper near the automation router, following the knowledge crawl pattern:

```python
def invoke_automation_run_async(run_id: str, automation_id: str, user_email: str) -> None:
    if not is_lambda():
        # local fallback can use asyncio.create_task or BackgroundTasks
        return

    client = boto3.client("lambda", region_name=aws_region())
    client.invoke(
        FunctionName=os.environ["AWS_LAMBDA_FUNCTION_NAME"],
        InvocationType="Event",
        Payload=json.dumps({
            "automation_run": {
                "run_id": run_id,
                "automation_id": automation_id,
                "user_email": user_email,
            }
        }).encode("utf-8"),
    )
```

Update the route:

```python
@router.post("/{automation_id}/test-run", response_model=AutomationRunResponse, status_code=202)
async def test_run(...):
    user_email = get_user_email(request)
    graph = service.get_graph(automation_id, user_email)
    service.validate_graph(graph.nodes, graph.edges, graph.triggers, user_email)
    run = runner.create_test_run(graph, body.trigger_id, body.input, user_email)
    invoke_automation_run_async(run.run_id, automation_id, user_email)
    return run.to_response()
```

Local development fallback options:

- Prefer `asyncio.create_task(runner.execute_run(run.run_id, user_email))` when an event loop exists.
- Or keep synchronous execution locally if that simplifies debugging.
- Do not rely on FastAPI `BackgroundTasks` for Lambda, because the project already documents that Lambda may freeze after returning an HTTP response.

### 4. Idempotency Guard

Async Lambda invocations can be retried by AWS. `execute_run(...)` should avoid re-running a completed run.

Minimum guard:

```python
if run.status in {
    AutomationRunStatus.SUCCEEDED,
    AutomationRunStatus.FAILED,
    AutomationRunStatus.CANCELLED,
}:
    return run
```

For duplicate concurrent async deliveries, a stronger DynamoDB conditional transition would be better:

- transition `pending -> running` using a conditional update
- if the condition fails, reload and return

This can be added as a follow-up if duplicate execution becomes a real issue. The first implementation can be acceptable for manual test runs, but should at least skip terminal runs.

## Frontend Design

Current SPA flow in `spa/src/pages/dashboard/automations/AutomationBuilderPage.tsx`:

```ts
const run = await automationApiService.testRun(automationId, { input: parsed });
const detail = await automationApiService.getRun(automationId, run.run_id);
setLatestRun(detail);
```

Change to:

1. Call `testRun`.
2. Store returned `run_id`.
3. Poll `getRun` every 1-2 seconds.
4. Update `latestRun` on each poll so the step log appears progressively.
5. Stop polling when `run.status` is terminal.
6. Stop polling on unmount or when the user starts a new run.

Sketch:

```ts
const terminal = new Set(["succeeded", "failed", "cancelled"]);

const pollRun = async (automationId: string, runId: string) => {
  while (true) {
    const detail = await automationApiService.getRun(automationId, runId);
    setLatestRun(detail);
    if (terminal.has(detail.run.status)) break;
    await new Promise((resolve) => window.setTimeout(resolve, 1500));
  }
};
```

For React correctness, implement this with `setInterval`, `useRef`, or a cancellable loop so state is not updated after unmount.

UI copy update:

- Replace "Running automation and waiting for step results..." with copy that fits polling, e.g. "Running automation..." while node results update.

No API service type change is required if `testRun` still returns `AutomationRunResponse`.

## Tests

Backend tests:

1. Router test: `POST /automations/{id}/test-run` returns `202` and a run with `pending` or `running` status without waiting for execution.
2. Router test: async invocation helper is called with `run_id`, `automation_id`, and `user_email`.
3. Runner test: `create_test_run(...)` persists the run and conversation.
4. Runner test: `execute_run(run_id, user_email)` updates run status and node results.
5. Lambda handler test: event with `automation_run` calls `AutomationRunner.execute_run(...)`.
6. Idempotency test: `execute_run(...)` returns immediately for terminal runs.

Frontend tests/manual checks:

1. Starting a test run immediately shows a running state.
2. The panel updates as `node_results` appear.
3. Polling stops on `succeeded`, `failed`, or `cancelled`.
4. Navigating away or closing the panel stops polling.

## Rollout

1. Deploy backend async run support.
2. Deploy SPA polling change.
3. Verify with:

```bash
curl -i 'https://api.innomightlabs.com/automations/{automation_id}/test-run' \
  -H 'authorization: Bearer ...' \
  -H 'content-type: application/json' \
  --data-raw '{"input":{"input":"Clean 50 marketing emails I received this week."}}'
```

Expected immediate response:

```json
{"run_id":"...","status":"pending",...}
```

Then poll:

```bash
curl 'https://api.innomightlabs.com/automations/{automation_id}/runs/{run_id}' \
  -H 'authorization: Bearer ...'
```

Expected status progression:

```text
pending/running -> succeeded or failed
```

## Non-Goals

- This design does not require changing Lambda timeout.
- This design does not require creating a new DynamoDB table.
- This design does not require replacing the existing run detail endpoint.
- This design does not add live SSE/WebSocket streaming; polling is sufficient for the requested behavior.

