# Low Level Design: Automation Foreach Construct

Date: 2026-07-14  
Status: Draft  
Owner: InnomightLabs API / SPA

## Summary

Add a first-class `foreach` construct to automations so users can run a nested set of workflow steps once per item in an input array.

The construct should feel like normal programming:

```text
foreach email in $.nodes.search.output.result.messages:
  classify email
  if email.should_delete:
    delete email
  else:
    skip
continue workflow
```

The important design decision is that `foreach` is not a graph cycle. It is a scoped container node. The outer graph stays acyclic, and the runner executes the child graph repeatedly in code. This fits the current graph validation model, keeps the canvas understandable, and avoids turning React Flow edges into runtime loops.

## Goals

- Let users iterate over arrays produced by previous nodes or trigger input.
- Let the foreach body contain normal automation steps: action, condition, nested foreach later, and final/body-end nodes.
- Pass each array item and index into the nested body through stable smart values.
- Persist per-iteration output in run context so later steps can use aggregated results.
- Keep top-level graph validation acyclic.
- Keep the implementation extensible through scoped graph helpers and runner executors.

## Non-Goals

- Parallel foreach execution in v1.
- Retry policy per item in v1.
- Arbitrary Python/Jinja expressions.
- Mutating global context directly from child nodes except through normal node outputs and foreach aggregation.

## Current Architecture Fit

Current backend:

- `AutomationNodeType`: `start`, `action`, `condition`, `final`.
- `AutomationService.validate_graph(...)` rejects cycles.
- Runner walks a node/edge graph from start to final.
- Smart values resolve against the run context, for example:
  - `{{ $.input.name }}`
  - `{{ $.nodes.search.output.result }}`

Current frontend:

- React Flow canvas renders normal graph nodes.
- Node config is stored as `AutomationNode.config`.
- Builder helpers already centralize graph operations such as inserting action and condition nodes.

`foreach` should extend these patterns instead of adding a separate workflow DSL.

## Data Model

### Node Type

Add:

```python
class AutomationNodeType(str, Enum):
    START = "start"
    ACTION = "action"
    CONDITION = "condition"
    FOREACH = "foreach"
    FINAL = "final"
```

### Scoped Nodes

Add optional scope ownership to `AutomationNode`:

```python
class AutomationNode(BaseModel):
    ...
    parent_node_id: str | None = None
```

Meaning:

- `parent_node_id is None`: top-level workflow node.
- `parent_node_id == <foreach_node_id>`: node belongs to that foreach body.

Persist `parent_node_id` in DynamoDB and API responses. Existing automations default to `None`, so this is backward compatible.

### Foreach Config

Add a config model:

```python
class ForeachNodeConfig(BaseModel):
    items_path: str
    item_alias: str = "item"
    index_alias: str = "index"
    body_start_node_id: str
    body_final_node_id: str
    max_items: int = 100
    empty_behavior: Literal["skip", "fail"] = "skip"
    failure_policy: Literal["fail_fast", "continue", "collect_errors"] = "fail_fast"
    output_mode: Literal["collect_final_outputs", "collect_all_context"] = "collect_final_outputs"
```

`items_path` must be a smart-value JSONPath and must resolve to an array at runtime:

```json
{
  "items_path": "$.nodes.search.output.result.messages",
  "item_alias": "email",
  "index_alias": "email_index",
  "body_start_node_id": "foreach_email_start",
  "body_final_node_id": "foreach_email_done",
  "max_items": 100,
  "empty_behavior": "skip",
  "failure_policy": "fail_fast",
  "output_mode": "collect_final_outputs"
}
```

## Smart Values Inside Foreach

During each iteration, the runner injects loop variables into context:

```json
{
  "loops": {
    "foreach_emails": {
      "item": {"id": "msg_123", "subject": "Sale"},
      "index": 0,
      "alias": {
        "email": {"id": "msg_123", "subject": "Sale"},
        "email_index": 0
      }
    }
  }
}
```

Supported references:

```text
{{ $.loops.foreach_emails.item }}
{{ $.loops.foreach_emails.index }}
{{ $.loops.foreach_emails.alias.email }}
{{ $.loops.foreach_emails.alias.email_index }}
```

The alias layer lets prompt text read naturally while keeping a stable canonical shape.

Later steps after the foreach can use:

```text
{{ $.nodes.foreach_emails.output.items }}
{{ $.nodes.foreach_emails.output.succeeded_count }}
{{ $.nodes.foreach_emails.output.failed_count }}
```

## Run Context Shape

When the foreach node finishes:

```json
{
  "nodes": {
    "foreach_emails": {
      "status": "succeeded",
      "output": {
        "items": [
          {
            "index": 0,
            "status": "succeeded",
            "item": {"id": "msg_123"},
            "output": {"deleted": true},
            "error": null
          }
        ],
        "succeeded_count": 1,
        "failed_count": 0,
        "total_count": 1
      },
      "message_ids": {},
      "error": null
    }
  }
}
```

Also store regular `AutomationRunNodeResult` records for the foreach node itself. Child node results should be persisted with iteration metadata:

```python
class AutomationRunNodeResult(BaseModel):
    ...
    parent_node_id: str | None = None
    iteration_index: int | None = None
```

This makes run inspection clear:

- Foreach node result: summary.
- Child result: exact input/output for item 0, item 1, etc.

## Validation Rules

Validation should become scope-aware.

Top-level rules remain:

- At least one top-level start node.
- At least one top-level final node.
- Top-level graph must be acyclic.
- Top-level reachable nodes must be reachable from triggers/start.

Foreach body rules:

- `foreach` node config must include valid `items_path`, `body_start_node_id`, and `body_final_node_id`.
- `items_path` must be a smart-value path beginning with `$.`.
- `max_items` must be bounded, recommended `1..1000`, default `100`.
- `body_start_node_id` and `body_final_node_id` must reference nodes whose `parent_node_id` is the foreach node id.
- Foreach child graph must be acyclic.
- Child graph must be reachable from `body_start_node_id`.
- Body final node cannot have outgoing edges.
- Edges inside a foreach body must connect nodes in the same scope.
- Edges cannot cross scope boundaries except:
  - External edge into the foreach container node.
  - External edge out of the foreach container node.

Recommended validation helper:

```python
@dataclass(frozen=True)
class GraphScope:
    scope_id: str | None
    nodes: list[AutomationNode]
    edges: list[AutomationEdge]
    entry_node_ids: set[str]
```

`AutomationService.validate_graph(...)` can build scopes and validate each scope with the same graph validator.

## Runner Design

Introduce a node-executor registry so `foreach` does not add more branching to the runner:

```python
class AutomationNodeExecutor(Protocol):
    async def execute(self, ctx: NodeExecutionContext) -> AutomationRunNodeResult:
        ...


class NodeExecutorRegistry:
    def get(self, node: AutomationNode) -> AutomationNodeExecutor:
        ...
```

Executors:

- `StartNodeExecutor`
- `ConditionNodeExecutor`
- `ActionNodeExecutor`
- `ForeachNodeExecutor`
- `FinalNodeExecutor`

The existing `AutomationRunner._execute_node(...)` can be migrated incrementally to this registry. For v1, only extracting `ForeachNodeExecutor` plus small wrappers around existing behavior is enough.

### Foreach Execution

Pseudo-code:

```python
async def execute_foreach(ctx):
    config = ForeachNodeConfig(**ctx.node.config)
    items = resolve_json_path(config.items_path, ctx.run.context)
    if not isinstance(items, list):
        return failed("Foreach input must resolve to an array")
    if not items and config.empty_behavior == "fail":
        return failed("Foreach input array is empty")

    results = []
    for index, item in enumerate(items[: config.max_items]):
        iteration_context = build_iteration_context(ctx.run.context, ctx.node.node_id, config, index, item)
        iteration_result = await execute_scoped_graph(
            scope_parent_node_id=ctx.node.node_id,
            entry_node_id=config.body_start_node_id,
            final_node_id=config.body_final_node_id,
            context=iteration_context,
        )
        results.append(iteration_result)
        if iteration_result.failed and config.failure_policy == "fail_fast":
            return foreach_failed(results)

    return foreach_succeeded(results)
```

The scoped graph executor should reuse the same node execution machinery as the top-level runner, but with a constrained node set and edge set.

## Error Semantics

`foreach.failure_policy` controls item failures:

- `fail_fast`: first failed iteration fails the foreach node and follows the foreach node's `error` edge if present.
- `continue`: failed items are collected, foreach node still succeeds if the loop completes.
- `collect_errors`: loop completes, foreach node fails if any item failed.

This gives users control:

- Bulk delete emails: `continue` may be useful.
- Generate invoices: `fail_fast` is safer.
- Data validation: `collect_errors` is ideal.

## Graph Edges

Outer graph:

```text
Search emails -> Foreach emails -> Generate summary -> Done
                          |
                          error -> Failure final
```

Foreach body scope:

```text
Body Start -> Classify email -> Condition -> Delete / Skip -> Body Done
```

Persist body edges normally as `AutomationEdge`, but source and target nodes both have `parent_node_id=<foreach_node_id>`.

## API Changes

Models:

- Add `AutomationNodeType.FOREACH`.
- Add `AutomationNode.parent_node_id`.
- Add `parent_node_id` and `iteration_index` to run node result models.
- Add `ForeachNodeConfig`.

No new routes are required. Existing graph save/load APIs can carry `parent_node_id` and foreach config.

## Frontend Design

### Canvas

Render `foreach` as a container node:

- Header: `Foreach`
- Subtext: selected array smart value.
- Body preview: child step count.
- Action: `Open loop body`.

Clicking `Open loop body` changes the builder scope:

- Breadcrumb: `Workflow / Foreach emails`
- Canvas shows only child nodes for that foreach body.
- Toolbar adds steps inside the body.
- Back button returns to parent graph.

This is cleaner than trying to render every nested node inside the same full canvas at all zoom levels.

### Inspector

Fields:

- Array smart value input: `items_path`
- Item alias: default `item`
- Index alias: default `index`
- Max items
- Empty behavior
- Failure policy
- Output mode

The smart-value picker should filter to likely array outputs where possible, but the backend remains the source of truth and validates runtime type.

### Builder Helpers

Add pure graph helpers:

```ts
addForeachAfter(graph, sourceNodeId)
enterScope(graph, foreachNodeId)
addNodeInsideScope(graph, parentNodeId, type)
deleteScope(graph, foreachNodeId)
validateScopedGraphDraft(graph)
```

When creating a foreach node, also create default body nodes:

- body start
- body final
- edge body start -> body final

## Run Analysis UI

Update run detail view to show hierarchy:

```text
Foreach emails
  iteration 0
    classify email
    delete email
  iteration 1
    classify email
    skip email
```

When selecting a child node result, show:

- Parent foreach node id.
- Iteration index.
- Loop item JSON.
- Input/output/tool calls as today.

This builds naturally on the recent run-analysis split between node input, tool calls, lifecycle, and output response.

## Marketplace Behavior

Automation marketplace templates should preserve foreach scopes exactly:

- Preserve `parent_node_id`.
- Preserve foreach configs.
- Preserve child node ids so smart values remain stable.
- Regenerate edge ids on import as currently planned.
- Import inputs can be used in `items_path`, for example:
  - `$.inputs.gmail_messages`

## Implementation Steps

1. Add `FOREACH` node type, `parent_node_id`, and foreach config models.
2. Update DynamoDB serialization/deserialization for nodes and node results.
3. Add scope-aware graph validation.
4. Add scoped graph execution helper in runner.
5. Add `ForeachNodeExecutor`.
6. Add run context aggregation and child node result metadata.
7. Add backend tests:
   - rejects non-array runtime input.
   - executes body once per item.
   - supports condition inside foreach.
   - supports failure policies.
   - rejects cross-scope edges.
   - preserves acyclic validation.
8. Update SPA types for `foreach` and scoped nodes.
9. Add foreach node card, inspector fields, and scope navigation.
10. Add run-analysis grouping by foreach iteration.
11. Update marketplace publish/import tests for scoped graphs.
12. Run:

```bash
cd api
uv run pytest -v
cd ../spa
yarn build
```

## Open Questions

1. Should v1 allow nested foreach inside foreach, or block nested foreach until the UI is mature?
2. Should v1 default `failure_policy` to `fail_fast` or `collect_errors`?
3. Should max item count be user-configurable up to 1000, or capped lower for cost control?

Recommendation:

- Allow the backend design to support nested foreach, but hide nested foreach creation in the UI for v1.
- Default to `fail_fast`.
- Default `max_items=100`, cap at `1000`.
