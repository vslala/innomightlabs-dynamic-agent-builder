# Low Level Design: Automations Backend Module

Date: 2026-05-18  
Status: Implemented  
Owner: InnomightLabs API

## Summary
The automations backend adds a graph-native workflow module under `src/automations/`. It stores automation definitions, nodes, edges, triggers, runs, and per-node run results as first-class DynamoDB entities. Triggers remain separate from graph nodes because they are external entry points and have a different lifecycle from workflow execution.

Phase 1 supports CRUD, graph persistence, and validation. Phase 2 supports synchronous manual/test execution with `invoke_agent` action nodes through `AgentArchitecture.handle_message_buffered(...)`.

## Data Model
Core persisted entities:
- `Automation`: owner-scoped workflow definition with title, description, status, and version.
- `AutomationNode`: graph node with type `start`, `action`, `condition`, or `final`.
- `AutomationEdge`: directed connection between nodes with branch labels such as `next`, `true`, `false`, and `error`.
- `AutomationTrigger`: external entry point such as `manual`, `webhook`, or `schedule`, with `entry_node_id`.
- `AutomationRun`: execution state and context document.
- `AutomationRunNodeResult`: per-node execution input, output, error, and message ids.

Initial action config:
```python
class AutomationActionType(str, Enum):
    INVOKE_AGENT = "invoke_agent"
    SEND_EMAIL = "send_email"
    WEBHOOK_CALL = "webhook_call"


class InvokeAgentActionConfig(BaseModel):
    action_type: AutomationActionType = AutomationActionType.INVOKE_AGENT
    agent_id: str
    prompt_template: str
    input: dict[str, Any] = Field(default_factory=dict)
```

Initial condition config:
```python
class ConditionNodeConfig(BaseModel):
    expression: str
    true_label: str = "true"
    false_label: str = "false"
```

## DynamoDB Shape
Definition ownership:
- `Automation`: `pk=User#{created_by}`, `sk=Automation#{automation_id}`
- `AutomationNode`: `pk=Automation#{automation_id}`, `sk=Node#{node_id}`
- `AutomationEdge`: `pk=Automation#{automation_id}`, `sk=Edge#{edge_id}`
- `AutomationTrigger`: `pk=Automation#{automation_id}`, `sk=Trigger#{trigger_id}`
- `AutomationRun`: `pk=Automation#{automation_id}`, `sk=Run#{created_at}#{run_id}`
- `AutomationRunNodeResult`: `pk=AutomationRun#{run_id}`, `sk=NodeResult#{started_at}#{node_id}`

Run lookup also writes:
- `pk=User#{created_by}`, `sk=AutomationRun#{run_id}`

Webhook triggers are prepared to use the existing `gsi2` later with:
- `gsi2_pk=WebhookTrigger#{token_hash}`
- `gsi2_sk=Automation#{automation_id}#Trigger#{trigger_id}`

## API
Router prefix: `/automations`.

Definition endpoints:
- `POST /automations`
- `GET /automations`
- `GET /automations/{automation_id}`
- `PATCH /automations/{automation_id}`
- `DELETE /automations/{automation_id}`

Graph endpoints:
- `GET /automations/{automation_id}/graph`
- `PUT /automations/{automation_id}/graph`
- Node, edge, and trigger add/update/delete endpoints under the automation.

Execution endpoints:
- `POST /automations/{automation_id}/test-run`
- `GET /automations/{automation_id}/runs`
- `GET /automations/{automation_id}/runs/{run_id}`

## Validation
`AutomationService.validate_graph(...)` enforces:
- At least one `start` node and one `final` node.
- Multiple starts require trigger entry coverage.
- Edge source and target node ids must exist.
- Triggers must reference a valid `start` node.
- All required nodes must be reachable from trigger entries.
- Non-final reachable nodes must have outgoing edges.
- Final nodes cannot have outgoing edges.
- Condition nodes must have valid `true` and `false` outgoing branches.
- `invoke_agent` action nodes must reference an agent owned by the user.
- Cycles are rejected until explicit loop nodes are introduced.

## Runner
The Phase 2 runner is synchronous and in-process:
- Creates an `AutomationRun(status=AutomationRunStatus.RUNNING)`.
- Creates one `AutomationConversation` for the run.
- Walks the graph from the selected trigger entry node.
- Executes `start`, `condition`, `action.invoke_agent`, and `final` nodes.
- Stores each node result and updates the run context document.

Run context shape:
```json
{
  "input": {},
  "trigger": {"type": "manual", "trigger_id": "..."},
  "nodes": {
    "node_id": {
      "status": "succeeded",
      "output": {},
      "message_ids": {},
      "error": null
    }
  }
}
```

Prompt templates support minimal JSONPath substitution:
```text
Hello {{ $.input.name }}
Prior result: {{ $.nodes.extract.output.response_text }}
```

Conditions support truthy JSONPath expressions plus simple `==` and `!=` comparisons.

## Future Phases
- Phase 3: webhook trigger endpoint and token lookup through `gsi2`.
- Phase 4: schedule activation through infrastructure-owned scheduler/EventBridge integration.
- Phase 5: retries, richer error edges, observability, cancellation, and run metrics.
