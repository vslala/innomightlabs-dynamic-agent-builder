# Low Level Design: Automation Smart Values

Date: 2026-05-19
Status: Proposed
Owner: InnomightLabs SPA/API

## Summary

The current automation template system supports `{{ $.path }}` interpolation against the run context, but the only way to reference previous node output is through backend-generated node IDs such as:

```txt
{{ $.nodes.action-bf61da39-efce-49e9-8843-f2adbaaffc70.output.response_text }}
```

That is not usable in a visual builder. Node IDs are implementation details, they change when a node is recreated, and users cannot discover them from the prompt editor. Smart values should instead be based on stable, human-readable step aliases, typed output fields, and an editor that inserts valid references.

This design keeps the existing raw context for compatibility, then adds a first-class alias and smart value layer:

```txt
{{ steps.find_promotional_senders.output.response_text }}
{{ last.output.response_text }}
{{ input.input }}
{{ trigger.type }}
```

The backend remains the source of truth for execution. The frontend becomes the source of discoverability.

## External Product Lessons

n8n expressions expose current input as `$json` and previous nodes by visible node name, with helpers like `$("NodeName").first()`, `$("NodeName").item`, `$("NodeName").all()`, and `$("NodeName").last()`. It also separates direct current-item access from explicit previous-node references. Source: https://docs.n8n.io/data/expression-reference/

n8n item linking tracks which input item generated which output item, so downstream nodes can refer to the relevant previous item without forcing users to manage internal IDs. The InnomightLabs v1 automation runner does not have item arrays yet, but the same principle applies: preserve execution identity internally, expose meaningful references externally. Source: https://docs.n8n.io/data/data-mapping/data-item-linking/

Glean actions are modeled as reusable operations with typed input schemas, typed output schemas, side effects, and error behavior. Workflow agents accumulate prior step outputs into memory so later steps can reason over previous results. Source: https://docs.glean.com/administration/actions/home and https://docs.glean.com/agents/how-agents-work

The local design should adopt these lessons without copying n8n's full JavaScript expression runtime. For this product, a constrained template language is safer and enough for prompts, condition branches, and future action input mappings.

## Current Local Behavior

Relevant files:
- `api/src/automations/runner.py`
- `api/src/automations/models.py`
- `api/src/automations/service.py`
- `spa/src/pages/dashboard/automations/AutomationBuilderPage.tsx`
- `spa/src/types/automation.ts`

`AutomationRunner.run_test()` initializes context:

```py
context={
    "input": input_data,
    "trigger": {"type": "...", "trigger_id": "..."},
    "nodes": {},
}
```

`_store_context_node()` writes results only by node ID:

```py
run.context.setdefault("nodes", {})[node_id] = {
    "status": status,
    "output": output,
    "message_ids": message_ids,
    "error": error,
}
```

`_render_template()` only resolves paths matching `{{ $.something }}`. `_resolve_json_path()` is a minimal dot-path resolver and does not support bracket notation, aliases, path escaping, fallback values, or discoverability metadata.

The SPA prompt editor currently shows this hint:

```tsx
Use context paths like {"{{ $.input }}"} or {"{{ $.nodes.step_id.output.response_text }}"}.
```

That hint encodes the core UX failure: the user needs an opaque `step_id`, but the builder surfaces readable step names.

## Goals

- Make previous step references discoverable and stable enough for users.
- Preserve backend UUID node IDs as execution identity.
- Avoid breaking existing `{{ $.nodes.<node_id>... }}` templates.
- Support prompt templates and condition expressions with the same smart value resolver.
- Add typed output schemas so the UI can offer valid field suggestions.
- Show live preview/evaluation from the latest run context.
- Keep the expression language constrained, deterministic, and safe.

## Non-Goals

- No arbitrary JavaScript execution in templates.
- No full n8n-compatible runtime in v1.
- No item-array linking in v1. The current runner executes one context object through the graph.
- No AI-inferred parameter filling in v1, but the design leaves room for it.

## Data Model Changes

Add a stable user-facing alias to nodes. The alias is unique within an automation and can be regenerated from the name when empty.

```py
class AutomationNode(BaseModel):
    node_id: str = Field(default_factory=lambda: str(uuid4()))
    automation_id: str
    type: AutomationNodeType
    name: str
    alias: str | None = None
    description: str | None = None
    position: dict[str, Any] = Field(default_factory=dict)
    config: dict[str, Any] = Field(default_factory=dict)
```

API response/request types need the same optional `alias`.

```ts
export interface AutomationNode {
  node_id: string;
  automation_id: string;
  type: AutomationNodeType;
  name: string;
  alias?: string | null;
  description?: string | null;
  position: AutomationNodePosition;
  config: Record<string, unknown>;
  created_at: string;
  updated_at?: string | null;
}
```

Alias rules:
- Lowercase slug: `Find Promotional Senders` -> `find_promotional_senders`.
- Allowed pattern: `^[a-z][a-z0-9_]{1,62}$`.
- Reserved aliases: `input`, `trigger`, `steps`, `nodes`, `last`, `current`, `run`, `env`.
- Unique within one automation.
- User can edit alias in advanced step settings.
- Changing an alias should warn when templates currently reference the old alias.

Migration/backfill:
- Existing nodes with missing aliases get generated aliases during graph load/save.
- If two nodes slug to the same alias, append `_2`, `_3`, etc.
- Raw node-ID references continue to resolve.

## Runtime Context Shape

Keep `context.nodes` exactly as-is for compatibility. Add `context.steps` and `context.execution`.

```json
{
  "input": { "input": "Fetch emails for today" },
  "trigger": { "type": "manual", "trigger_id": "..." },
  "nodes": {
    "action-bf61...": { "status": "succeeded", "output": {}, "message_ids": {}, "error": null }
  },
  "steps": {
    "find_promotional_senders": {
      "node_id": "action-c598...",
      "name": "Find Promotional Senders",
      "type": "action",
      "status": "succeeded",
      "output": {},
      "message_ids": {},
      "error": null
    }
  },
  "execution": {
    "last_step_alias": "find_promotional_senders",
    "last_node_id": "action-c598..."
  }
}
```

When a node result is stored:
1. Write `context.nodes[node_id]` as today.
2. Look up the node alias.
3. Write `context.steps[alias]` with the same result plus `node_id`, `name`, and `type`.
4. Update `context.execution.last_step_alias` and `last_node_id`.

This makes the common case readable:

```txt
{{ steps.find_promotional_senders.output.response_text }}
{{ last.output.response_text }}
```

`last` should resolve from `context.execution.last_step_alias`, not from graph order, because condition branches can skip nodes.

## Template Language

Support two syntaxes for a transition period:

1. Legacy JSON context syntax:

```txt
{{ $.input.input }}
{{ $.nodes.action-c5980f58-e4b4-42f3-9fa8-13b19e60e5ff.output.response_text }}
```

2. Smart value syntax:

```txt
{{ input.input }}
{{ trigger.type }}
{{ steps.find_promotional_senders.output.response_text }}
{{ last.output.response_text }}
```

Resolution rules:
- `input.*` maps to `context.input`.
- `trigger.*` maps to `context.trigger`.
- `steps.<alias>.*` maps to `context.steps[alias]`.
- `nodes.<node_id>.*` maps to `context.nodes[node_id]` for legacy/debug usage.
- `last.*` maps to the most recent executed step result.
- Missing values render as an empty string in prompts.
- Missing values evaluate as `None` in conditions.

Add filters/helpers later, but reserve the syntax now:

```txt
{{ steps.find.output.response_text | default("No response") }}
{{ steps.find.output.events | json }}
{{ steps.find.output.events | length }}
```

V1 should implement only:
- `json`: JSON stringify dict/list values.
- `default("...")`: fallback when missing/empty.
- `length`: count string/list/dict.

Do not implement arbitrary function calls.

## Condition Expressions

Condition nodes should use the same resolver as templates.

Supported v1:

```txt
steps.find_promotional_senders.status == "succeeded"
steps.find_promotional_senders.output.response_text != ""
last.output.result
input.input
```

Keep existing `==`, `!=`, and truthy checks. Internally, `_evaluate_condition()` should call the same `SmartValueResolver` used by `_render_template()`.

## Output Catalog

Create a typed catalog of known outputs for each node/action type. This is what powers autocomplete and pickers.

```ts
interface SmartValueField {
  path: string;
  label: string;
  type: "string" | "number" | "boolean" | "object" | "array" | "null" | "unknown";
  description?: string;
  example?: unknown;
}

interface SmartValueSource {
  source: "input" | "trigger" | "step" | "last";
  alias?: string;
  nodeId?: string;
  label: string;
  fields: SmartValueField[];
}
```

Initial catalog:

```ts
const invokeAgentOutputFields = [
  { path: "output.response_text", label: "Response text", type: "string" },
  { path: "output.events", label: "Events", type: "array" },
  { path: "message_ids.user_message_id", label: "User message ID", type: "string" },
  { path: "message_ids.assistant_message_id", label: "Assistant message ID", type: "string" },
  { path: "status", label: "Status", type: "string" },
  { path: "error", label: "Error", type: "string" },
];
```

Condition output:

```ts
[{ path: "output.result", label: "Condition result", type: "boolean" }]
```

Start output:

```ts
[{ path: "output", label: "Manual input", type: "object" }]
```

The frontend can enrich the catalog from latest run samples by walking `latestRun.context.steps[alias]` and adding discovered paths with examples.

## Frontend UX

Add `ContextPathPicker` from the original builder LLD, but make it concrete:

- Triggered by an `{}` icon button beside prompt template and condition fields.
- Also opens when the user types `{{`.
- Groups sources as:
  - Input
  - Trigger
  - Previous steps
  - Last executed step
- Each step row displays `node.name`, alias, type, and execution status from latest run if available.
- Selecting a field inserts a complete token, for example:

```txt
{{ steps.find_promotional_senders.output.response_text }}
```

Add a compact token preview panel under prompt template:
- Shows detected smart values.
- Marks each as `valid`, `unknown alias`, `unknown field`, or `not yet executed`.
- If latest run data exists, show the resolved value preview truncated to 160 characters.

Add an alias editor:
- Location: step inspector, advanced section.
- Label: `Reference name`.
- Helper text: `Used in smart values, for example {{ steps.reference_name.output.response_text }}.`
- Warn on rename when references exist.

Replace the current raw hint with examples users can act on:

```txt
Use smart values like {{ input.input }}, {{ last.output.response_text }}, or pick a previous step field.
```

## Backend Components

Add:

```txt
api/src/automations/smart_values.py
```

Proposed API:

```py
class SmartValueResolver:
    def __init__(self, context: dict[str, Any]):
        self.context = context

    def render_template(self, template: str) -> str:
        ...

    def resolve(self, expression: str) -> Any:
        ...
```

Runner changes:
- `AutomationRunner._render_template()` delegates to `SmartValueResolver.render_template()`.
- `AutomationRunner._resolve_json_path()` is kept as a private compatibility path or moved into resolver.
- `AutomationRunner._evaluate_condition()` delegates value resolution to `SmartValueResolver.resolve()`.
- `_store_context_node()` accepts the full `AutomationNode`, not only `node_id`, so it can write `steps[alias]`.

Service validation changes:
- Validate node aliases for format, uniqueness, and reserved names.
- Validate templates at save time:
  - Syntax is balanced.
  - Referenced aliases exist.
  - Referenced fields are either known from catalog or allowed as dynamic paths with a warning.
- Do not reject unknown fields in v1, because agent outputs can evolve; surface warnings to the SPA later.

## API Contract Additions

Minimal v1 can compute the catalog client-side from graph + latest run. Better v1.5 adds an API endpoint:

```txt
GET /automations/{automation_id}/smart-values
```

Response:

```ts
interface AutomationSmartValuesResponse {
  sources: SmartValueSource[];
  reserved_aliases: string[];
}
```

Optional validation endpoint:

```txt
POST /automations/{automation_id}/smart-values/preview
```

Request:

```json
{
  "template": "Use {{ steps.find.output.response_text }}",
  "context": "latest_run"
}
```

Response:

```json
{
  "rendered": "Use ...",
  "tokens": [
    {
      "token": "{{ steps.find.output.response_text }}",
      "path": "steps.find.output.response_text",
      "status": "resolved",
      "value": "..."
    }
  ]
}
```

## Compatibility

Existing automations using `{{ $.input }}` continue to work.

Existing automations using `{{ $.nodes.<node_id>... }}` continue to work.

New automations should default to alias syntax in generated hints and inserted tokens.

The run context should preserve both `nodes` and `steps` for at least one major version. If raw UUID paths are ever deprecated, the builder can offer an automatic conversion tool by matching node IDs to aliases.

## Example

User-visible graph:

- Start
- Find promotional senders, alias `find_promotional_senders`
- Delete promotional emails, alias `delete_promotional_emails`
- Done

Prompt for second action:

```txt
Delete only the clear promotional emails from this list:

{{ steps.find_promotional_senders.output.response_text }}

Original request:
{{ input.input }}
```

Condition:

```txt
steps.find_promotional_senders.status == "succeeded"
```

This is readable, stable across backend UUIDs, and discoverable through the picker.

## Implementation Plan

1. Backend alias model
   - Add `alias` to automation node domain model, request models, response models, Dynamo serialization, and TypeScript types.
   - Backfill aliases during graph normalization/service save.
   - Add validation for alias format, uniqueness, and reserved names.

2. Backend smart value resolver
   - Add `api/src/automations/smart_values.py`.
   - Move template rendering and path resolution into resolver.
   - Support legacy `$.` and new `input`, `trigger`, `steps`, `nodes`, `last`.
   - Add tests for prompt rendering, condition evaluation, missing values, filters, and legacy paths.

3. Runtime context alias writing
   - Change `_store_context_node()` to write both `nodes[node_id]` and `steps[alias]`.
   - Track `execution.last_step_alias`.
   - Update runner tests to assert both old and new context shapes.

4. Frontend smart value catalog
   - Add `src/pages/dashboard/automations/editor/smartValues.ts`.
   - Generate sources from graph nodes, aliases, node types, and latest run samples.
   - Add token parsing and local validation helpers.

5. Frontend picker and preview
   - Add `ContextPathPicker`.
   - Add `{}` insertion button to prompt and condition fields.
   - Add token validation/preview under editors.
   - Replace raw UUID examples with alias examples.

6. Alias editor UX
   - Add reference-name field in the inspector.
   - Generate alias when adding or renaming steps.
   - Warn before changing aliases used by templates.

7. Optional API preview endpoint
   - Add server-side preview once frontend-only validation is in place.
   - Use latest run context for real resolved values.

## Test Plan

Backend:
- Alias generation from names and duplicate handling.
- Alias validation rejects reserved/invalid names.
- Legacy `{{ $.input.input }}` still renders.
- New `{{ input.input }}` renders.
- `{{ steps.alias.output.response_text }}` renders.
- `{{ last.output.response_text }}` resolves after a previous node executes.
- Conditions can reference aliases.
- Run context stores both `nodes` and `steps`.

Frontend:
- `buildSmartValueSources()` returns input, trigger, last, and prior step sources.
- Picker inserts the correct template token.
- Token parser flags unknown aliases.
- Token parser flags malformed `{{ ... }}`.
- Latest run sample values appear in preview.
- Alias rename warning detects references in prompt templates and conditions.

Manual:
- Create two action nodes.
- Run the first with manual input.
- Use picker in the second prompt to insert the first step response.
- Save and test run.
- Confirm latest run context includes `steps.<alias>` and the second agent receives the resolved first response.

## Risks and Mitigations

- Alias renames can break saved templates.
  - Mitigation: reference scanner + rename warning + optional automatic rewrite.

- Agent output is semi-structured.
  - Mitigation: typed known fields plus sample-derived dynamic fields. Unknown fields warn but do not block save.

- `last` can be ambiguous in branched graphs.
  - Mitigation: define it as the most recently executed non-final node. Prefer explicit `steps.alias` in generated tokens.

- Context can become large.
  - Mitigation: future `memory_policy` per node can decide which fields are retained for downstream steps.

- Users may expect full JSONPath.
  - Mitigation: call the feature "Smart values", document supported dot paths and filters, and avoid claiming full JSONPath compliance.
