# Low Level Design: Agent2Agent Public Discovery

Date: 2026-08-10  
Status: Draft  
Owner: InnomightLabs API / SPA

## Summary

Add an Agent2Agent (A2A) public sharing mode for InnomightLabs agents. A user can opt an agent into public A2A discovery, then external agents can discover it through the InnomightLabs registry endpoint and fetch an individual Agent Card for each listed agent before invoking it through A2A-compatible endpoints.

The implementation should target only A2A `1.0.0` as published at `https://a2a-protocol.org/latest/specification/`. Because this API host publishes multiple user-owned agents, do not use `/.well-known/agent-card.json` as the generic discovery source for all agents. Treat `/a2a/agents` as an InnomightLabs custom registry/catalog endpoint that returns links to individual Agent Cards. Do not add legacy `/.well-known/agent.json` compatibility in v1.

Public sharing must not publish internal prompts, provider API keys, OAuth tokens, installed skill secrets, or user-owned credentials. The public Agent Card is a capability and routing document only.

## External Standard Notes

Primary sources:

- A2A protocol specification: `https://a2a-protocol.org/latest/specification/`
- A2A project repository: `https://github.com/a2aproject/A2A`
- Google developer protocol overview: `https://developers.googleblog.com/en/developers-guide-to-ai-agent-protocols/`

Relevant requirements and design implications:

- A2A is designed for interoperable agent discovery, modality negotiation, task management, and secure exchange between opaque agent systems.
- A2A Servers publish Agent Cards for discovery. The current well-known path is `https://{server_domain}/.well-known/agent-card.json` for a server/agent that can be represented by one Agent Card.
- A2A discovery guidance also permits curated registries/catalogs, but it does not standardize a registry API shape or path. `/a2a/agents` is therefore an InnomightLabs registry endpoint, not a core A2A path.
- The current spec declares protocol operations independently of binding, then maps HTTP+JSON paths such as:
  - `POST /message:send`
  - `POST /message:stream`
  - `GET /tasks/{id}`
  - `GET /tasks`
  - `POST /tasks/{id}:cancel`
  - `POST /tasks/{id}:subscribe`
- A2A authentication is handled at the HTTP transport layer. The public Agent Card declares `securitySchemes` and `security`; credentials are obtained out of band.
- Production A2A endpoints should use HTTPS and should enforce input validation, authorization scoping, rate limits, and resource limits.
- The public registry and public Agent Cards should not include secrets. Extended Agent Cards can expose more detail only after authentication, via the spec's authenticated extended-card operation.

## Current Architecture Fit

Existing code to reuse:

- Agents:
  - `api/src/agents/models.py`
  - `api/src/agents/repository.py`
  - `api/src/agents/router.py`
- API key auth:
  - `api/src/apikeys/models.py`
  - `api/src/apikeys/repository.py`
  - `api/src/widget/middleware.py`
- Runtime invocation:
  - `api/src/agents/architectures/__init__.py`
  - `api/src/llm/events.py`
  - `api/src/conversations/models.py`
  - `api/src/conversations/repository.py`
- Existing public marketplace reference:
  - `api/src/agent_marketplace/*`
- App wiring and auth middleware:
  - `api/main.py`
  - `api/src/auth/middleware.py`

The existing agent API key is currently a bearer-like key (`pk_live_...`) looked up by GSI2 and scoped to one agent. It has active state, origin restrictions, request counts, and last-used timestamps. For v1 A2A, reuse this API key as the A2A client credential because the product request explicitly says the auth mechanism should be the same key generated per agent.

Important limitation: the current API key is not a true client id plus secret pair. It is a single shared secret with a public-looking name. The implementation should expose it to A2A clients as an HTTP bearer API key scheme. A later hardening migration can add a non-secret `client_id` plus hashed `client_secret` while keeping existing API keys backward compatible.

## User Experience

On the agent settings/detail surface:

- Add an `Agent2Agent` sharing section.
- Add a toggle: `Share in Agent2Agent discovery`.
- When enabled, show:
  - Public registry URL: `{API_BASE_URL}/a2a/agents`
  - Public Agent Card URL: `{API_BASE_URL}/a2a/agents/{agent_id}/card`
  - A2A service URL: `{API_BASE_URL}/a2a/agents/{agent_id}`
  - Required credential: active API key for that agent
  - Button/link to create or manage API keys if none exists
- Use existing agent fields for public metadata:
  - `agent_name` becomes the public Agent Card `name`.
  - `agent_description` becomes the public Agent Card `description`.
  - `agent_id` drives the agent-specific service URL.
  - Supported input/output modes are initially fixed to `text/plain`.

The toggle is a public publishing action. It should explain that the card is discoverable but invocation still requires an active agent key.

## Scope

Implement v1 in two layers:

1. Discovery:
   - Opt-in persistence.
   - Custom public registry endpoint returning enabled agent summaries.
   - Registry entries linking to individual public Agent Cards.
   - Agent-scoped Agent Cards built from existing agent fields.

2. Invocation:
   - Authenticated A2A JSON-RPC endpoint for one agent.
   - Basic task persistence for A2A task status/history.
   - Mapping from InnomightLabs SSE events to A2A messages, task status updates, and final task state.

Defer:

- Push notifications.
- File parts.
- Agent Card signing.
- gRPC binding.
- OAuth2 dynamic client registration.
- Public internet directory beyond this API's registry endpoint.

## Data Model

Extend `Agent` with a single public A2A enablement field in `api/src/agents/models.py`.

```python
class Agent(BaseModel):
    # existing fields...
    is_agent2agent_enabled: bool = False
```

Add this to `to_dynamo_item`, `from_dynamo_item`, and `AgentResponse`. Keep the default backward compatible for existing rows.

Do not duplicate existing agent metadata into A2A-specific fields. The Agent Card should be derived at response time from the current `Agent` object:

- `agent_name` -> Agent Card `name`
- `agent_description` -> Agent Card `description`
- `agent_id` -> Agent Card service URL
- `agent_provider` and `agent_model` stay internal and are not published unless a future version explicitly exposes safe capability metadata.

V1 can discover enabled agents by adding a repository method that scans existing Agent rows and filters `is_agent2agent_enabled = true`. This keeps the data model simple and avoids new DynamoDB item types while the feature proves usage. If A2A discovery volume grows, add a GSI on the same Agent row later; do not add duplicate pointer rows.

## A2A Task Model

Add a small A2A module:

- `api/src/a2a/models.py`
- `api/src/a2a/repository.py`
- `api/src/a2a/service.py`
- `api/src/a2a/router.py`
- `api/src/a2a/auth.py`

Persist tasks separately from normal dashboard conversations:

```python
from enum import Enum


class A2ATaskState(str, Enum):
    SUBMITTED = "TASK_STATE_SUBMITTED"
    WORKING = "TASK_STATE_WORKING"
    INPUT_REQUIRED = "TASK_STATE_INPUT_REQUIRED"
    COMPLETED = "TASK_STATE_COMPLETED"
    FAILED = "TASK_STATE_FAILED"
    CANCELED = "TASK_STATE_CANCELED"
    REJECTED = "TASK_STATE_REJECTED"


class A2AMessageRole(str, Enum):
    USER = "ROLE_USER"
    AGENT = "ROLE_AGENT"


class A2ATask(BaseModel):
    task_id: str = Field(default_factory=lambda: str(uuid4()))
    context_id: str
    agent_id: str
    owner_email: str
    client_key_id: str
    conversation_id: str
    state: A2ATaskState
    history: list[dict[str, Any]] = Field(default_factory=list)
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime
    ttl: int | None = None
```

Use enums for all protocol-controlled values, including task state, message role, part kind, and unsupported-operation error codes. This keeps request parsing and response generation type-safe while still serializing the exact A2A `1.0.0` strings.

DynamoDB keys:

```text
PK = A2A#Agent#{agent_id}
SK = Task#{task_id}
GSI2PK = A2ATask#{task_id}
GSI2SK = Agent#{agent_id}
```

`context_id` maps a remote client session to a private owner-side conversation. If the request has no context, generate one. Create conversations with IDs such as:

```text
a2a-{agent_id}-{sha256(client_key_id + context_id)[:16]}
```

The conversation `created_by` is the agent owner email, not the remote caller. Use `actor_id = "a2a:{client_key_id}"` and `actor_email = owner_email` unless the architecture requires a real email. Do not store remote client secrets in messages/history.

## Discovery And Agent Card Shape

### Registry Endpoint

`GET /a2a/agents` is the public InnomightLabs A2A registry. It is a custom catalog endpoint, not a standardized A2A operation. A2A-compatible clients can use it when explicitly configured with this registry URL.

The registry returns public entries for existing agents that have A2A enabled. Each item must include an `agentCardUrl` and an embedded `agentCard`. Clients can use the embedded card immediately, then fetch `agentCardUrl` when they need a fresh copy. They should not guess card paths.

Example:

```json
{
  "items": [
    {
      "id": "agent_123",
      "name": "SEO Research Agent",
      "description": "Researches search intent and drafts content briefs.",
      "agentCardUrl": "https://api.example.com/a2a/agents/agent_123/card",
      "agentCard": {
        "name": "SEO Research Agent",
        "description": "Researches search intent and drafts content briefs.",
        "supportedInterfaces": [
          {
            "url": "https://api.example.com/a2a/agents/agent_123",
            "protocolBinding": "JSONRPC",
            "protocolVersion": "1.0"
          }
        ],
        "version": "1.0.0",
        "capabilities": {
          "streaming": false,
          "pushNotifications": false,
          "extendedAgentCard": false
        },
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": []
      }
    }
  ]
}
```

Field rules:

- `id`: stable agent identifier.
- `name`: sanitized public name.
- `description`: sanitized public description.
- `agentCardUrl`: absolute URL for the individual Agent Card.
- `agentCard`: embedded scoped Agent Card for this registry row.
- `nextCursor`: optional cursor for pagination, omitted when there is no next page.

The embedded `agentCard` and the fetched `agentCardUrl` response must be produced by the same builder. If they ever differ, clients must treat the freshly fetched Agent Card as authoritative. Clients must read the callable A2A interface URL from `agentCard.supportedInterfaces`; the registry does not expose a separate `serviceUrl`.

### Agent-Scoped Card

`GET /a2a/agents/{agent_id}/card` returns the public Agent Card for one A2A-enabled agent. This card is the protocol contract for the selected agent.

Example:

```json
{
  "name": "SEO Research Agent",
  "description": "Researches search intent and drafts content briefs.",
  "supportedInterfaces": [
    {
      "url": "https://api.example.com/a2a/agents/agent_123",
      "protocolBinding": "JSONRPC",
      "protocolVersion": "1.0"
    }
  ],
  "provider": {
    "organization": "InnomightLabs",
    "url": "https://innomightlabs.com"
  },
  "version": "1.0.0",
  "capabilities": {
    "streaming": false,
    "pushNotifications": false,
    "extendedAgentCard": false
  },
  "defaultInputModes": ["text/plain"],
  "defaultOutputModes": ["text/plain"],
  "skills": [
    {
      "id": "chat",
      "name": "Chat With Agent",
      "description": "Send a task or question to this agent.",
      "tags": ["text"]
    }
  ]
}
```

The card builder must sanitize values:

- `name`: `agent_name`, trimmed, max 100 chars.
- `description`: `agent_description`, max 1000 chars.
- Never expose `agent_persona`.
- Never expose provider API key, OAuth provider settings, installed skill configs, or secret fields.

### Root Well-Known Card

Do not rely on `/.well-known/agent-card.json` for multi-agent discovery in v1. A generic well-known Agent Card can represent only one callable A2A server/agent cleanly. Since InnomightLabs exposes many user-owned agents on one host, the public registry URL must be documented and configured explicitly.

If a root well-known card is kept for compatibility or future use, it must not advertise unimplemented A2A interfaces. In particular, do not advertise `HTTP+JSON` at `https://api.example.com/a2a` unless `POST /a2a/message:send` and the related standard HTTP+JSON paths actually work. If `/a2a` is not a callable A2A server, either remove the root card or return a card that does not claim unsupported interfaces.

## API Contract

### Dashboard Authenticated Endpoints

Add to `api/src/agents/router.py` or a small `api/src/a2a/admin_router.py` mounted under `/agents`.

```http
GET /agents/{agent_id}/a2a-sharing
```

Returns current sharing metadata.

```http
PUT /agents/{agent_id}/a2a-sharing
```

Request:

```json
{
  "enabled": true
}
```

Behavior:

- Requires dashboard JWT and ownership.
- Idempotent.
- If enabling, require at least one active API key for the agent or return `400` with a clear message.
- Save `is_agent2agent_enabled` on the Agent row.
- If disabling, set `is_agent2agent_enabled = false`.
- Keep the endpoint shape flexible enough to add plan-gating or allowlisted-client settings later, but v1 makes the feature available to all users.

### Public Discovery Endpoints

Add to `api/src/a2a/router.py`. These must bypass dashboard auth.

```http
GET /a2a/agents?query=&limit=20&cursor=
GET /a2a/agents/{agent_id}/card
```

`/a2a/agents` returns compact summaries of existing agents that have A2A enabled. This is a custom InnomightLabs registry, not a separate persisted registry:

```json
{
  "items": [
    {
      "id": "agent_123",
      "name": "SEO Research Agent",
      "description": "Researches search intent and drafts content briefs.",
      "agentCardUrl": "https://api.example.com/a2a/agents/agent_123/card",
      "agentCard": {
        "name": "SEO Research Agent",
        "description": "Researches search intent and drafts content briefs.",
        "supportedInterfaces": [
          {
            "url": "https://api.example.com/a2a/agents/agent_123",
            "protocolBinding": "JSONRPC",
            "protocolVersion": "1.0"
          }
        ],
        "version": "1.0.0",
        "capabilities": {
          "streaming": false,
          "pushNotifications": false,
          "extendedAgentCard": false
        },
        "defaultInputModes": ["text/plain"],
        "defaultOutputModes": ["text/plain"],
        "skills": []
      }
    }
  ]
}
```

`/a2a/agents/{agent_id}/card` returns an agent-scoped Agent Card for clients that discovered a specific agent through the registry. It is not a well-known URL and it should still be built from the same Agent row.

### A2A Invocation Endpoints

Use the JSON-RPC binding at the agent service URL:

```http
POST /a2a/agents/{agent_id}
```

Initial support:

- JSON-RPC `SendMessage`: accepts text parts, runs the existing agent non-streamingly by collecting stream chunks, returns a completed or failed `Task`.
- JSON-RPC `GetTask`: returns persisted task if visible to the authenticated key.
- JSON-RPC `ListTasks`: lists tasks for this `agent_id` and authenticated `client_key_id`.
- JSON-RPC `CancelTask` and `SubscribeToTask`: return unsupported-operation errors until cancellation and durable stream resubscription are implemented.

Content types:

- Accept `application/a2a+json` and `application/json`.
- Return `application/a2a+json` for non-stream responses.
- Do not advertise HTTP+JSON in Agent Cards until standard HTTP+JSON operation routes are implemented.

## Authentication

Do not use `WidgetAuthMiddleware` for A2A because it only applies to `/widget` and expects `X-API-Key`. Add an A2A dependency:

```python
def get_a2a_client(
    request: Request,
    agent_id: str,
    api_key_repo: ApiKeyRepository = Depends(get_api_key_repository),
) -> AgentApiKey:
    credential = bearer_token(request.headers.get("Authorization"))
    if not credential:
        credential = request.headers.get("X-API-Key")
    api_key = api_key_repo.find_by_public_key(credential)
    if not api_key or not api_key.is_active or api_key.agent_id != agent_id:
        raise HTTPException(status_code=401, detail="Invalid A2A credential")
    api_key_repo.increment_request_count(api_key.agent_id, api_key.key_id)
    return api_key
```

Authorization rules:

- The target agent must have `is_agent2agent_enabled = true`.
- The supplied key must be active and belong to the target agent.
- Optional origin checks can be enforced for browser-originated requests, but A2A server-to-server calls often have no `Origin`. Do not reject missing `Origin` for A2A.
- Add rate limits keyed by `a2a:{agent_id}:{key_id}` using the existing rate-limit middleware/repository patterns if available.

Security scheme in Agent Cards:

- Declare `apiKey` in `Authorization` header with bearer format in the description.
- Do not publish the key value in the Agent Card.

Future hardening:

- Add `client_id` to `AgentApiKey` and store only a hash of a generated `client_secret`.
- Support `Authorization: Basic base64(client_id:client_secret)` or OAuth2 client credentials.
- Keep existing API keys backward compatible for embedded widgets and A2A clients.

## Invocation Mapping

### Request Parsing

Support the A2A JSON-RPC `SendMessage` shape:

```json
{
  "jsonrpc": "2.0",
  "id": "request-uuid",
  "method": "SendMessage",
  "params": {
    "message": {
      "messageId": "msg-uuid",
      "role": "ROLE_USER",
      "parts": [{"text": "Hello"}],
      "taskId": "optional-existing-task-id",
      "contextId": "optional-context-id"
    },
    "configuration": {
      "acceptedOutputModes": ["text/plain"]
    }
  }
}
```

Validation:

- Only `ROLE_USER` accepted from clients.
- Only text parts accepted in v1.
- Reject unsupported media types with a protocol error.
- Enforce max input length and max parts.
- Enforce accepted output modes containing `text/plain` if provided.

### Existing Runtime Call

For each request:

1. Load public-enabled agent by `agent_id`.
2. Validate API key belongs to the agent.
3. Resolve or create owner conversation for `context_id`.
4. Build prompt from text parts.
5. Call `get_agent_architecture(agent.agent_architecture).handle_message(...)`.
6. Translate `SSEEvent` values:
   - `LIFECYCLE_NOTIFICATION` -> `TaskStatusUpdateEvent` with `TASK_STATE_WORKING`.
   - `AGENT_RESPONSE_TO_USER` chunks -> append to final text buffer; optionally stream artifact/message updates.
   - `UI_FORM_RENDER` -> `TASK_STATE_INPUT_REQUIRED` with a data part describing the form.
   - `STREAM_COMPLETE` -> `TASK_STATE_COMPLETED`.
   - `ERROR` -> `TASK_STATE_FAILED`.
7. Persist final task state and history.

### A2A Response Shape

Use Pydantic models for A2A response objects instead of ad hoc dictionaries. Keep the model namespace local to `src/a2a` to avoid colliding with existing `SendMessageRequest` in `agents/router.py`.

Example completed task response:

```json
{
  "task": {
    "id": "task-uuid",
    "contextId": "ctx-uuid",
    "status": {
      "state": "TASK_STATE_COMPLETED",
      "message": {
        "role": "ROLE_AGENT",
        "parts": [{"text": "Hello from the agent."}]
      }
    },
    "history": [
      {
        "role": "ROLE_USER",
        "parts": [{"text": "Hello"}]
      }
    ]
  }
}
```

Do not document streaming support until `message/stream` or an equivalent A2A-compatible streaming operation is implemented and advertised in the scoped Agent Card.

## Middleware Changes

Update `api/src/auth/middleware.py`:

- Add public prefixes:
  - `/a2a/`

The `/a2a/` prefix handles its own credential validation. It should be skipped by dashboard JWT middleware the same way `/widget` is skipped.

Update `api/main.py`:

- Include `a2a_router` before generic routes.
- No changes to `WidgetAuthMiddleware`; it only applies to `/widget`.

## Repository Methods

Add to `AgentRepository`:

```python
def list_agent2agent_enabled(self, *, limit: int, cursor: str | None = None) -> tuple[list[Agent], str | None]:
    # V1: scan Agent rows and filter is_agent2agent_enabled.
    # Future: replace with a GSI on the Agent row if discovery volume requires it.
```

For known `agent_id` requests, avoid public unauthenticated lookup when possible:

- For invocation, validate the API key first and use `api_key.created_by` plus `api_key.agent_id` to load the target agent with `find_agent_by_id(...)`.
- For `/a2a/agents`, use `list_agent2agent_enabled(...)` and build response data from the current Agent rows.
- Do not add separate registry or pointer items in v1.

Methods:

```python
def set_a2a_sharing(self, agent: Agent) -> Agent
def list_agent2agent_enabled(self, *, limit: int, cursor: str | None = None) -> tuple[list[Agent], str | None]
```

## SPA Changes

Likely files:

- `spa/src/pages/dashboard/AgentDetail.tsx` or current agent settings surface.
- API client module for agents.
- Existing schema form components if the settings surface is schema-driven.

Add:

- Sharing toggle.
- Read-only URLs.
- Existing agent name and description edit entrypoints for public card metadata.
- Key presence warning and link to API key management.

Use existing dashboard styling and form patterns. This is an operational settings panel, not a marketing view.

## Testing Plan

Backend tests:

- `api/tests/test_agents_repository.py`
  - saves default A2A fields as disabled.
  - enables sharing by setting `is_agent2agent_enabled = true`.
  - disables sharing by setting `is_agent2agent_enabled = false`.
  - lists only A2A-enabled agents.

- `api/tests/test_agents_router.py`
  - authenticated owner can enable/disable A2A sharing.
  - non-owner cannot update sharing.
  - enabling without active API key returns `400`.

- `api/tests/test_a2a_discovery.py`
  - registry endpoint is public.
  - registry lists only agents with `is_agent2agent_enabled = true`.
  - registry entries include `agentCardUrl` and embedded `agentCard`.
  - agent-scoped `/a2a/agents/{agent_id}/card` returns `404` for disabled agents.
  - agent-scoped card returns sanitized data for enabled agents.
  - agent-scoped card advertises only implemented bindings, initially `JSONRPC`.
  - card does not include `agent_persona`, provider credentials, or installed skill secrets.

- `api/tests/test_a2a_auth.py`
  - missing credential returns `401`.
  - wrong agent key returns `401`.
  - inactive key returns `401`.
  - valid key authorizes invocation.

- `api/tests/test_a2a_invocation.py`
  - JSON-RPC `SendMessage` accepts text and returns completed task.
  - unsupported file/data parts return protocol error.
  - unsupported JSON-RPC methods return protocol errors.
  - task lookup is scoped to the authenticated key.

Run:

```bash
cd api
uv run pytest -v
```

## Rollout Plan

1. Add backend model/repository fields and tests.
2. Add dashboard sharing endpoints.
3. Add public registry and agent-card builders/routes.
4. Add A2A auth dependency.
5. Add JSON-RPC `SendMessage` with text-only invocation.
6. Add JSON-RPC task lookup/list methods.
7. Add SPA settings UI.
8. Enable in one non-production environment and verify:
   - `/a2a/agents`
   - `/a2a/agents/{agent_id}/card`
   - JSON-RPC `SendMessage` at `/a2a/agents/{agent_id}`
9. Add API documentation examples.

## Open Questions

- Should `/a2a/agents` stay unauthenticated long term, or should private/team registries require credentials?
- What request and task retention limits should apply per API key?
- Should future client id/secret credentials be introduced as a separate API key mode, or should existing API keys evolve in place?

## Recommended V1 Decisions

- Use the current A2A `1.0.0` shape for individual Agent Cards.
- Make `/a2a/agents` the documented InnomightLabs registry endpoint.
- Make `/a2a/agents/{agent_id}/card` the authoritative Agent Card URL for listed agents.
- Do not advertise unimplemented HTTP+JSON bindings.
- Make A2A sharing available to all users in v1; keep the service boundary flexible enough for future plan or policy gates.
- Rename user-facing "widget keys" to "API keys".
- Treat the existing API key as a bearer API key, not a true client id/secret pair.
- Keep v1 text-only.
- Do not expose installed skills individually unless there is a safe, explicit public description for each skill.
- Store A2A tasks with TTL, for example 30 days, to avoid unbounded growth.
