# Low Level Design: Automation Skill Actions

Date: 2026-05-21
Status: Proposed
Owner: InnomightLabs API

## Summary
Add direct skill action execution to automations so a workflow action node can call a manifest-declared skill action, such as `google_mail.search`, without first invoking an agent conversation. The automation builder should expose installed skill actions as selectable actions, let users provide action arguments, and allow dynamic values through the same smart-value syntax already used by automation prompts and conditions.

This design should also split authentication from skills into standalone connectors. A connector represents a user-level external account connection, such as Gmail or Google Drive. A skill declares connector dependencies in its manifest. Once the user connects Gmail, Gmail-backed skill actions become available to both agents and automations without requiring per-agent OAuth.

The feature should reuse the existing skill action boundary while moving auth checks to connectors and gradually converting built-in automation actions into first-party skills:
- Skill actions are declared in `src/skills/*/manifest.yml`.
- Skill handlers execute through `src.skills.registry.SkillRegistry.execute_action(...)`.
- Skill manifests declare required connectors.
- Skill manifests can include action configuration forms using the existing `Form`/`FormInput` contract.
- Connector credentials are stored per user/provider and reused across agents and automations.
- Agents and automations keep their own enabled-skill state, but not OAuth credentials.

## Existing State
Relevant files:
- `src/automations/models.py` defines `AutomationActionType` with `invoke_agent`, `send_email`, and `webhook_call`.
- `src/automations/service.py` validates only `invoke_agent`; `send_email` and `webhook_call` are explicit placeholders.
- `src/automations/runner.py` executes only `invoke_agent` action nodes. It renders smart values only inside string prompt templates through `_render_template(...)`.
- `src/skills/service.py` has `SkillRuntimeService.handle_tool_call(...)` for agent tool use and validates that a skill is installed/enabled for an agent before calling the registry.
- `src/skills/registry.py` loads skill manifests and executes actions with `arguments`, installed `config`, and runtime `context`.
- Current OAuth-backed skills, such as Gmail and Google Drive, resolve credentials from provider settings through skill-owned OAuth helpers.
- `../spa/src/pages/dashboard/automations/AutomationBuilderPage.tsx` currently hardcodes action nodes to `invoke_agent`.

## Connector Model
Introduce a first-class connector layer for external account authentication.

Connector responsibilities:
- Own OAuth start/callback routes.
- Own token exchange, refresh, revocation, and credential persistence.
- Expose connection status for the signed-in user.
- Provide runtime credentials to skill handlers by connector id/provider name.

Skills should not own OAuth flow endpoints after this migration. Instead, a skill declares required connectors and uses connector runtime helpers to obtain access tokens.

Initial connectors:
- `google_mail`: Gmail account connection.
- `google_drive`: Google Drive account connection.

The existing encrypted `ProviderSettings` storage can remain the backing store if it already fits user/provider credentials. The conceptual API should be connector-oriented even if the persistence table is reused.

Recommended module shape:

```text
src/connectors/
  models.py
  repository.py
  service.py
  router.py
  google_mail/
    oauth.py
    client.py
  google_drive/
    oauth.py
    client.py
```

Recommended persisted entity, if a new explicit entity is preferred over existing provider settings:

```python
class ConnectorConnection(BaseModel):
    connection_id: str
    connector_id: str
    provider_name: str
    owner_email: str
    status: Literal["connected", "expired", "revoked"]
    encrypted_credentials: str
    scopes: list[str]
    connected_at: datetime
    updated_at: datetime | None = None
```

DynamoDB shape:

```text
pk=User#{owner_email}
sk=Connector#{connector_id}
```

Only one connection per user/connector is required for v1. Multiple accounts per connector can be added later by introducing `connection_id` into the sort key and adding a selected connection reference to enabled-skill records.

## Skill Manifest Connector Dependencies
Extend `src/skills/models.py`:

```python
class SkillConnectorDependency(BaseModel):
    connector_id: str
    required: bool = True


class SkillManifest(BaseModel):
    ...
    connectors: list[SkillConnectorDependency] = Field(default_factory=list)
```

Example Gmail manifest:

```yaml
id: google_mail
namespace: integrations.google
name: Gmail
description: Read and manage messages from the connected Gmail account.
connectors:
  - connector_id: google_mail
    required: true
actions:
  - name: search
    ...
```

Deprecate manifest fields:
- `requires_oauth`
- `oauth_provider_name`

Keep them temporarily for backward compatibility in catalog responses while the SPA migrates to connector-aware checks.

Skill catalog responses should include:

```json
{
  "skill_id": "google_mail",
  "connectors": [
    {
      "connector_id": "google_mail",
      "connected": true,
      "connect_path": "/connectors/google_mail/oauth/start"
    }
  ],
  "available": true
}
```

`available` is true when every required connector dependency is connected for the signed-in user.

## Automation Skill Enablement
Automations should be standalone and should not depend on agents for skill availability.

Add an automation-owned enabled skill record:

```python
class AutomationSkill(BaseModel):
    automation_id: str
    skill_id: str
    namespace: str
    skill_name: str
    skill_description: str
    enabled: bool = True
    config: dict[str, Any] = Field(default_factory=dict)
    enabled_by: str
    enabled_at: datetime
    updated_at: datetime | None = None
```

DynamoDB shape:

```text
pk=Automation#{automation_id}
sk=Skill#{skill_id}
```

This mirrors the current `AgentSkill` concept but excludes OAuth secrets. Secrets live only under connector/provider storage. Skill config remains per orchestrator because an automation may want a default label, site URL, or behavior different from an agent.

Add `src/automations/skills.py` or keep in `src/automations/service.py` initially:
- `list_enabled_skills(automation_id, user_email)`
- `enable_skill(automation_id, skill_id, config, user_email)`
- `update_skill(...)`
- `disable_skill(...)`

Enable validation:
1. Automation must be owned by the user.
2. Skill must exist in `SkillRegistry`.
3. Required connectors from the manifest must be connected for `user_email`.
4. Skill-local install/config validation still runs through the registry or skill package.

## Agent Skill Migration
Agents can keep `AgentSkill` for enabled-skill state, but OAuth fields should be migrated away from agent skill install flows.

Target agent behavior:
- `AgentSkill` stores enabled state and skill config.
- Connector credentials are resolved by `owner_email` and `connector_id`.
- The add-skill dialog checks manifest connector dependencies.
- If a connector is missing, user connects it through `/connectors/...`, then the skill becomes available for install.

This preserves existing agent skill UX while making the authentication reusable by automations.

## Automation Standalone Boundary
Automation skill actions must not depend on the agent module. The implementation should keep these paths separate:

- Core automation graph CRUD, validation, runs, triggers, and skill actions.
- Optional/legacy `invoke_agent` action execution.

The current code imports `AgentRepository` directly in `AutomationService` and `AutomationRunner` because `invoke_agent` was the only action type. The target design is to convert that behavior into a first-party skill so automation can treat agent invocation like any other action.

Recommended first-party skill:

```text
src/skills/agent_invocation/
  manifest.yml
  actions.py
  models.py
```

Manifest sketch:

```yaml
id: agent_invocation
namespace: core.automation
name: Invoke Agent
description: Send a smart-value prompt to one of your agents.
actions:
  - name: invoke
    description: Invoke an agent and return its response text and runtime events.
    input_schema:
      type: object
      required: [agent_id, prompt_template]
      properties:
        agent_id:
          type: string
          description: Agent to invoke.
          # UI is defined in action_form, not in JSON Schema.
        prompt_template:
          type: string
          description: Prompt template with automation smart values.
          # UI is defined in action_form, not in JSON Schema.
    action_form:
      form_name: Invoke Agent
      form_inputs:
        - input_type: select
          label: Agent
          name: agent_id
          attr:
            source: agents
        - input_type: text_area
          label: Prompt template
          name: prompt_template
          attr:
            rows: "10"
            smart_values: "true"
    handler: actions:invoke
```

The saved automation node becomes a normal skill action:

```json
{
  "action_type": "skill_action",
  "skill_id": "agent_invocation",
  "action": "invoke",
  "arguments": {
    "agent_id": "agent-123",
    "prompt_template": "Summarize {{ $.input }}"
  }
}
```

This preserves the current UX because the builder still renders an agent picker and prompt textarea, but the backend no longer needs a special `invoke_agent` node execution branch.

Migration path:
- Keep existing `invoke_agent` config accepted temporarily for backward compatibility.
- On graph save or load, optionally normalize old `invoke_agent` config to `skill_action(agent_invocation.invoke)`.
- New UI should create `agent_invocation.invoke` skill-action nodes only.
- Once existing saved graphs are migrated, remove the special `invoke_agent` execution path.

Longer term, the automation module should own an action execution interface:

```python
class AutomationActionExecutor(Protocol):
    action_type: AutomationActionType

    async def execute(self, request: AutomationActionExecutionRequest) -> AutomationRunNodeResult:
        ...
```

Then `invoke_agent` can be one registered executor rather than a hard dependency of the automation service. This keeps automations standalone while preserving backward compatibility for existing workflows that already invoke agents.

After `agent_invocation.invoke` exists, this executor interface may only be needed for non-skill system nodes. The preferred steady state is that action nodes execute through the skill runtime.

## Manifest-Driven Action Forms
Phase 1 should avoid custom skill-owned frontend components. Instead, extend skill actions with an optional form definition using the existing schema-driven form contract from `src/form_models.py`.

Extend `src/skills/models.py`:

```python
class SkillActionManifest(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    action_form: form_models.Form | None = None
    handler: str
```

The form is used only to render and collect action arguments. The saved node still stores a plain `arguments` object that must match `input_schema`.

Example Gmail search form:

```yaml
actions:
  - name: search
    description: Search Gmail messages.
    input_schema:
      type: object
      properties:
        query:
          type: string
        recent_20:
          type: boolean
        page_size:
          type: integer
    action_form:
      form_name: Gmail Search
      form_inputs:
        - input_type: text_area
          label: Query
          name: query
          attr:
            rows: "3"
            smart_values: "true"
            placeholder: "from:billing@example.com newer_than:7d"
        - input_type: choice
          label: Recent 20
          name: recent_20
          value: "false"
          values: ["true", "false"]
        - input_type: text
          label: Page size
          name: page_size
          attr:
            inputmode: numeric
    handler: actions:search
```

Example agent invocation form:

```yaml
actions:
  - name: invoke
    input_schema:
      type: object
      required: [agent_id, prompt_template]
      properties:
        agent_id:
          type: string
        prompt_template:
          type: string
    action_form:
      form_name: Invoke Agent
      form_inputs:
        - input_type: select
          label: Agent
          name: agent_id
          attr:
            source: agents
        - input_type: text_area
          label: Prompt template
          name: prompt_template
          attr:
            rows: "10"
            smart_values: "true"
    handler: actions:invoke
```

Builder behavior:
- If `action_form` is present, render it using the existing SPA `SchemaForm` pattern.
- Extend the frontend form renderer only where needed for automation action forms:
  - `attr.source="agents"` means options come from the user's agent list.
  - `attr.smart_values="true"` means show the smart-value helper near the field.
- Convert form values into the action `arguments` object.
- Preserve primitive types where possible by using `input_schema` as a coercion guide. For example, `"true"` becomes `true` for boolean fields and `"20"` becomes `20` for integer fields.
- If `action_form` is absent or unsupported, fall back to `AutomationJsonEditor` plus readonly schema panel.

Backend behavior:
- Treat `action_form` as UI metadata only.
- Validation still comes from action `input_schema`, registry required-field checks, and skill-local Pydantic models.
- Never trust frontend form metadata as validation.

## Action Config Contract
Add a new action type:

```python
class AutomationActionType(str, Enum):
    SKILL_ACTION = "skill_action"
    INVOKE_AGENT = "invoke_agent"  # legacy compatibility during migration
    SEND_EMAIL = "send_email"
    WEBHOOK_CALL = "webhook_call"
```

Add a typed config model in `src/automations/models.py`:

```python
class SkillActionConfig(BaseModel):
    action_type: AutomationActionType = AutomationActionType.SKILL_ACTION
    skill_id: str
    action: str
    arguments: dict[str, Any] = Field(default_factory=dict)
```

Example persisted node config:

```json
{
  "action_type": "skill_action",
  "skill_id": "google_mail",
  "action": "search",
  "arguments": {
    "query": "from:{{ $.input.sender }}",
    "start_date": "{{ $.input.start_date }}",
    "recent_20": false,
    "label_ids": ["INBOX"]
  }
}
```

No `agent_id` is present. Automations resolve skill availability from `AutomationSkill` records and connector credentials from the user-level connector layer.

## Smart Values
Prompts already support:

```text
{{ $.input.name }}
{{ $.nodes.extract.output.response_text }}
```

Extend this from prompt-only rendering to recursive value rendering for skill `arguments`.

Implement in `src/automations/runner.py`:

```python
def _render_smart_values(self, value: Any, context: dict[str, Any]) -> Any:
    if isinstance(value, dict):
        return {key: self._render_smart_values(item, context) for key, item in value.items()}
    if isinstance(value, list):
        return [self._render_smart_values(item, context) for item in value]
    if isinstance(value, str):
        return self._render_smart_string(value, context)
    return value
```

String behavior:
- If the whole string is exactly one smart value, return the resolved value with its original type. This supports arrays, booleans, numbers, and objects.
- If the string contains smart values plus other text, interpolate each value as text. Dict/list values should be JSON encoded in mixed strings.
- Missing paths resolve to `""` in mixed strings and `None` for whole-value expressions.

This keeps static JSON arguments typed while allowing dynamic arguments such as:

```json
{
  "message_id": "{{ $.nodes.gmail_search.output.result.messages.0.id }}"
}
```

## Backend Execution
Update `AutomationRunner.__init__` to accept skill and connector dependencies:

```python
def __init__(
    self,
    automation_repo: AutomationRepository | None = None,
    conversation_repo: ConversationRepository | None = None,
    skill_service: SkillService | None = None,
    automation_skill_repo: AutomationSkillRepository | None = None,
    connector_service: ConnectorService | None = None,
):
```

Add `_execute_skill_action(...)` called from `_execute_node(...)` when `node.config["action_type"] == "skill_action"`:

1. Read `skill_id`, `action`, and `arguments`.
2. Verify the skill is enabled for the automation through `AutomationSkillRepository.find_by_id(...)`.
3. Verify all required manifest connectors are connected for `user_email`.
4. Resolve automation skill runtime config.
5. Render `arguments` using recursive smart-value rendering.
6. Call:

```python
result = await self.skill_service.registry.execute_action(
    skill_id=skill_id,
    action_name=action,
    arguments=rendered_arguments,
    config=config,
    context={
        "owner_email": user_email,
        "actor_email": user_email,
        "actor_id": user_email,
        "conversation_id": conversation.conversation_id,
        "automation_id": automation.automation_id,
        "automation_run_id": run.run_id,
        "automation_node_id": node.node_id,
        "orchestrator_type": "automation",
        "orchestrator_id": automation.automation_id,
    },
)
```

7. Store the node result as:

```json
{
  "skill_id": "google_mail",
  "action": "search",
  "arguments": {},
  "result": "Gmail search results: ..."
}
```

If a skill returns a dict/list, store it directly under `result`. If a handler raises, mark the node failed and preserve the error string so existing `error` edges continue to work.

Automation conversations should no longer require an agent id for direct skill-only runs. If `AutomationConversation.agent_id` is currently required, make it optional for automation conversations or store an empty string only as a temporary compatibility shim. The preferred model is `orchestrator_type="automation"` and `automation_id`/`automation_run_id` as the owning execution context.

## Backend Validation
Update `AutomationService` dependencies to include `AutomationSkillRepository`, `SkillRegistry` or `SkillService`, and `ConnectorService`.

Extend `_validate_action_config(...)`:

```python
if action_type == AutomationActionType.SKILL_ACTION.value:
    config = SkillActionConfig(**config)
    enabled = self.automation_skill_repo.find_by_id(automation_id, config.skill_id)
    if not enabled or not enabled.enabled:
        raise AutomationValidationError("skill_action references a skill that is not enabled for this automation")
    loaded = self.skill_registry.get(config.skill_id)
    if not loaded:
        raise AutomationValidationError("skill_action references an unavailable skill")
    missing = self.connector_service.missing_required_connectors(loaded.manifest, user_email)
    if missing:
        raise AutomationValidationError("skill_action requires connected connectors: " + ", ".join(missing))
    if not any(action.name == config.action for action in loaded.manifest.actions):
        raise AutomationValidationError("skill_action references an unknown skill action")
```

Do not fully validate smart-value-rendered arguments at graph-save time because values may not exist until run time. Do perform static required-field validation for literal arguments:
- If a required field is missing from `arguments`, reject the graph.
- If a required field is present as a smart value, accept it and let runtime validation fail if it resolves to invalid data.

The registry already performs required-field checks immediately before handler execution. Skill-local Pydantic models continue to enforce detailed action argument validity.

## Action Catalog for Builder
The automation builder needs a catalog of actions enabled for the automation. Add a backend read endpoint so the SPA can show available skill actions without duplicating manifest parsing.

Recommended endpoint:

```http
GET /automations/{automation_id}/action-catalog
```

Response:

```json
{
  "actions": [
    {
      "action_type": "skill_action",
      "skill_id": "google_mail",
      "skill_name": "Gmail",
      "action": "search",
      "label": "Gmail: Search",
      "description": "Search Gmail messages...",
      "input_schema": {"type": "object", "properties": {}},
      "action_form": {
        "form_name": "Gmail Search",
        "form_inputs": []
      }
    }
  ]
}
```

Implementation can live in `src/automations/models.py` for response schemas and `src/automations/service.py` for `list_action_catalog(automation_id, user_email)`. The service should verify the automation belongs to the user and only include enabled automation skills whose required connectors are connected.

## Automation Skill API
Add endpoints under `/automations/{automation_id}/skills`:

```http
GET /automations/{automation_id}/skills
POST /automations/{automation_id}/skills?skill_id=google_mail
PATCH /automations/{automation_id}/skills/{skill_id}
DELETE /automations/{automation_id}/skills/{skill_id}
```

Responses should include connector dependency status so the builder can prompt the user to connect Gmail or Google Drive before enabling the skill.

Example:

```json
{
  "skill_id": "google_mail",
  "name": "Gmail",
  "enabled": true,
  "connectors": [
    {
      "connector_id": "google_mail",
      "connected": true,
      "connect_path": "/connectors/google_mail/oauth/start"
    }
  ]
}
```

## SPA Builder Changes
Update `../spa/src/types/automation.ts`:
- Add `"skill_action"` to `AutomationActionType`.
- Add `SkillActionConfig`.
- Add action catalog response types.

Update `../spa/src/services/automations/AutomationApiService.ts`:
- Add `getActionCatalog(automationId: string)`.

Update `../spa/src/pages/dashboard/automations/AutomationBuilderPage.tsx`:
- Load enabled automation skills and the automation action catalog.
- Replace the disabled `Action` select with:
  - action family select for enabled automation skill action entries.
  - skill action select should show grouped labels such as `Gmail / Search`, `Gmail / Read`, `Google Drive / Search`.
- When the user chooses a skill action, set config:

```ts
{
  action_type: "skill_action",
  skill_id,
  action,
  arguments: {}
}
```

- Render `action_form` with the existing `SchemaForm` pattern when present. For `agent_invocation.invoke`, this should preserve the existing agent select plus prompt textarea experience.
- Fall back to `AutomationJsonEditor` when an action does not define `action_form` or the form contains unsupported inputs.
- Show the selected action `input_schema` next to the argument editor in a collapsible/readonly panel so the user can see required fields and descriptions.
- Keep smart-value helper available; add examples for direct skill output:

```text
{{ $.nodes.gmail_search.output.result }}
{{ $.nodes.gmail_search.output.skill_id }}
{{ $.nodes.gmail_search.output.action }}
```

Unsupported action forms should use JSON editor plus schema display. Custom skill-owned UI components can be considered later if the shared form contract becomes insufficient.

Add an automation skill management surface, either in the builder side panel or a sibling tab:
- List available skills from `/skills` with connector status.
- If required connector is missing, show `Connect Gmail` / `Connect Google Drive` from connector metadata.
- Once connected, allow enabling the skill for the automation.
- Once enabled, action nodes can use that skill's manifest actions.

## Tests
Add backend tests:

`tests/test_automations_service_validation.py`
- Accepts `skill_action` when the skill is enabled for the automation, required connectors are connected, and the action exists in the manifest.
- Rejects skill not enabled or disabled for the automation.
- Rejects missing connector dependency.
- Rejects unknown action name.
- Rejects missing required literal arguments from manifest schema.

`tests/test_automations_runner.py`
- Executes a fake installed skill action and stores `output.result`.
- Renders smart values recursively in skill arguments.
- Preserves resolved object/array/boolean types for whole-string smart values.
- Follows an `error` edge when the skill handler raises.
- Executes a skill-only automation without requiring an agent id.
- Executes `agent_invocation.invoke` as a normal skill action and returns the same output shape expected by existing run displays.

`tests/test_automations_router.py`
- Returns action catalog only for user-owned automations.
- Includes enabled automation skill actions with input schema.
- Rejects enabling a skill when required connectors are missing.

Connector tests:
- Connector status returns connected/disconnected for user.
- Skill catalog availability reflects connector dependencies.
- Existing Gmail/GDrive OAuth flows persist credentials under connector ownership.

Action form tests:
- Action catalog returns `input_schema` and `action_form`.
- Builder renders `action_form` through the existing form renderer.
- Builder resolves `attr.source="agents"` into agent select options.
- Unsupported forms fall back to JSON editor.

Frontend checks:
- `yarn build`
- Manual builder flow: create skill action node, enter Gmail search arguments with smart values, save, test-run, inspect run output.

Backend checks:

```bash
cd api
uv run pytest -v tests/test_automations_service_validation.py tests/test_automations_runner.py tests/test_automations_router.py
uv run pytest -v
```

## Implementation Order
1. Add backend model enums and response schemas.
2. Introduce connector manifest dependency model and connector status service.
3. Migrate Gmail/GDrive OAuth metadata from skill-owned catalog fields to connector dependency checks.
4. Add `AutomationSkill` persistence and automation skill endpoints.
5. Add manifest-driven action forms to skill action schemas and expose them through the action catalog.
6. Add `agent_invocation` first-party skill wrapping current invoke-agent behavior.
7. Add service dependencies and `skill_action` validation.
8. Add recursive smart-value renderer in `AutomationRunner`.
9. Add runtime execution for `skill_action`.
10. Add action catalog endpoint for the SPA.
11. Update SPA types, API service, skill enablement surface, and builder inspector.
12. Render `action_form` through the existing schema-form pattern, including agent-sourced selects and smart-value-enabled text areas.
13. Add backend and frontend tests.
14. Run backend tests and SPA build.

## Open Decisions
- Output normalization: first implementation should store all skill handler returns under `output.result`. If later builders need richer previews, add optional skill-specific display metadata rather than changing the run context shape.
- Multiple accounts per connector: v1 assumes one connected account per user/connector. Multi-account support should add `connection_id` to connector storage and enabled-skill config.
- Argument UI: v1 supports manifest-driven `action_form` rendering through the existing form module plus JSON editor fallback. Custom skill-owned UI components are a later phase.
