# Low Level Design: REST Template Skill

Date: 2026-06-17  
Status: Draft  
Owner: InnomightLabs API

## Summary
Add a first-party `rest_template` skill that lets agents and automations call arbitrary HTTP endpoints with two initial actions:
- `get`
- `post`

The skill should be highly flexible: each action accepts any URL, arbitrary headers as key/value pairs, optional query parameters, timeout controls, and response capture settings. The same manifest action handlers will be used by both the agent runtime and automation runner through the existing `SkillRegistry.execute_action(...)` path.

## Existing Architecture Fit
Skills are discovered from `api/src/skills/*/manifest.yml` by `SkillRegistry` and exposed to both:
- Agents through `SkillRuntimeService.handle_tool_call(...)` in `api/src/skills/service.py`.
- Automations through `AutomationRunner._execute_skill_action(...)` in `api/src/automations/runner.py`.

No new agent or automation execution surface is required. Adding the skill folder, manifest, action handlers, models, and tests is enough for the skill to appear in the catalog and automation action list.

## Naming
Use:
- Folder: `api/src/skills/rest_template/`
- Skill id: `rest_template`
- Namespace: `core.http`
- Display name: `REST Template`

This keeps it provider-neutral and avoids implying OAuth, webhooks, or one specific API.

## Files
Add:
- `api/src/skills/rest_template/__init__.py`
- `api/src/skills/rest_template/manifest.yml`
- `api/src/skills/rest_template/actions.py`
- `api/src/skills/rest_template/helper.py`
- `api/src/skills/rest_template/models.py`
- `api/tests/test_rest_template_skill_actions.py`

Use `httpx.AsyncClient` for the HTTP client. It is already a direct dependency in `api/pyproject.toml`, matches the existing skill implementations, and avoids wrapping synchronous `requests` calls in worker threads.

## Manifest Design
`api/src/skills/rest_template/manifest.yml`:

```yaml
id: rest_template
namespace: core.http
name: REST Template
description: Send flexible GET and POST HTTP requests to external APIs.
system_prompt: |
  Use this skill when the user asks to call an HTTP API endpoint.
  Always ask for confirmation before sending secrets, tokens, or credentials to a URL the user has not explicitly provided.
  Use get for read-only requests and post for requests that create, submit, or trigger work.
  Put every header in headers as key/value pairs.
  Prefer json_body for JSON payloads. Use text_body only when the endpoint expects raw text.
  Do not invent Authorization headers or API keys. If the user tells you to use a secret placeholder such as {{ api_token }},
  pass that placeholder exactly; the runtime replaces it from environment variables before sending the request.
  By default the result includes only ok, status_code, and body_preview. Set include_full_response=true only when headers,
  content type, parsed JSON, elapsed time, or other metadata are required.
actions:
  - name: get
    aliases: [http_get, send_get]
    description: Send a GET request to any URL with optional headers and query parameters.
    input_schema:
      type: object
      required: [url]
      properties:
        url:
          type: string
          description: Absolute http or https URL to request.
        headers:
          type: object
          additionalProperties:
            type: string
          description: Optional request headers as key/value pairs.
        query:
          type: object
          additionalProperties:
            type: string
          description: Optional query parameters as key/value pairs.
        timeout_seconds:
          type: integer
          description: Request timeout, clamped to a safe range.
        max_response_chars:
          type: integer
          description: Maximum response body characters to return.
        include_full_response:
          type: boolean
          description: Return response metadata, parsed JSON when available, and truncation details. Defaults to false.
    action_form:
      form_name: REST GET
      submit_path: ""
      form_inputs:
        - input_type: text
          name: url
          label: URL
          attr:
            placeholder: "https://api.example.com/items"
            smart_values: "true"
        - input_type: key_value
          name: headers
          label: Headers
          attr:
            empty_text: "No headers configured."
            key_placeholder: "Authorization"
            value_placeholder: "Bearer {{ api_token }}"
            add_label: "Add header"
            smart_values: "true"
        - input_type: key_value
          name: query
          label: Query parameters
          attr:
            empty_text: "No query parameters configured."
            key_placeholder: "page"
            value_placeholder: "1"
            add_label: "Add query parameter"
            smart_values: "true"
        - input_type: choice
          name: include_full_response
          label: Full response
          value: "false"
          values: ["true", "false"]
    handler: actions:get
  - name: post
    aliases: [http_post, send_post]
    description: Send a POST request to any URL with optional headers, query parameters, and body.
    input_schema:
      type: object
      required: [url]
      properties:
        url:
          type: string
          description: Absolute http or https URL to request.
        headers:
          type: object
          additionalProperties:
            type: string
          description: Optional request headers as key/value pairs.
        query:
          type: object
          additionalProperties:
            type: string
          description: Optional query parameters as key/value pairs.
        json_body:
          description: Optional JSON payload. Prefer this for application/json APIs.
        text_body:
          type: string
          description: Optional raw request body. Use only when JSON is not appropriate.
        timeout_seconds:
          type: integer
          description: Request timeout, clamped to a safe range.
        max_response_chars:
          type: integer
          description: Maximum response body characters to return.
        include_full_response:
          type: boolean
          description: Return response metadata, parsed JSON when available, and truncation details. Defaults to false.
    action_form:
      form_name: REST POST
      submit_path: ""
      form_inputs:
        - input_type: text
          name: url
          label: URL
          attr:
            placeholder: "https://api.example.com/items"
            smart_values: "true"
        - input_type: key_value
          name: headers
          label: Headers
          attr:
            empty_text: "No headers configured."
            key_placeholder: "Content-Type"
            value_placeholder: "application/json"
            add_label: "Add header"
            smart_values: "true"
        - input_type: key_value
          name: query
          label: Query parameters
          attr:
            empty_text: "No query parameters configured."
            key_placeholder: "dry_run"
            value_placeholder: "true"
            add_label: "Add query parameter"
            smart_values: "true"
        - input_type: text_area
          name: json_body
          label: JSON body
          attr:
            rows: "10"
            optional: "true"
            smart_values: "true"
            placeholder: "{\"name\":\"Example\"}"
        - input_type: text_area
          name: text_body
          label: Text body
          attr:
            rows: "6"
            optional: "true"
            smart_values: "true"
        - input_type: choice
          name: include_full_response
          label: Full response
          value: "false"
          values: ["true", "false"]
    handler: actions:post
```

## Request Models
`api/src/skills/rest_template/models.py` should own validation and normalization.

```python
from __future__ import annotations

import json
from typing import Any
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

from .helper import normalize_string_map


DEFAULT_TIMEOUT_SECONDS = 20
MIN_TIMEOUT_SECONDS = 1
MAX_TIMEOUT_SECONDS = 60
DEFAULT_MAX_RESPONSE_CHARS = 12000
MAX_RESPONSE_CHARS_LIMIT = 50000


class RestRequest(BaseModel):
    url: str
    headers: dict[str, Any] = Field(default_factory=dict)
    query: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS
    max_response_chars: int = DEFAULT_MAX_RESPONSE_CHARS
    include_full_response: bool = False

    @model_validator(mode="after")
    def normalize(self) -> "RestRequest":
        self.url = self.url.strip()
        parsed = urlparse(self.url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("url must be an absolute http or https URL")
        if parsed.username or parsed.password:
            raise ValueError("url must not include embedded username or password credentials")
        self.headers = normalize_string_map(self.headers, "headers")
        self.query = normalize_string_map(self.query, "query")
        self.timeout_seconds = max(MIN_TIMEOUT_SECONDS, min(MAX_TIMEOUT_SECONDS, int(self.timeout_seconds)))
        self.max_response_chars = max(1, min(MAX_RESPONSE_CHARS_LIMIT, int(self.max_response_chars)))
        return self


class RestPostRequest(RestRequest):
    json_body: Any | None = None
    text_body: str | None = None

    @model_validator(mode="after")
    def validate_body(self) -> "RestPostRequest":
        if isinstance(self.json_body, str):
            stripped = self.json_body.strip()
            if stripped:
                try:
                    self.json_body = json.loads(stripped)
                except json.JSONDecodeError as exc:
                    raise ValueError(f"json_body must be valid JSON: {exc.msg}") from exc
            else:
                self.json_body = None
        if self.json_body is not None and self.text_body:
            raise ValueError("Provide either json_body or text_body, not both")
        return self
```

`api/src/skills/rest_template/helper.py` should hold pure static helper functions:

```python
from __future__ import annotations

import os
import re
from typing import Any


PLACEHOLDER_RE = re.compile(r"{{\s*([A-Za-z_][A-Za-z0-9_]*)\s*}}")
REDACTED = "[redacted]"
SENSITIVE_HEADER_NAMES = {
    "authorization",
    "proxy-authorization",
    "cookie",
    "set-cookie",
    "x-api-key",
    "api-key",
}


def normalize_string_map(value: dict[str, Any], field_name: str) -> dict[str, str]:
    if not isinstance(value, dict):
        raise ValueError(f"{field_name} must be an object")
    normalized: dict[str, str] = {}
    for raw_key, raw_value in value.items():
        key = str(raw_key).strip()
        if not key:
            continue
        normalized[key] = "" if raw_value is None else str(raw_value)
    return normalized


def expand_env_placeholders(value: Any) -> Any:
    if isinstance(value, str):
        return PLACEHOLDER_RE.sub(_environment_value, value)
    if isinstance(value, list):
        return [expand_env_placeholders(item) for item in value]
    if isinstance(value, dict):
        return {key: expand_env_placeholders(item) for key, item in value.items()}
    return value


def _environment_value(match: re.Match[str]) -> str:
    name = match.group(1)
    if name not in os.environ:
        raise ValueError(f"Missing environment variable for REST Template placeholder: {name}")
    return os.environ[name]
```

Notes:
- Keep `headers` and `query` as plain dictionaries to preserve maximum flexibility.
- Parse `json_body` when it arrives as a string from `SchemaForm`; leave dict/list/scalar JSON values intact when agents call the action directly.
- `include_full_response` defaults to `False` to keep agent tool output compact.
- Do not store credentials in skill config for v1. Let automations use step-time values and let agents pass secret placeholders such as `{{ api_token }}` when the user instructs them to.

## Secret Placeholder Resolution
Header, query, URL, and body values may contain placeholders like `{{ api_token }}`. Before sending the request, the skill resolves those placeholders against environment variables by exact name.

Example:

```json
{
  "headers": {
    "Authorization": "Bearer {{ api_token }}"
  }
}
```

If `os.environ["api_token"]` is set, the outgoing header receives the secret value. The unresolved placeholder remains visible to the agent and automation configuration, but the actual secret is not exposed in skill prompts, action arguments, logs, or returned metadata.

Rules:
- Placeholder syntax is `{{ variable_name }}`.
- Variable names should match `[A-Za-z_][A-Za-z0-9_]*`.
- Missing environment variables should fail before the request is sent with a clear `ValueError`, for example `Missing environment variable for REST Template placeholder: api_token`.
- Placeholder expansion should happen after argument validation and before request dispatch.
- Redaction still applies after expansion.

Implementation detail: put placeholder expansion in `helper.py` so it is unit-testable independently of network calls.

## Action Handler Design
`api/src/skills/rest_template/actions.py` should expose `get(...)` and `post(...)`.

`actions.py` should stay focused on runtime handlers and HTTP dispatch:
- `_validate_get(arguments) -> RestRequest`
- `_validate_post(arguments) -> RestPostRequest`
- `_send_request(method, request) -> dict[str, Any]`

Create `api/src/skills/rest_template/helper.py` for pure static functions:
- `body_preview(text, max_chars) -> tuple[str, bool]`
- `content_type(headers) -> str`
- `redact_headers(headers) -> dict[str, str]`
- `redact_url(url) -> str`
- `normalize_string_map(value, field_name) -> dict[str, str]`
- `expand_env_placeholders(value) -> Any`
- `compact_response(response, body_preview) -> dict[str, Any]`
- `full_response(response, body_preview, body_json, truncated, elapsed_ms) -> dict[str, Any]`

Return structured data rather than a prose-only string so automations can reference response fields.

Default compact response:

```json
{
    "ok": true,
    "status_code": 200,
    "body_preview": "{\"items\":[]}"
}
```

Full response when `include_full_response=true`:

```json
{
    "ok": true,
    "method": "GET",
    "url": "https://api.example.com/items",
    "status_code": 200,
    "reason": "OK",
    "headers": {"content-type": "application/json"},
    "content_type": "application/json",
    "body_preview": "{\"items\":[]}",
    "body_json": {"items": []},
    "truncated": false,
    "elapsed_ms": 123
}
```

For non-2xx responses, do not raise. Return `ok: false`, `status_code`, and `body_preview` so automations can branch and agents can explain what happened.

```json
{
    "ok": false,
    "status_code": 401,
    "body_preview": "{\"error\":\"invalid token\"}"
}
```

For transport errors where no HTTP response exists, return `ok: false`, `status_code: null`, an empty `body_preview`, and a human-readable `error` field:
- timeout: `REST GET timed out after 20 seconds while calling https://...`
- DNS/connect: `REST GET could not connect to https://...: <short reason>`
- invalid response decoding: still return body preview; do not fail solely because JSON parsing fails.

## HTTP Client Choice
Preferred implementation:

```python
async with httpx.AsyncClient(timeout=request.timeout_seconds, follow_redirects=True) as client:
    response = await client.request(
        method,
        request.url,
        params=request.query,
        headers=request.headers,
        json=request.json_body if has_json else None,
        content=request.text_body if has_text else None,
    )
```

## Error Translation
Human-readable errors should include:
- method
- URL origin/path without query secrets
- timeout or status code
- short server response preview when available
- likely fix when obvious

Bound server response previews to 500 characters in error messages. Bound successful response bodies through `max_response_chars`.

Redact sensitive request headers from any returned metadata:
- `authorization`
- `proxy-authorization`
- `cookie`
- `set-cookie`
- `x-api-key`
- `api-key`

Do not include request body in error messages by default.

## Security and Safety
The product requirement is to allow any URL. Do not block private, internal, link-local, localhost, or metadata-service URLs.

Required v1 baseline:
- Allow only `http` and `https`.
- Reject URLs containing username/password credentials.
- Reject redirect chains that end in unsupported schemes.
- Set explicit timeout and response size limits.
- Do not log full headers or request bodies.
- Redact credentials in returned request metadata and errors.

## Automation Behavior
The existing automation runner renders smart values before skill execution:

`api/src/automations/runner.py`:

```python
arguments = self._render_smart_values(deepcopy(raw_arguments), run.context)
result = await self.skill_service.registry.execute_action(...)
```

Because the action forms mark URL, headers, query, and bodies as `smart_values: "true"`, users can build templates such as:

```json
{
  "url": "https://api.example.com/customers/{{ input.customer_id }}",
  "headers": {
    "Authorization": "Bearer {{ api_token }}"
  },
  "query": {
    "include": "subscriptions"
  }
}
```

The returned structured result will be saved in the node output under `result`, making fields such as `result.ok`, `result.status_code`, and `result.body_preview` available to downstream smart values and branching logic.

## Agent Behavior
Agents will see the skill in `load_skill` with the manifest system prompt and action schemas. The agent should:
- Use `get` for read-only API calls.
- Use `post` for submit/create/trigger calls.
- Use user-provided placeholders such as `{{ api_token }}` instead of asking the user to reveal secret values directly to the agent.
- Explain HTTP errors from `ok:false`, `status_code`, `body_preview`, and `error`.
- Request `include_full_response=true` only when the task needs response headers, parsed JSON, elapsed time, or truncation metadata.

## Tests
Add `api/tests/test_rest_template_skill_actions.py`.

Coverage:
- `get` sends URL, headers, and query params.
- `post` sends JSON body and defaults `Content-Type` only when useful.
- `post` rejects both `json_body` and `text_body`.
- URL validation rejects relative URLs and non-http schemes.
- Timeout is clamped to the configured max.
- Default response returns only `ok`, `status_code`, and `body_preview`.
- `include_full_response=true` returns metadata, `body_json` when available, and `truncated`.
- Successful JSON response returns `body_json` only when `include_full_response=true`.
- Non-JSON response returns `body_preview` and no `body_json`.
- Large response is bounded in `body_preview`; `truncated=true` is returned only when `include_full_response=true`.
- 4xx/5xx response returns `ok:false`, status code, and bounded body preview.
- Timeout/connect errors return `ok:false`, `status_code:null`, `body_preview:""`, and a human-readable `error`.
- Environment placeholders such as `{{ api_token }}` are resolved before dispatch and missing placeholders fail before dispatch.
- Sensitive headers are redacted from returned metadata.
- `SkillRegistry.execute_action(...)` can execute aliases such as `http_get`.

Also update existing catalog tests if they assert exact counts. Most current tests assert presence of specific skills, so this may not be required.

## Implementation Steps
1. Add `rest_template` skill folder and empty `__init__.py`.
2. Add manifest with `get` and `post` actions and schema-driven action forms.
3. Add Pydantic models for argument validation and normalization.
4. Add `helper.py` with pure placeholder, preview, redaction, and response-shaping helpers.
5. Add action handlers with explicit timeout, response size bounds, redaction, compact/full response modes, and human-readable transport errors.
6. Add unit tests for action behavior, helper behavior, placeholder expansion, and registry alias execution.
7. Run:

```bash
cd api
uv run pytest -v
```
