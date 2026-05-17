# Skill Development Guide

Skills are self-contained integrations that can be installed on an agent and invoked by the runtime through manifest-declared actions. Keep each skill isolated: put skill-specific models, request parsing, API clients, OAuth helpers, and forms inside the skill folder unless the code is genuinely shared platform infrastructure.

## 1. Add a Folder With the Skill Name

Create a folder under `src/skills` using a stable snake_case skill id:

```text
src/skills/
  my_skill/
    __init__.py
    manifest.yml
    actions.py
    models.py
```

Use the folder name as the skill id unless there is a strong reason not to. The registry scans `src/skills/*/manifest.yml`, validates each manifest, and exposes the skill through the catalog.

## 2. Skill Anatomy

A typical skill contains:

- `manifest.yml`: required metadata, action declarations, install form fields, and OAuth flags.
- `actions.py`: action handlers called by the skill runtime.
- `models.py`: skill-local Pydantic models for credentials and action arguments.
- `forms.py`: optional helpers for complex form parsing or dynamically generated widget forms.
- `oauth.py`: optional OAuth helpers for third-party authorization flows.
- `router.py`: optional skill-owned API routes when manifest `api_router` is used.

Avoid defining Pydantic models inline in `actions.py` once a skill has more than trivial validation. Prefer `models.py` so action code stays focused on behavior.

## 3. Manifest.yml

Every skill needs a `manifest.yml`:

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
      properties:
        query:
          type: string
          description: Query text.
      required: [query]
    handler: actions:search
form:
  - input_type: text
    name: site_url
    label: WordPress Site URL
    attr:
      placeholder: https://example.com
```

Required top-level fields:

- `id`: stable skill id used in URLs, storage, and runtime execution.
- `namespace`: dotted category such as `integrations.google`.
- `name`: human-readable display name.
- `description`: short catalog description.
- `actions`: list of runtime-callable actions.

Optional top-level fields:

- `system_prompt`: instructions the agent should follow when using the skill.
- `form`: install-time configuration fields rendered by the SPA schema form.
- `requires_oauth`: set to `true` when the skill needs provider OAuth before install.
- `oauth_provider_name`: provider key used to find OAuth metadata and stored credentials.
- `api_router`: skill-owned FastAPI router path, for example `router:router`.

Action handlers use `module:function` syntax. Relative handlers resolve inside the skill folder, so `actions:search` resolves to `src.skills.<skill_folder>.actions.search`.

## 4. Actions

Action handlers receive `arguments`, installed skill `config`, and runtime `context`:

```python
from __future__ import annotations
from typing import Any
from pydantic import ValidationError
from .models import SearchRequest


def _validate_search_request(arguments: dict[str, Any]) -> SearchRequest:
    try:
        return SearchRequest.model_validate(arguments)
    except ValidationError as exc:
        raise ValueError(f"Invalid My Skill search arguments: {exc}") from exc


async def search(arguments: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> str:
    request = _validate_search_request(arguments)
    owner_email = str(context.get("owner_email") or "")
    del config

    return f"Searched for {request.query} as {owner_email}"
```

Action guidelines:

- Validate arguments with skill-local Pydantic models.
- Return compact strings or structured data that the agent can use directly.
- Raise `ValueError` for invalid user/action input.
- Raise `RuntimeError` for third-party API failures with bounded response previews.
- Keep timeouts explicit for network calls.
- Do not read credentials directly from agent config when OAuth/provider settings own them.
- Keep destructive actions explicit in the name and description, for example `delete` or `batch_delete`.

The runtime performs only lightweight required-field checks from `input_schema`; deeper validation belongs in the action model.

## 5. Models

Put skill-specific models in `models.py`:

```python
from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, StringConstraints, model_validator


class SearchRequest(BaseModel):
    query: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]
    page_size: int = 10

    @model_validator(mode="after")
    def normalize(self) -> "SearchRequest":
        self.page_size = max(1, min(50, int(self.page_size or 10)))
        return self
```

Prefer models for:

- action argument validation
- credential payloads
- normalized filter/query objects
- third-party response shapes when useful

## 6. Install Form Schema

Use manifest `form` when the skill needs user-provided configuration during activation. These fields are exposed through the install schema endpoint and rendered by the shared SPA `SchemaForm`.

Supported input types come from `src/form_models.py`:

- `text`
- `text_area`
- `password`
- `select`
- `choice`
- `file_upload`

Example:

```yaml
form:
  - input_type: text
    name: site_url
    label: Site URL
    attr:
      placeholder: https://example.com
  - input_type: password
    name: api_key
    label: API Key
    attr:
      secret: "true"
  - input_type: select
    name: mode
    label: Mode
    values: [fast, balanced, thorough]
    value: balanced
```

Form guidelines:

- Keep field names stable; they become config keys.
- Mark optional fields with `attr.optional: "true"`.
- Mark secrets with `attr.secret: "true"` so they are encrypted and omitted from plain config.
- Use `attr` for UI hints such as `placeholder`, `rows`, `type`, `accept`, and `multiple`.
- Prefer `options` when display labels differ from stored values.

The registry validates install config against the manifest form. Unsupported form input types for skill config will be rejected.

## 7. OAuth Skills

For third-party OAuth skills, do not ask the user to paste access tokens or refresh tokens. Use provider settings and OAuth routes.

Manifest example:

```yaml
requires_oauth: true
oauth_provider_name: GoogleMail
```

Then register OAuth metadata in `src/skills/oauth_providers.py`:

```python
SKILL_OAUTH_PROVIDERS = {
    "GoogleMail": SkillOAuthProvider(
        provider_name="GoogleMail",
        start_path="/auth/google-mail/start",
    ),
}
```

The catalog exposes `oauth_start_path`, and the SPA starts OAuth generically from that path. Keep the button text/UI generic; backend metadata should drive the flow.

OAuth implementation guidelines:

- Store encrypted credentials in `ProviderSettings` using the provider name.
- Include refresh token support when the provider supports it.
- Keep provider-specific OAuth helpers in the skill folder when possible, for example `src/skills/google_mail/oauth.py`.
- Use the least privilege scope that supports the skill actions.
- On uninstall, decide whether provider credentials should remain connected or be explicitly disconnected by user choice.

Runtime actions should load credentials by provider name and owner email from context, for example:

```python
repo.find_by_provider(owner_email, "GoogleMail")
```

## 8. Skill-Owned API Routes

Most skills only need manifest actions. Add a skill-owned router only when the skill needs additional HTTP endpoints.

Manifest:

```yaml
api_router: router:router
```

Router location:

```text
src/skills/my_skill/router.py
```

Keep routes under the skill boundary and avoid adding special cases to global routers unless the behavior is genuinely platform-level.

## 9. Testing Checklist

Add focused tests for each new skill:

- manifest loads through the registry
- install form validation accepts valid config and rejects invalid config
- action argument validation
- successful action behavior with mocked third-party calls
- third-party API failure behavior
- OAuth start/callback behavior when applicable
- token refresh behavior when applicable

Run:

```bash
uv run pytest -v
```

For quick syntax checks:

```bash
uv run python -m py_compile src/skills/my_skill/actions.py src/skills/my_skill/models.py
```

## 10. Development Principles

- Keep skill behavior inside the skill folder.
- Share only platform infrastructure: registry, runtime, provider settings, encryption, and form models.
- Prefer manifest/schema-driven UI over bespoke frontend changes.
- Use structured validation instead of ad hoc string parsing.
- Keep action names and descriptions precise enough for the agent to choose safely.
- Do not introduce provider-specific `if`/`else` branches in shared routers when metadata or schema can express the behavior.
