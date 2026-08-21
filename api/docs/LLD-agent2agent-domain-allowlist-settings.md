# Low Level Design: Agent2Agent Domain Allowlist Settings

Date: 2026-08-20  
Status: Draft  
Owner: InnomightLabs API / SPA

## Summary

Add a user-level Agent2Agent settings area where users can manage allowed A2A registry/service domains. The `agent2agent_client` skill should validate configured registry URLs against this allowlist before discovery or invocation, while still allowing localhost for the phase-one rollout and local testing.

The goal is to make outbound A2A trust explicit at account level instead of hardcoding production URL rules inside the skill. Users can opt into arbitrary external registries, but the system should require those registries to be present in their A2A allowlist.

## Current Issue

The current `agent2agent_client` phase-one implementation originally rejected `http://localhost` outside local development. That blocks the exact local testing flow we need:

```text
http://localhost:1455/.well-known/agent-card.json
```

We removed that hardcoded production restriction. The right long-term control is not environment-based localhost blocking inside the skill. It is user-owned allowlisting:

- The user explicitly adds `localhost:1455` or `api.innomightlabs.com`.
- Skill install forms and runtime actions validate registry URLs against the user’s allowlist.
- Unsupported or untrusted domains produce actionable validation messages.

## Current Architecture Fit

Relevant existing patterns:

- Settings domain:
  - `api/src/settings/router.py`
  - `api/src/settings/models.py`
  - `api/src/settings/repository.py`
  - `api/src/settings/schemas.py`
- Schema-driven settings forms:
  - `api/src/form_models.py`
  - `api/src/form_validation.py`
  - `spa/src/components/forms/SchemaForm.tsx`
  - `spa/src/pages/dashboard/Settings.tsx`
- Skill runtime:
  - `api/src/skills/agent2agent_client/models.py`
  - `api/src/skills/agent2agent_client/actions.py`
  - `api/src/skills/service.py`
- Existing account-level settings reference:
  - `api/src/smart_suggestions/*`

Do not put this in provider settings. A2A domain trust is not an LLM provider credential. It should be a separate user-scoped settings record.

## Product Behavior

Settings page adds an `Agent2Agent` tab.

In that tab the user can:

- View allowed A2A domains/origins.
- Add an origin such as:
  - `http://localhost:1455`
  - `https://api.innomightlabs.com`
  - `https://partner.example.com`
- Optionally add a note/label.
- Remove an origin.
- Validate a registry URL before saving or installing a skill.

When installing the `Agent2Agent Client` skill:

- The existing install form still accepts one or more registry URLs.
- The backend validates each configured registry URL against the user’s A2A allowlist.
- If the URL is not allowed, installation fails with a clear message:

```text
Agent2Agent registry host is not allowlisted: https://partner.example.com.
Add it under Settings > Agent2Agent before installing this skill.
```

When the skill runs:

- `discover_agents`, `get_agent_card`, and `send_message` validate the target registry/card/service URL against the current user allowlist.
- This avoids stale trust if a user removes a domain after installing the skill.
- `localhost` is allowed only when the user explicitly allowlists it. It is not automatically trusted by environment.

## Trust Model

Allowlist entries are user scoped, not global.

Rules:

- Match by normalized origin: `scheme://host[:port]`.
- Preserve scheme because `http://localhost:1455` and `https://localhost:1455` are different origins.
- Preserve port because local testing commonly uses different API ports.
- Normalize host case and remove trailing slash.
- Do not allow path-specific trust in v1. Registry path details belong in skill install config.
- Do not store credentials in allowlist settings.

Default behavior:

- New users start with an empty allowlist.
- For usability, the SPA can offer a one-click “Add localhost test registry” row when `window.location.hostname` is `localhost` or `127.0.0.1`.
- Existing installed `agent2agent_client` skills must use allowlisted origins before outbound calls continue to work.

## Data Model

Add `api/src/settings/agent2agent_models.py`.

```python
class Agent2AgentAllowedOrigin(BaseModel):
    origin: str
    label: str | None = None
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class Agent2AgentSettings(BaseModel):
    user_email: str
    allowed_origins: list[Agent2AgentAllowedOrigin] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    updated_at: datetime | None = None

    @property
    def pk(self) -> str:
        return f"User#{self.user_email}"

    @property
    def sk(self) -> str:
        return "Agent2AgentSettings"
```

DynamoDB item:

```json
{
  "pk": "User#user@example.com",
  "sk": "Agent2AgentSettings",
  "entity_type": "Agent2AgentSettings",
  "user_email": "user@example.com",
  "allowed_origins": [
    {
      "origin": "http://localhost:1455",
      "label": "Local API"
    }
  ],
  "created_at": "...",
  "updated_at": "..."
}
```

Add `api/src/settings/agent2agent_repository.py`:

```python
class Agent2AgentSettingsRepository:
    def find_by_user(self, user_email: str) -> Agent2AgentSettings | None: ...
    def save(self, settings: Agent2AgentSettings) -> Agent2AgentSettings: ...
```

No GSI is needed because all access is by authenticated user.

## URL Normalization

Add `api/src/settings/agent2agent_url_policy.py`.

Responsibilities:

- Normalize arbitrary registry/service/card URLs to origin.
- Validate allowed schemes.
- Validate host exists.
- Optionally reject unsupported schemes.
- Compare URL origins to allowlist.

```python
class A2AUrlPolicy:
    def normalize_origin(self, raw_url: str) -> str: ...
    def assert_allowed(self, raw_url: str, settings: Agent2AgentSettings) -> None: ...
```

Phase-one schemes:

- Allow `http` and `https`.
- Do not block localhost/private IPs if the origin is user allowlisted.

Future hardening can add optional organization-level policies:

- block private IP ranges by default
- require HTTPS for non-localhost origins
- superuser/global allowlists
- audit logs for external calls

## API Contract

Add routes to `api/src/settings/router.py` or a focused subrouter imported there.

```http
GET /settings/agent2agent
```

Response:

```json
{
  "allowed_origins": [
    {
      "origin": "http://localhost:1455",
      "label": "Local API",
      "created_at": "..."
    }
  ],
  "created_at": "...",
  "updated_at": "..."
}
```

```http
GET /settings/agent2agent/schema
```

Returns a `Form` that `SchemaForm` can render:

```python
Form(
    form_name="Agent2Agent Domain Allowlist",
    submit_path="/settings/agent2agent",
    form_inputs=[
        FormInput(
            input_type=FormInputType.KEY_VALUE,
            name="allowed_origins",
            label="Allowed A2A Origins",
            attr={
                "key_placeholder": "http://localhost:1455",
                "value_placeholder": "Local API",
                "add_label": "Add origin",
                "empty_text": "No A2A origins allowlisted.",
                "validation_endpoint": "/settings/agent2agent/validate-origin",
            },
        )
    ],
)
```

```http
PUT /settings/agent2agent
```

Request:

```json
{
  "allowed_origins": {
    "http://localhost:1455": "Local API",
    "https://api.innomightlabs.com": "Production InnomightLabs"
  }
}
```

Behavior:

- Requires dashboard JWT.
- Normalizes keys to origins.
- Deduplicates by origin.
- Stores labels as optional display text.
- Returns normalized settings.

```http
POST /settings/agent2agent/validate-origin
```

Request:

```json
{
  "value": "http://localhost:1455/.well-known/agent-card.json"
}
```

Response:

```json
{
  "valid": true,
  "origin": "http://localhost:1455",
  "message": "Origin is valid and allowlisted."
}
```

Failure response should use HTTP `200` with `valid=false` for form-friendly inline validation, and HTTP `400` only when the request shape itself is invalid.

```json
{
  "valid": false,
  "origin": "https://unknown.example.com",
  "message": "Origin is valid but not allowlisted. Add it under Settings > Agent2Agent."
}
```

### Form Module Integration

Add a small generic optional extension to SPA `SchemaForm` rather than making A2A bespoke:

- Read `field.attr.validation_endpoint`.
- For `text`, `text_area`, and `key_value` keys, call the endpoint on blur or before submit.
- Expected contract:

```ts
type FieldValidationRequest = {
  field_name: string;
  value: string;
  form_data?: Record<string, FormValue>;
};

type FieldValidationResponse = {
  valid: boolean;
  message?: string;
  normalized_value?: string;
  metadata?: Record<string, unknown>;
};
```

For this A2A settings release, keep SPA integration minimal:

- Settings page can call `/settings/agent2agent/validate-origin` before save.
- The form-schema `validation_endpoint` attribute is included so the generic form enhancement can use it later.

## Skill Integration

Update `api/src/skills/agent2agent_client/actions.py`.

Runtime context already includes:

```python
context = {
    "agent_id": agent_id,
    "owner_email": owner_email,
    ...
}
```

Use `owner_email` to load A2A settings and validate URLs.

```python
def _registry_config(config: dict[str, Any], context: dict[str, Any]) -> A2ARegistryConfig:
    user_email = str(context.get("owner_email") or "").strip()
    settings = Agent2AgentSettingsRepository().find_by_user(user_email)
    registry_config = A2ARegistryConfig.from_runtime_config(config)
    A2AUrlPolicy().assert_all_allowed(registry_config.registry_urls, settings)
    return registry_config
```

Validate:

- all configured registry URLs before discovery
- `agent_ref.registry_url`
- `agent_ref.card_url` if present
- `agent_ref.service_url`

This prevents a malicious or stale `agent_ref` from calling outside the allowlist.

## Skill Install Validation

Runtime validation is required, but install-time validation improves user experience.

Add an optional skill-specific install config validator hook to the skills system:

Manifest:

```yaml
config_validator: validators:validate_install_config
```

Registry/service behavior:

- After manifest form validation, if `config_validator` exists, call it with:

```python
validate_install_config(
    normalized_config: dict[str, Any],
    user_email: str,
    context: dict[str, Any] | None = None,
) -> dict[str, Any]
```

For `agent2agent_client`, the validator:

- parses `registry_urls`
- normalizes origins
- checks each origin against user A2A allowlist
- returns normalized config unchanged or raises `ValueError`

This keeps A2A-specific validation in the A2A skill package, not in the generic skills service.

If we do not want a generic hook yet, implement install-time validation directly in `SkillService.validate_install_config` as a narrow special case only for `agent2agent_client`. The hook is cleaner if we expect more skills to need account-level validation.

## SPA Changes

Settings page:

- Refactor `spa/src/pages/dashboard/Settings.tsx` into tabs:
  - Account
  - Providers
  - Agent2Agent
  - Smart Suggestions
  - Billing
  - Appearance
- Keep the current stacked cards inside their relevant tabs to avoid a full redesign.
- Add `Agent2Agent` tab with:
  - `SchemaForm` for allowlist key/value map.
  - Save button.
  - Inline validation result for each origin if implemented now.
  - Short explanatory copy:

```text
Allow registries and remote agents this account may contact through Agent2Agent skills.
```

Services:

- Add `spa/src/services/settings/Agent2AgentSettingsService.ts`.
- Export from `spa/src/services/settings/index.ts` if present.

Types:

```ts
export interface Agent2AgentAllowedOrigin {
  origin: string;
  label?: string | null;
  created_at?: string | null;
}

export interface Agent2AgentSettings {
  allowed_origins: Agent2AgentAllowedOrigin[];
  created_at?: string | null;
  updated_at?: string | null;
}
```

Skill install dialog:

- No major UI change required.
- When install fails with “not allowlisted”, show the backend error and include a link to `/dashboard/settings?tab=agent2agent`.

## Rollout

Rollout should keep the behavior simple and explicit: outbound A2A calls require an allowlisted origin. No settings record means an empty allowlist.

Recommended sequence:

1. Add settings model, repository, schema, and routes.
2. Add SPA Agent2Agent tab.
3. Allow users to save `http://localhost:1455`.
4. Add runtime allowlist validation to `agent2agent_client`.
5. Add install-time validation after runtime validation is stable.

Rules:

- Empty allowlist means no outbound A2A calls.
- User must explicitly add an origin before installing or using an A2A registry.
- The validation error should tell the user where to fix it: `Settings > Agent2Agent`.

## Testing Plan

Backend tests:

- `api/tests/test_agent2agent_settings.py`
  - default settings returns empty allowlist.
  - schema includes key/value `allowed_origins` and validation endpoint metadata.
  - saving normalizes origins and deduplicates.
  - saving accepts `http://localhost:1455`.
  - invalid schemes are rejected.
  - validation endpoint returns `valid=true` for allowlisted URL.
  - validation endpoint returns `valid=false` for valid but non-allowlisted URL.

- `api/tests/test_agent2agent_client_skill.py`
  - discovery allows registry URL when origin is allowlisted.
  - discovery blocks registry URL when origin is not allowlisted.
  - `send_message` validates service URL from decoded `agent_ref`.
  - localhost remains callable when allowlisted.

SPA tests/build:

```bash
cd spa
yarn build
```

Backend:

```bash
cd api
uv run pytest tests/test_agent2agent_settings.py tests/test_agent2agent_client_skill.py -v
uv run pytest -v
```

## Open Questions

- Should account-level allowlist be enough, or should each installed skill instance also declare which allowlisted origins it can use?
- Should labels be plain text only, or should we add environment labels such as local/staging/production?
- Should we log every outbound A2A domain call for audit visibility in a later phase?

## Recommended V1 Decision

- Add user-level A2A allowlist under Settings > Agent2Agent.
- Allow `http://localhost` and any arbitrary external origin when explicitly allowlisted.
- Enforce allowlist at runtime first; add install-time validation through a generic skill config validator hook if the implementation cost stays small.
- Treat missing A2A settings as an empty allowlist. Deny outbound A2A calls by default until the user explicitly allowlists an origin.
