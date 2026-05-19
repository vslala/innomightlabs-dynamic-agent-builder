# Low Level Design: Automation Builder Frontend

Date: 2026-05-18
Status: Proposed
Owner: InnomightLabs SPA

## Summary
Add an Automations area to the dashboard that lets users create, edit, test, activate, deactivate, inspect, and delete automation workflows. The first builder version is a full-page node graph canvas powered by React Flow (`@xyflow/react`) while persisting the backend's graph-native automation model directly.

Phase 1 intentionally supports only:
- Manual triggers.
- `invoke_agent` action nodes.
- Structured IF/ELSE condition nodes.
- Test runs, run history, and run context inspection, because the backend already exposes run endpoints.

The frontend should be designed around registries and adapters from the start so new trigger types, action types, node renderers, and editors can be added without rewriting the builder.

## Existing Context
Relevant backend API is implemented under `api/src/automations/`:
- `POST /automations`
- `GET /automations`
- `GET /automations/{automation_id}`
- `PATCH /automations/{automation_id}`
- `DELETE /automations/{automation_id}`
- `GET /automations/{automation_id}/graph`
- `PUT /automations/{automation_id}/graph`
- Node, edge, and trigger CRUD endpoints.
- `POST /automations/{automation_id}/test-run`
- `GET /automations/{automation_id}/runs`
- `GET /automations/{automation_id}/runs/{run_id}`

Relevant SPA patterns:
- Routes live in `src/App.tsx`.
- Dashboard navigation lives in `src/components/dashboard/Sidebar.tsx`.
- Page title mapping lives in `src/components/dashboard/DashboardLayout.tsx`.
- REST services are singleton classes under `src/services/*`.
- Shared API request handling goes through `src/services/http/client.ts`.
- Agent selection can reuse `agentApiService.listAgents()` from `src/services/agents/AgentApiService.ts`.
- `react-grid-layout` is already used for analytics dashboards, but automation building needs a graph editor rather than a widget layout grid.

## Goals
- Give users a visual canvas for workflow construction.
- Persist exact backend graph entities, not an unrelated frontend-only DSL.
- Keep the first implementation small but structurally extensible.
- Support manual test execution from the builder.
- Expose run history and run detail context inspection.
- Provide activation/deactivation and full automation deletion controls.
- Maintain human-readable step names while preserving backend node IDs as execution identity.

## Non-Goals
- Webhook and schedule trigger configuration in Phase 1.
- `send_email` and `webhook_call` action editors in Phase 1.
- Looping workflows. Backend validation rejects graph cycles.
- Multi-user collaboration or live editing.
- A custom freeform diagram engine. Use React Flow for the node/edge canvas.

## UX Model
The Automations dashboard should be nested like the existing Agents area. The left sidebar has one primary `Automations` link. Clicking it opens the automation section, whose index route shows the list of automations. Builder, runs, analytics, and future automation subpages live under the selected automation route.

The Automations area should have these primary surfaces:

1. `AutomationsListPage`
   - Route: `/dashboard/automations`
   - Shows automations with status, description, created/updated date, and actions.
   - Primary action creates a draft automation, then navigates to the builder.

2. `AutomationDetailLayout`
   - Route: `/dashboard/automations/:automationId`
   - Mirrors `AgentDetailLayout` at a lighter weight.
   - Loads automation metadata once and provides it through outlet context.
   - Provides automation-level navigation such as `Builder`, `Runs`, and later `Analytics`.
   - Keeps destructive and status-level controls discoverable without duplicating them across subpages.

3. `AutomationBuilderPage`
   - Route: `/dashboard/automations/:automationId`
   - This is the index route inside `AutomationDetailLayout`.
   - Full-page builder with a large canvas and side inspector.
   - Header actions: save, test run, active toggle, delete.
   - Canvas contains draggable node cards.
   - Users add nodes from a compact toolbar or command menu.
   - Selecting a node opens its inspector.
   - Selecting the automation background opens workflow settings.

4. `AutomationRunsPage`
   - Route: `/dashboard/automations/:automationId/runs`
   - Shows test run history and run detail, including context and per-node results.

5. `AutomationAnalyticsPage`
   - Route: `/dashboard/automations/:automationId/analytics`
   - Placeholder route for later automation execution analytics.
   - Should not block the builder v1, but the route structure should reserve room for it.

Recommendation: use nested routing now, even if only the list, builder, and runs pages are implemented first. The builder can still include a compact recent-run panel for fast feedback after a test run, but full run history belongs on the nested `runs` route.

## Canvas Design
Use React Flow (`@xyflow/react`) through a thin workflow-specific wrapper rather than binding automation business logic directly to the library.

React Flow is a better fit than `react-grid-layout` for this feature. `react-grid-layout` is useful for dashboards where the main problem is placing rectangular widgets in a responsive grid. Automation authoring is a graph editing problem: nodes, handles, edges, selection, panning, zooming, edge labels, connection validation, and custom node/edge rendering are first-class requirements. React Flow provides those primitives directly and is MIT-licensed.

Rete.js is the main alternative worth tracking. It is a strong visual programming framework with dataflow/control-flow processing engines and a plugin ecosystem. For this product, the backend already owns graph validation and execution, so Rete's frontend engine model is more than v1 needs. React Flow is the more pragmatic canvas layer while keeping execution semantics in the backend.

Proposed wrapper:
```tsx
// src/pages/dashboard/automations/builder/AutomationCanvas.tsx
interface AutomationCanvasProps {
  nodes: AutomationNode[];
  edges: AutomationEdge[];
  selectedNodeId: string | null;
  onSelectNode: (nodeId: string) => void;
  onMoveNode: (nodeId: string, position: AutomationNodePosition) => void;
  onConnectNodes: (sourceNodeId: string, targetNodeId: string, label: AutomationEdgeLabel) => void;
  onAddNextNode: (sourceNodeId: string, type: AutomationNodeType) => void;
  onDeleteNode: (nodeId: string) => void;
}
```

React Flow handles node placement, edge rendering, viewport pan/zoom, node selection, edge selection, connection gestures, and built-in controls. The wrapper owns conversion between backend graph entities and React Flow nodes/edges.

Store node position in backend `AutomationNode.position`, for example:
```json
{
  "x": 480,
  "y": 240
}
```

This maps directly to React Flow node positions:
```ts
const flowNode = {
  id: node.node_id,
  type: node.type,
  position: {
    x: Number(node.position.x ?? 0),
    y: Number(node.position.y ?? 0),
  },
  data: {
    automationNode: node,
  },
};
```

Backend edges map to React Flow edges:
```ts
const flowEdge = {
  id: edge.edge_id,
  source: edge.source_node_id,
  target: edge.target_node_id,
  label: edge.label,
  type: edge.label === "true" || edge.label === "false" ? "condition" : "workflow",
  data: {
    automationEdge: edge,
  },
};
```

Use custom React Flow node types for `start`, `action`, `condition`, and `final`. Use custom edge types for normal flow and condition branches so the UI can render true/false branch labels and later add edge actions.

## Workflow Graph Rules
The frontend should respect backend graph validation but not duplicate it completely. Client validation should prevent obvious broken states and give immediate feedback.

Phase 1 graph shape:
- One `start` node.
- One `final` node.
- Manual trigger points at the start node.
- Linear `next` edges connect normal flow.
- Condition nodes require exactly one `true` edge and one `false` edge.
- Action nodes support an optional `error` edge later, but v1 can omit it from UI.
- Cycles are not allowed.

The builder should keep graph operations in pure helper functions:
```ts
addActionAfter(graph, sourceNodeId, actionConfig)
addConditionAfter(graph, sourceNodeId, conditionConfig)
deleteNodeAndReconnect(graph, nodeId)
updateNodeConfig(graph, nodeId, config)
validateAutomationGraphDraft(graph)
```

These helpers should live outside React components so they can be tested.

## Type Model
Create a dedicated automation type module:
```ts
// src/types/automation.ts
export type AutomationStatus = "draft" | "active" | "disabled" | "deleted";
export type AutomationNodeType = "start" | "action" | "condition" | "final";
export type AutomationActionType = "invoke_agent" | "send_email" | "webhook_call";
export type AutomationTriggerType = "manual" | "webhook" | "schedule";
export type AutomationRunStatus = "pending" | "running" | "succeeded" | "failed" | "cancelled";
export type AutomationNodeRunStatus = "pending" | "running" | "succeeded" | "failed" | "skipped";

export interface AutomationResponse {
  automation_id: string;
  title: string;
  description?: string | null;
  status: AutomationStatus;
  version: number;
  created_by: string;
  created_at: string;
  updated_at?: string | null;
}

export interface AutomationNode {
  node_id: string;
  automation_id: string;
  type: AutomationNodeType;
  name: string;
  description?: string | null;
  position: AutomationNodePosition;
  config: Record<string, unknown>;
  created_at: string;
  updated_at?: string | null;
}

export interface InvokeAgentActionConfig {
  action_type: "invoke_agent";
  agent_id: string;
  prompt_template: string;
  input: Record<string, unknown>;
}

export interface ConditionNodeConfig {
  expression: string;
  true_label: "true";
  false_label: "false";
}
```

Keep backend names (`automation_id`, `node_id`) in API-facing types. UI view models can add camelCase computed fields only inside builder modules.

## Service Layer
Add:
```txt
src/services/automations/AutomationApiService.ts
src/services/automations/index.ts
```

Methods:
```ts
listAutomations(): Promise<AutomationResponse[]>
createAutomation(data: CreateAutomationRequest): Promise<AutomationGraphResponse>
getAutomation(id: string): Promise<AutomationResponse>
updateAutomation(id: string, data: UpdateAutomationRequest): Promise<AutomationResponse>
deleteAutomation(id: string): Promise<void>
getGraph(id: string): Promise<AutomationGraphResponse>
saveGraph(id: string, data: SaveAutomationGraphRequest): Promise<AutomationGraphResponse>
testRun(id: string, data: StartAutomationRunRequest): Promise<AutomationRunResponse>
listRuns(id: string, limit?: number, cursor?: string): Promise<PaginatedResponse<AutomationRunResponse>>
getRun(id: string, runId: string): Promise<AutomationRunDetailResponse>
```

Use the same `URLSearchParams` pagination pattern as `ConversationApiService`.

## Builder Module Structure
Proposed file layout:
```txt
src/pages/dashboard/automations/
  AutomationsListPage.tsx
  AutomationDetailLayout.tsx
  AutomationBuilderPage.tsx
  AutomationRunsPage.tsx
  AutomationAnalyticsPage.tsx
  components/
    AutomationCanvas.tsx
    AutomationNodeCard.tsx
    AutomationToolbar.tsx
    AutomationInspector.tsx
    AutomationHeaderActions.tsx
    AutomationRunsPanel.tsx
    AutomationRunDetailPanel.tsx
    ContextPathPicker.tsx
    ConditionBuilder.tsx
  editor/
    graphAdapter.ts
    graphOperations.ts
    graphValidation.ts
    flowTypes.ts
    nodeRegistry.tsx
    edgeRegistry.tsx
    actionRegistry.tsx
    triggerRegistry.tsx
    contextCatalog.ts
  styles.css
```

Registry examples:
```ts
export const actionRegistry = {
  invoke_agent: {
    label: "Invoke Agent",
    defaultConfig: (): InvokeAgentActionConfig => ({
      action_type: "invoke_agent",
      agent_id: "",
      prompt_template: "",
      input: {},
    }),
    Editor: InvokeAgentActionEditor,
  },
} satisfies Record<string, ActionDefinition>;
```

Later `send_email` and `webhook_call` become new registry entries, not new switch statements across the builder.

## Node Editors
### Start Node
Read-only in v1. Shows that the automation starts from a manual trigger.

### Invoke Agent Node
Fields:
- Step name (`node.name`).
- Description (`node.description`).
- Agent select from `agentApiService.listAgents()`.
- Prompt template textarea.
- Input mapping editor for optional named values.
- Context picker insertion button for prompt template and input values.

Persisted config:
```json
{
  "action_type": "invoke_agent",
  "agent_id": "agent-123",
  "prompt_template": "Summarize {{ $.input.topic }}",
  "input": {
    "topic": "$.input.topic"
  }
}
```

### Condition Node
Fields:
- Step name.
- Left operand from context path picker or literal value.
- Operator: `exists`, `truthy`, `equals`, `not_equals`.
- Right value for equality operators.

Compile to backend expression:
```ts
truthy("$.nodes.extract.output.response_text") => "$.nodes.extract.output.response_text"
equals("$.input.plan", "pro") => "$.input.plan == 'pro'"
notEquals("$.input.plan", "free") => "$.input.plan != 'free'"
```

Persisted config:
```json
{
  "expression": "$.nodes.extract.output.response_text",
  "true_label": "true",
  "false_label": "false"
}
```

The condition editor should preserve a frontend-only structured condition shape where possible in `node.position.ui` or another namespaced position key only if backend accepts arbitrary position data. Better long-term backend option: add `config.ui_condition` or a typed condition model. Until then, regenerate the structured form from supported expressions when possible and fall back to raw expression display.

## Context Picker
The run context shape is:
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

The picker should offer:
- `$.input`
- `$.trigger.type`
- For each preceding reachable node:
  - `$.nodes.<node_id>.status`
  - `$.nodes.<node_id>.output`
  - Common known invoke-agent outputs, if confirmed by backend tests.

Because output schemas are not currently declared by the backend, the first picker must be an assisted path composer, not a fully typed schema browser. It can list known nodes by human-readable name but insert backend-safe node IDs.

Display example:
```txt
Research Customer Intent
$.nodes.node_abc.output.response_text
```

The UI can show the human-readable step name while preserving the inserted `node_id`.

## Human-Readable Step Names
The backend already has `AutomationNode.name`, so no backend change is required for display names. Use:
- `node.node_id` for graph identity, execution context, and edge endpoints.
- `node.name` for UI labels.

Add frontend validation:
- Name is required.
- Name should be unique within an automation as a usability rule, even though backend identity does not require it.
- If duplicate names exist from old data, show a warning but do not block graph loading.

Do not use names in JSONPath. JSONPath should use node IDs because step names can change.

## Activation And Deletion
Activation toggle:
- `draft` or `disabled` to `active`: `PATCH /automations/{id}` with `{ "status": "active" }`.
- `active` to `disabled`: `PATCH /automations/{id}` with `{ "status": "disabled" }`.
- If activation fails with `422`, surface backend validation detail and keep the toggle unchanged.

Deletion:
- Use the existing confirmation dialog pattern.
- `DELETE /automations/{id}`.
- Navigate back to `/dashboard/automations` after success.
- The backend soft-delete operation is expected to hide the automation and its graph from normal reads.

## Test Runs And Context Inspection
Builder test flow:
1. User clicks `Test Run`.
2. Dialog asks for manual input as JSON.
3. Frontend saves dirty graph first or asks the user to save before running. Recommendation: save automatically, then run.
4. Call `POST /automations/{id}/test-run` with `{ "input": parsedJson }`.
5. Fetch run detail with `GET /automations/{id}/runs/{run_id}`.
6. Show per-node result badges on the canvas and full context in the run detail panel.

Run history:
- Use `GET /automations/{id}/runs?limit=20`.
- Support load-more via `next_cursor`.
- Status mapping:
  - `running` -> `in_progress`
  - `succeeded` -> `success` or `completed`
  - `failed` -> `failed`
  - `cancelled` -> `cancelled`
  - `pending` -> `pending`

Context inspector:
- Show formatted JSON for the full context.
- Provide node result list with input, output, error, and message IDs.
- On selecting a run node result, highlight the matching canvas node by `node_id`.

## Routing And Navigation
Update:
- `src/components/dashboard/Sidebar.tsx`: add Automations nav item with a workflow icon, for example `Workflow` from `lucide-react`.
- `src/components/dashboard/DashboardLayout.tsx`: add page titles for automations routes.
- `src/App.tsx`: add nested routes:
```tsx
<Route path="automations" element={<AutomationsListPage />} />
<Route path="automations/:automationId" element={<AutomationDetailLayout />}>
  <Route index element={<AutomationBuilderPage />} />
  <Route path="runs" element={<AutomationRunsPage />} />
  <Route path="analytics" element={<AutomationAnalyticsPage />} />
</Route>
```

## State Management
Use local React state in v1. Avoid adding a global store.

Recommended state split:
```ts
interface AutomationBuilderState {
  graph: AutomationGraphResponse;
  draftGraph: AutomationGraphResponse;
  selectedNodeId: string | null;
  selectedRunId: string | null;
  dirty: boolean;
  validation: AutomationValidationIssue[];
}
```

Use pure functions for graph changes and keep async API calls in the page/container.

Autosave should not be enabled in v1. Provide explicit save and auto-save only before test run. This avoids surprising users while graph editing semantics are still settling.

## Validation Strategy
Client validation:
- Required automation title.
- Required node names.
- Start/final presence.
- Manual trigger exists and points to start node.
- Action node has supported `action_type`.
- Invoke agent action has `agent_id` and `prompt_template`.
- Condition has structured expression and true/false outgoing edges.
- Edges reference existing nodes.
- No obvious cycles.

Server validation remains authoritative. The UI should display backend `422` details exactly enough to fix the graph.

## Error Handling
Follow existing page conventions:
- Initial load: `LoadingState`.
- Load failure: `ErrorState` with retry.
- Mutations: button-level loading states.
- Delete: confirmation dialog.
- Validation: inline issue panel in builder header or inspector.

For API errors, preserve `HttpError.message`. Backend automation validation returns useful `detail` strings.

## Styling Notes
This is an operational builder, not a marketing page. Keep the layout dense and work-focused:
- Full-width builder surface inside dashboard.
- Reduce the dashboard content max-width constraint for the builder route, or add a layout escape option so the canvas can use the page.
- Avoid nested cards. Use a toolbar, canvas surface, and inspector panels.
- Node cards should have stable dimensions to prevent layout jumps.
- Use icon buttons for node actions and text buttons only for primary commands.

A builder route may need a dashboard layout option:
```tsx
<main style={{ flex: 1, padding: isBuilderRoute ? 0 : "2rem" }}>
  <div style={{ maxWidth: isBuilderRoute ? "none" : "80rem", margin: "0 auto" }}>
    <Outlet context={{ user }} />
  </div>
</main>
```

## Implementation Plan
1. Add automation TypeScript API types.
2. Add `AutomationApiService`.
3. Add `@xyflow/react` dependency and React Flow base styles.
4. Add automations nested routes, sidebar item, and page title mapping.
5. Build `AutomationsListPage` with create, status display, and delete.
6. Build `AutomationDetailLayout` with nested automation navigation and shared context.
7. Build `AutomationBuilderPage` data loader and explicit save flow.
8. Add React Flow canvas wrapper and graph adapters.
9. Add node and edge registries with renderers for start, invoke-agent action, condition, final, normal edges, and condition edges.
10. Add inspector editors for workflow settings, invoke-agent nodes, and condition nodes.
11. Add context path picker based on current graph topology.
12. Add graph operations and draft validation helpers.
13. Add manual test-run dialog and compact latest-run panel.
14. Add `AutomationRunsPage` with pagination and run detail context inspection.
15. Add activation toggle and deletion flow.
16. Add focused tests for graph adapter, graph operations, condition expression compilation, and context catalog generation.
17. Run `yarn build` and `yarn lint`.

## Testing Plan
Unit-test pure helpers where practical:
- Backend graph response to React Flow nodes/edges conversion.
- React Flow node positions back to backend graph position conversion.
- Add node after another node.
- Delete node behavior.
- Condition expression compile/parse for supported forms.
- Context catalog includes only reachable prior nodes for a selected node.

Manual verification:
- Create automation.
- Add invoke-agent node.
- Select agent from existing list.
- Insert context path into prompt template.
- Add IF/ELSE condition.
- Save graph.
- Activate, handle validation errors.
- Run test with manual JSON input.
- Inspect context and node outputs.
- Deactivate.
- Delete automation.

## ADR Candidates
Create ADRs once the team agrees on these decisions:

1. `ADR-automation-builder-canvas-library.md`
   - Decision: use React Flow (`@xyflow/react`) for the v1 builder canvas.
   - Rationale: automation authoring is a node/edge graph editing problem, and React Flow provides graph primitives such as custom nodes, handles, edges, selection, panning, zooming, and controls.
   - Consequence: add a new SPA dependency, but keep it isolated behind `AutomationCanvas` and graph adapter helpers.

2. `ADR-automation-graph-source-of-truth.md`
   - Decision: persist backend graph entities directly.
   - Rationale: avoids frontend/backend DSL drift.
   - Consequence: frontend has adapter helpers but does not own an alternate execution format.

3. `ADR-automation-node-registries.md`
   - Decision: use node/action/trigger registries.
   - Rationale: new action and trigger support should be additive.
   - Consequence: each new action ships with default config, validation, renderer, and editor.

4. `ADR-automation-context-paths-use-node-ids.md`
   - Decision: context JSONPath uses node IDs, not step names.
   - Rationale: names are user-editable; node IDs are stable.
   - Consequence: UI must translate IDs to names in pickers and inspectors.

## Open Backend Questions
- Confirm exact output shape for `invoke_agent`; examples mention `response_text`, while the user's concept mentions `output.response`.
- Decide whether condition structured editor metadata should be persisted as backend-supported config or reconstructed from expression strings.
- Confirm whether deleting an automation deletes child graph records physically or soft-deletes the automation and hides graph reads. The UI only needs success semantics, but product copy should be accurate.
- Confirm whether schedule/webhook triggers should be returned but disabled in UI when existing data contains them.
