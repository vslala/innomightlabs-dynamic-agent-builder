# Skill Manifest Reference

`manifest.yml` is the contract between a skill package, the agent runtime, the automation action catalog, the install UI, and optional skill-owned HTTP routes. This file should be clear enough that an agent can choose the right action and strict enough that the backend and SPA can render forms without bespoke code.

This guide documents every supported manifest key in the current codebase and shows examples from existing skills.

## Minimal Manifest

```yaml
id: wordpress_search
namespace: integrations.wordpress
name: WordPress Search
description: Search posts from a configured WordPress site.
system_prompt: |
  Use this skill when the user asks to find or inspect blog posts from WordPress.
actions:
  - name: search
    description: Search WordPress posts.
    input_schema:
      type: object
      required: [query]
      properties:
        query:
          type: string
          description: Query text.
    handler: actions:search
form:
  - input_type: text
    name: site_url
    label: WordPress Site URL
    attr:
      placeholder: https://example.com
```

The registry scans `src/skills/*/manifest.yml`, validates the file against `SkillManifest`, and skips invalid manifests with a startup warning.

## Skill Package Layout

A normal skill folder looks like this:

```text
src/skills/my_skill/
  __init__.py
  manifest.yml
  actions.py
  models.py
  router.py                 # optional, only with api_router
  lifecycle/                # optional, for cleanup hooks
    __init__.py
    some_action.py
```

Keep skill-specific code inside the skill folder. Shared platform code belongs in `src/skills`, `src/form_models.py`, provider settings, connectors, or runtime modules only when more than one skill needs it.

## Top-Level Keys

### `id`

Required string. Stable machine id for the skill.

Used for:

- catalog lookup
- agent skill install records
- runtime action execution
- skill-owned API prefix `/skills/{id}`
- automation action catalog references

Example:

```yaml
id: google_mail
```

Prefer the folder name as the id. Use snake_case and do not rename it after users have installed the skill.

### `namespace`

Required string. Dotted grouping for catalog organization and ownership.

Examples:

```yaml
namespace: integrations.google
namespace: core.productivity
namespace: growth.leads
```

Use namespace to describe the domain, not the implementation module.

### `name`

Required string. Human-readable skill name shown in catalogs and installed skill lists.

Examples:

```yaml
name: Gmail
name: Send Email
name: Interactive Forms
```

### `description`

Required string. Short product-facing summary.

Example from `send_email`:

```yaml
description: Send a templated email to configured recipients.
```

Keep this concise. Detailed usage guidance belongs in `system_prompt` and action descriptions.

### `system_prompt`

Optional string. Instructions injected into the agent’s skill context after the skill is installed. Use this to teach the agent when to use the skill, which action to prefer, safety constraints, and exact calling conventions.

Example from `lead_capture`:

```yaml
system_prompt: |
  Use this skill to collect structured input from the user via interactive forms.

  Critical reliability rule:
  - Never say that you have sent, shown, rendered, or displayed a form unless you actually call render_form or render_custom_form in that same turn.
```

Good `system_prompt` content:

- when to use the skill
- which action to call first
- examples of valid action arguments
- action ordering rules
- safety or confirmation rules
- common mistakes the agent must avoid

Avoid burying runtime-critical validation only in the prompt. Also enforce it in action models.

### `repeatable`

Optional boolean, default `false`.

When `false`, the skill has one installed instance per agent or automation. When `true`, the same skill can be installed multiple times with different identity fields.

Example from `agent_invocation`:

```yaml
repeatable: true
repeatable_identity_fields: [target_agent_id]
```

Example from `send_email`:

```yaml
repeatable: true
repeatable_identity_fields: [to]
```

Use `repeatable` when two installations of the same skill with different configuration should be treated as distinct tools. For example, invoking different target agents or sending email to different fixed recipient groups.

### `repeatable_identity_fields`

Optional list of install-form field names, default `[]`.

When `repeatable: true`, these fields are used to derive a deterministic installed skill id. That gives each unique configuration a stable install identity and prevents installing the exact same identity twice.

Rules:

- Field names must come from top-level `form`.
- Pick fields that define the identity of the installation.
- Do not include secrets.
- Do not include cosmetic fields.
- Keep the list short.

Good:

```yaml
repeatable_identity_fields: [target_agent_id]
```

Risky:

```yaml
repeatable_identity_fields: [display_name]
```

### `requires_oauth`

Optional boolean, default `false`.

Set to `true` when the skill requires a connected provider account before installation or use.

Example from `google_mail`:

```yaml
requires_oauth: true
oauth_provider_name: GoogleMail
```

The skill catalog checks provider settings and connector status so unavailable OAuth skills can be shown as disconnected or unavailable instead of failing late.

### `oauth_provider_name`

Optional string. ProviderSettings key used to find encrypted OAuth credentials.

Examples:

```yaml
oauth_provider_name: GoogleMail
oauth_provider_name: GoogleDrive
```

This name must match the provider stored in `ProviderSettings` and any metadata in `src/skills/oauth_providers.py`.

### `connectors`

Optional list of connector dependencies, default `[]`.

Each item has:

```yaml
connector_id: google_mail
required: true
```

Example from `google_mail`:

```yaml
connectors:
  - connector_id: google_mail
    required: true
```

Connectors make availability explicit for agent skills and automation actions. If a required connector is missing, the skill can be shown as unavailable or disabled instead of being offered as a working action.

Use connectors for external accounts/services. Use install `form` for skill-specific configuration values.

### `automation`

Optional object. Controls whether the skill is generally available as automation actions.

Schema:

```yaml
automation:
  enabled: true
```

Default:

```yaml
automation:
  enabled: true
```

Set top-level `automation.enabled: false` when the whole skill should never appear in automation action catalogs.

Use action-level `automation.enabled: false` when only specific actions should be hidden from automations.

### `api_router`

Optional string. Skill-owned FastAPI router reference mounted under `/skills/{skill_id}`.

Format:

```yaml
api_router: router:router
```

Resolution:

- `router:router` resolves to `src.skills.<skill_folder>.router.router`
- fully qualified module paths are also supported
- routers are mounted during app startup by `build_skill_api_routers`

Use this only when the skill needs HTTP endpoints beyond runtime actions, such as callbacks, previews, or skill-owned resources.

### `lifecycle`

Optional object. Skill-level lifecycle hooks. Current runtime support is focused on `delete`.

Schema:

```yaml
lifecycle:
  delete:
    handler: lifecycle.cleanup:on_delete
```

Skill-level delete hooks run when a skill is uninstalled from an agent. Hooks are optional and non-blocking for destructive operations. If a hook fails, the delete still proceeds and the error is logged.

Lifecycle context includes:

- `event`
- `target_type`
- `owner_email`
- `skill_id`
- `installed_skill_id`
- `config`
- `metadata`

Use skill-level lifecycle for cleanup tied to the installed skill as a whole.

### `actions`

Optional list, default `[]`, but a useful skill normally has at least one action.

Each action describes one callable runtime operation. See [Action Keys](#action-keys).

### `form`

Optional list of install-time configuration inputs, default `[]`.

This is rendered when a user installs/configures the skill. The submitted values become the installed skill config. Secret fields are encrypted.

Example from `wordpress_search`:

```yaml
form:
  - input_type: text
    name: site_url
    label: WordPress Site URL
    attr:
      placeholder: https://example.com
  - input_type: password
    name: app_password
    label: WordPress App Password
    attr:
      optional: "true"
      secret: "true"
```

Use top-level `form` for stable values provided during skill activation. Use action `input_schema` and `action_form` for values supplied when the agent or automation invokes an action.

Install form fields can also expose short, user-provided usage context back to the skill runtime. Use this for routing hints or human-readable purpose statements that help a runtime caller decide when to use a configured skill instance. Do not expose secrets or long internal instructions.

Example from `agent_invocation`:

```yaml
form:
  - input_type: select
    name: target_agent_id
    label: Agent
    options_source:
      type: agents
  - input_type: text_area
    name: usage_description
    label: When should this agent be invoked?
    attr:
      rows: "4"
      placeholder: "Use this agent when the task needs SEO research, content planning, or recent blog summaries."
      expose_to_runtime: "true"
      usage_context_label: "Use when"
      usage_context_max_chars: "500"
```

When installed, the exposed field is rendered in the runtime skill context:

```text
- agent_invocation: Invoke Agent - Send a smart-value prompt to one of your agents. (skill_id: agent_invocation)
  Use when: Use this agent when the task needs SEO research, content planning, or recent blog summaries.
```

## Action Keys

Each item in `actions` is a `SkillActionManifest`.

### `name`

Required string. Stable action id.

Examples:

```yaml
name: search
name: read
name: batch_delete
name: render_custom_form
```

Action names should be verbs or verb phrases. Use precise names for destructive actions.

### `aliases`

Optional list of strings, default `[]`.

Aliases are accepted by the runtime when resolving an action.

Example from `google_mail`:

```yaml
aliases: [search_messages, search_email, search_emails]
```

Use aliases for agent ergonomics and backwards compatibility. Keep `name` stable as the canonical action id.

### `description`

Required string. Describes what the action does.

Example:

```yaml
description: Move multiple Gmail messages to trash in batches. This is not permanent deletion.
```

Descriptions matter because agents use them to choose actions. Include important safety and scope details.

### `input_schema`

Optional JSON-schema-like object. Defaults to:

```yaml
type: object
properties: {}
```

The runtime uses `required` for lightweight required-field checks. Automation uses the schema for action metadata. Deep validation should still happen in the action handler with Pydantic models.

Example from `google_drive.search`:

```yaml
input_schema:
  type: object
  properties:
    query:
      type: string
      description: Search text for matching file names or content metadata.
    mode:
      type: string
      enum: [search, list, children]
      description: search=full-text search, list=list visible files, children=list direct children of a folder.
    recursive:
      type: boolean
      description: For mode=children, recursively traverse nested folders.
  required: [query]
```

Supported JSON schema patterns in project examples:

- `type: string`
- `type: integer`
- `type: boolean`
- `type: object`
- `type: array`
- `items`
- `properties`
- `required`
- `enum`
- `additionalProperties`
- descriptions on every field

Guidelines:

- Give every property a useful `description`.
- Put all required inputs in `required`.
- Use `enum` for bounded values.
- Use arrays for repeated values, not comma-separated strings, unless the external API truly expects text.
- Keep destructive fields explicit, for example `message_ids` instead of `ids`.

### `action_form`

Optional `Form`. Used by automation/action UIs to ask for exact action inputs instead of raw JSON.

Example from `send_email`:

```yaml
action_form:
  form_name: Send Email
  submit_path: ""
  form_inputs:
    - input_type: text
      name: subject
      label: Subject
      attr:
        smart_values: "true"
    - input_type: text_area
      name: body
      label: Body
      attr:
        rows: "10"
        smart_values: "true"
```

Example using key/value input from `scheduler.schedule_automation`:

```yaml
action_form:
  form_name: Schedule Automation
  submit_path: ""
  form_inputs:
    - input_type: key_value
      name: input
      label: Input
      attr:
        help_text: "Optional. Add values only when this automation expects scheduled run input."
        empty_text: "No input values will be passed to the scheduled automation."
        key_placeholder: "customer_email"
        value_placeholder: "{{ input.email }}"
        add_label: "Add input"
        smart_values: "true"
```

Use `action_form` whenever an action is available to automations. Without it, users may have to edit raw JSON.

### `automation`

Optional action-level automation config. Defaults to enabled.

Schema:

```yaml
automation:
  enabled: false
```

Example from `scheduler.create_or_update`:

```yaml
actions:
  - name: create_or_update
    automation:
      enabled: false
```

Use this when an action makes sense for agents but not as an automation action. For example, scheduler `create_or_update` wakes the current agent in the current conversation, which is not the right abstraction for automation trigger management.

### `lifecycle`

Optional action-level lifecycle hooks. Current runtime support is focused on `delete`.

Example from `scheduler.schedule_automation`:

```yaml
lifecycle:
  delete:
    handler: lifecycle.schedule_automation:on_delete
```

Action delete hooks run when an automation action node using that skill action is deleted or when an automation is deleted. The hook receives action arguments, installed skill config, and metadata such as automation id and node id.

Use action lifecycle hooks for external resources created by that action, such as schedules, remote subscriptions, or webhooks.

### `handler`

Required string. Python callable that executes the action.

Relative handler example:

```yaml
handler: actions:search
```

This resolves to:

```text
src.skills.<skill_folder>.actions.search
```

Fully qualified handlers are also supported if the module starts with `src.`.

Action handler signature:

```python
async def search(
    arguments: dict[str, Any],
    config: dict[str, Any],
    context: dict[str, Any],
) -> str | dict[str, Any]:
    ...
```

The handler may be sync or async. The registry awaits it when needed.

## Form Input Keys

`form` and `action_form.form_inputs` use the shared `FormInput` schema.

### `input_type`

Required. Supported values:

- `text`
- `text_area`
- `password`
- `select`
- `choice`
- `file_upload`
- `key_value`

Examples:

```yaml
input_type: text
input_type: password
input_type: key_value
```

For HTML-specific types such as email, URL, or phone, use `input_type: text` and set `attr.type`.

### `name`

Required. Stable key used in config or action arguments.

Examples:

```yaml
name: site_url
name: target_agent_id
name: prompt_template
```

Do not rename fields casually. Installed configs and automation action arguments depend on these keys.

### `label`

Required. User-visible field label.

Example:

```yaml
label: Recipient emails
```

### `value`

Optional string default.

Example:

```yaml
value: UTC
```

### `values`

Optional list of string choices. Useful for simple `select` or `choice` inputs where label and stored value are identical.

Example:

```yaml
values: ["true", "false"]
```

### `options`

Optional list of `{value, label}` objects. Use this when the display label differs from the stored value.

Example from custom form schema:

```yaml
options:
  - value: bridge
    label: Take the bridge
  - value: engine_room
    label: Go to the engine room
```

### `options_source`

Optional dynamic option source metadata for `select` and `choice`.

Schema:

```yaml
options_source:
  type: agents
  mode: hydrate
  endpoint: null
```

Current source types:

- `agents`
- `agent_model_providers`
- `agent_models`

Example from `agent_invocation` install form:

```yaml
form:
  - input_type: select
    name: target_agent_id
    label: Agent
    options_source:
      type: agents
```

`mode: hydrate` resolves options on the backend before the form is returned. `mode: lazy` and `endpoint` are part of the schema contract, but only use them when the frontend supports that source and flow.

### `attr`

Optional string map for UI hints and runtime metadata.

Common keys:

- `placeholder`: placeholder text shown by the frontend.
- `rows`: textarea row count.
- `optional`: set to `"true"` to allow an empty install config value.
- `secret`: set to `"true"` to encrypt the value and hide it from API responses.
- `expose_to_runtime`: set to `"true"` to render this installed config value in the runtime installed-skill context.
- `usage_context_label`: label used when rendering an exposed usage context value. Defaults to the field `label`.
- `usage_context_max_chars`: maximum rendered characters for an exposed value. Defaults to `600`.

Example:

```yaml
attr:
  expose_to_runtime: "true"
  usage_context_label: "Use when"
  usage_context_max_chars: "500"
```

Only expose short, user-facing summaries. Never expose passwords, API keys, OAuth tokens, or full internal prompts. Fields marked `secret: "true"` are never rendered to the runtime skill context even if `expose_to_runtime` is also set.

### `validation`

Optional declarative validation metadata.

Schema:

```yaml
validation:
  format: email
  multiple: true
  separator: ","
  min_items: 1
  max_items: 10
```

Example from `send_email`:

```yaml
form:
  - input_type: text
    name: to
    label: Recipient emails
    attr:
      placeholder: "name@example.com, team@example.com"
    validation:
      format: email
      multiple: true
      separator: ","
      min_items: 1
```

Current format support includes `email`.

### `attr`

Optional string map for UI hints and behavior flags.

Common keys in this project:

```yaml
attr:
  placeholder: "0 9 * * 1-5"
  optional: "true"
  secret: "true"
  smart_values: "true"
  rows: "10"
  type: "email"
  help_text: "Shown near the field."
  empty_text: "Shown when key_value has no rows."
  key_placeholder: "customer_email"
  value_placeholder: "{{ input.email }}"
  add_label: "Add input"
```

Important flags:

- `optional: "true"` means install config validation allows the field to be empty.
- `secret: "true"` means the install value is encrypted and not stored in plain config.
- `smart_values: "true"` allows automation UIs to insert smart values.

All `attr` values should be strings.

## OAuth and Connector Example

Use OAuth and connectors when the skill depends on a user-connected external account.

Example from `google_mail`:

```yaml
id: google_mail
namespace: integrations.google
name: Gmail
description: Read and manage messages from the connected Gmail account.
requires_oauth: true
oauth_provider_name: GoogleMail
connectors:
  - connector_id: google_mail
    required: true
actions:
  - name: search
    description: Search Gmail messages using text, time range, sender/recipient, labels, unread status, attachment filters, and pagination.
    handler: actions:search
```

Action code should load credentials from `ProviderSettings` by `owner_email` and provider name. Do not put access tokens in the manifest form.

## Repeatable Skill Example

Use repeatable skills when the same base skill can be installed multiple times with different identity config.

Example from `agent_invocation`:

```yaml
id: agent_invocation
namespace: core.automation
name: Invoke Agent
repeatable: true
repeatable_identity_fields: [target_agent_id]
form:
  - input_type: select
    name: target_agent_id
    label: Agent
    options_source:
      type: agents
  - input_type: text_area
    name: usage_description
    label: When should this agent be invoked?
    attr:
      expose_to_runtime: "true"
      usage_context_label: "Use when"
actions:
  - name: invoke
    handler: actions:invoke
```

This lets a user install "Invoke Agent" for different target agents as separate installed skill instances.

## Automation Action Example

An action intended for automations should include `action_form` so users do not need to type raw JSON.

Example from `send_email`:

```yaml
actions:
  - name: send
    description: Send an email to the configured recipients and return delivery status.
    input_schema:
      type: object
      required: [subject, body]
      properties:
        subject:
          type: string
          description: Email subject.
        body:
          type: string
          description: Trusted HTML body to render inside the default email template.
    action_form:
      form_name: Send Email
      submit_path: ""
      form_inputs:
        - input_type: text
          name: subject
          label: Subject
          attr:
            smart_values: "true"
        - input_type: text_area
          name: body
          label: Body
          attr:
            rows: "10"
            smart_values: "true"
    handler: actions:send
```

## Agent-Only Action Example

Set action-level automation to disabled when the action only makes sense in an agent conversation.

Example from `scheduler`:

```yaml
actions:
  - name: create_or_update
    description: Create a new schedule for this agent and conversation, or update an existing schedule by schedule_id.
    automation:
      enabled: false
    handler: actions:create_or_update
```

The skill can still be installed and used by agents. It will not appear as an automation action.

## Lifecycle Hook Example

Use lifecycle hooks to clean up external resources when the skill or automation action is deleted.

Manifest:

```yaml
actions:
  - name: schedule_automation
    lifecycle:
      delete:
        handler: lifecycle.schedule_automation:on_delete
    handler: actions:schedule_automation
```

Implementation:

```python
from src.skills.lifecycle import SkillLifecycleContext


async def on_delete(context: SkillLifecycleContext) -> None:
    automation_id = context.metadata.get("automation_id")
    node_id = context.metadata.get("automation_node_id")
    # Delete external resources owned by this automation action node.
```

Lifecycle hooks are best-effort. They should log and fail gracefully because the delete operation is not blocked by hook failure.

## Skill-Owned Router Example

Manifest:

```yaml
api_router: router:router
```

Skill folder:

```text
src/skills/my_skill/router.py
```

Router:

```python
from fastapi import APIRouter

router = APIRouter()


@router.get("/status")
async def status() -> dict[str, str]:
    return {"status": "ok"}
```

Mounted path:

```text
GET /skills/my_skill/status
```

Use a router only for HTTP resources. Do not add one for ordinary skill actions.

## Handler Resolution

The registry resolves handler strings in two forms.

Relative:

```yaml
handler: actions:search
```

Resolves to:

```text
src.skills.<skill_folder>.actions.search
```

Fully qualified:

```yaml
handler: src.skills.google_mail.actions:search
```

Prefer relative handlers inside a skill package.

## Runtime Context

Action handlers receive:

```python
arguments: dict[str, Any]
config: dict[str, Any]
context: dict[str, Any]
```

Common context keys:

- `agent_id`
- `owner_email`
- `actor_email`
- `actor_id`
- `conversation_id`

Automation executions may provide automation-related metadata depending on the runtime path. Do not assume every context key is present unless that action is only valid in that runtime.

## Authoring Checklist

Before adding a skill:

- Choose a stable `id`.
- Pick a useful `namespace`.
- Write a short `description`.
- Write `system_prompt` guidance with examples if the agent may misuse the skill.
- Add install `form` fields for stable configuration.
- Mark optional install fields with `attr.optional: "true"`.
- Mark secrets with `attr.secret: "true"`.
- Use `requires_oauth`, `oauth_provider_name`, and `connectors` for external accounts.
- Add one action per distinct operation.
- Add `input_schema.required` for mandatory arguments.
- Add an `action_form` for any action exposed to automations.
- Disable automation at skill or action level when the behavior is agent-only.
- Add lifecycle hooks when the skill creates external resources that need cleanup.
- Validate arguments in `models.py`; do not rely only on manifest schema.
- Add tests for registry load, install validation, and action behavior.

## Common Mistakes

- Using HTML input types such as `email` or `textarea` as `input_type`. Use `text` with `attr.type: "email"` or `text_area`.
- Forgetting `action_form` for automation-facing actions.
- Putting action arguments in install `form`.
- Putting install configuration in action `input_schema`.
- Renaming `id`, action names, or form field names after users have installed the skill.
- Marking a secret as optional but not `secret`.
- Relying only on prompt instructions instead of validating in action code.
- Exposing an action to automations when it depends on current conversation context.
- Adding global router code for behavior that belongs in `api_router`.
