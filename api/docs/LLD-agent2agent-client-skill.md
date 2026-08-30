# Low Level Design: Agent2Agent Client Skill

Date: 2026-08-19  
Status: Draft  
Owner: InnomightLabs API / Skills

## Summary

Add an installable `agent2agent_client` skill that lets any InnomightLabs agent discover and delegate work to other A2A-compatible agents. The skill gives the reasoning agent a small generic interface:

- `discover_agents`: search configured A2A registries and Agent Cards.
- `get_agent_card`: inspect one discovered agent before delegating.
- `send_message`: send a text A2A message to a selected agent.

This keeps remote agents dynamic. We should not expose every remote agent as a static tool because that removes the main benefit of A2A discovery. The installed skill defines the trusted registry set and credentials; runtime actions discover currently available agents from those registries.

## Current Architecture Fit

Reuse existing code and patterns:

- Skill registry/runtime:
  - `api/src/skills/registry.py`
  - `api/src/skills/service.py`
  - `api/src/skills/repository.py`
  - `api/src/skills/CONTRIBUTION.md`
- Existing A2A server models:
  - `api/src/a2a/models.py`
  - `api/src/a2a/service.py`
- Existing skill examples:
  - `api/src/skills/rest_template/*` for outbound HTTP action style.
  - `api/src/skills/agent_invocation/*` for agent delegation semantics.
- Schema-driven install forms:
  - `api/src/form_models.py`
  - SPA `SchemaForm`

The official Python SDK exists as `a2a-sdk` and supports A2A protocol `1.0` clients and servers across JSON-RPC, HTTP+JSON/REST, and gRPC. For the first implementation, keep the skill dependency-light and use the SDK client behind an isolated module, with JSON-RPC as the preferred binding for InnomightLabs agents. The `client.py` boundary keeps SDK usage isolated from actions, discovery, credentials, and tests.

Create a new isolated skill package:

```text
api/src/skills/agent2agent_client/
  __init__.py
  manifest.yml
  actions.py
  client.py
  credentials.py
  discovery.py
  models.py
```

No skill-owned router is required in this phase because OAuth and browser credential collection are deferred. Runtime discovery and invocation remain manifest-declared actions.

## Product Behavior

The user installs the skill on an agent and provides one or more trusted discovery URLs. InnomightLabs multi-agent discovery uses a custom registry URL such as `https://api.innomightlabs.com/a2a/agents`; generic A2A Agent Cards can still be configured directly when the remote endpoint represents one callable agent. At runtime, the agent can:

1. Call `discover_agents` with a simple keyword.
2. Receive up to 10 matching agents from all configured registries.
3. Optionally call `get_agent_card` for a full card.
4. Call `send_message` using a selected `agent_ref` and a task prompt.

The LLM sees generic actions, not one tool per remote agent:

```text
Agent
  -> load_skill(agent2agent_client)
  -> execute_skill_action(discover_agents, { keyword: "gmail" })
  -> execute_skill_action(send_message, { agent_ref: "...", message: "..." })
```

The skill handles:

- registry URL normalization
- pagination across registries
- Agent Card fetching
- credential lookup
- secure credential collection links when a selected agent needs credentials
- pending delegation resume after credentials are saved
- A2A JSON-RPC `SendMessage`
- response trimming and safety bounds

The skill does not decide trust automatically. It returns enough metadata for the reasoning agent to choose, and the install configuration defines which registries are trusted.

## Install Configuration

Use one repeatable skill instance per registry set. This keeps the runtime prompt readable and allows different agents to have different A2A networks.

Manifest sketch:

```yaml
id: agent2agent_client
namespace: core.agent2agent
name: Agent2Agent Client
description: Discover and message A2A-compatible agents from configured registries.
repeatable: true
repeatable_identity_fields: [registry_set_name]
system_prompt: |
  Use this skill when the user asks you to delegate work to another agent or find an agent with a capability.
  Always call discover_agents before send_message unless the user or prior tool result already provided a valid agent_ref.
  Prefer agents whose skills and description directly match the keyword.
  Do not send secrets, API keys, OAuth tokens, or unrelated private conversation history to remote agents.
  When sending context, summarize only the relevant task state needed by the remote agent.
  Discovery is keyword based. Use short capability keywords such as gmail, calendar, research, finance, drive, email, scheduler, or report.
  If discover_agents returns next_cursor, call discover_agents again with the same keyword and that cursor to inspect the next page.
form:
  - input_type: text
    name: registry_set_name
    label: Registry Set Name
    attr:
      placeholder: Internal A2A Network
      expose_to_runtime: "true"
      usage_context_label: Registry set
  - input_type: text
    name: registry_url
    label: Registry URL
    attr:
      placeholder: https://api.example.com/a2a/agents
      help_text: Enter the primary registry URL. For InnomightLabs, use /a2a/agents.
      optional: "true"
      expose_to_runtime: "true"
      usage_context_label: Primary discovery URL
  - input_type: text_area
    name: registry_urls
    label: Additional Discovery URLs
    attr:
      rows: "4"
      placeholder: "https://agent.example.com/.well-known/agent-card.json\nhttps://partner.example.com/a2a/agents"
      help_text: Optional. Add one extra registry or single-agent card URL per line.
      optional: "true"
      expose_to_runtime: "true"
      usage_context_label: Additional discovery URLs
      usage_context_max_chars: "800"
  - input_type: key_value
    name: default_credentials
    label: Default Registry Credentials
    attr:
      optional: "true"
      secret: "true"
      key_placeholder: "https://api.example.com"
      value_placeholder: "Bearer token or API key"
      empty_text: "No registry credentials configured."
api_router: router:router
actions:
  - name: discover_agents
    description: Search configured A2A registries for agents matching a keyword.
    handler: actions:discover_agents
  - name: get_agent_card
    description: Fetch and return a sanitized Agent Card for a discovered agent.
    handler: actions:get_agent_card
  - name: send_message
    description: Send a text A2A message to a selected remote agent.
    handler: actions:send_message
  - name: resume_message
    description: Resume a pending A2A message after the user has connected required credentials.
    handler: actions:resume_message
```

`registry_url` is the primary discovery URL and is the common path for InnomightLabs registries such as `https://api.innomightlabs.com/a2a/agents`. `registry_urls` remains as an optional newline-separated additional list because the current form schema does not have a native repeatable list input. Runtime config merges both fields and deduplicates URLs before discovery. `default_credentials` is secret config and is not exposed to runtime prompts or Agent Cards. Per-agent credentials are added later through the skill-owned credential connection page.

Accepted URL forms:

- InnomightLabs registry endpoint: `https://host/a2a/agents`
- Agent-scoped card: `https://host/a2a/agents/{agent_id}/card`
- Agent-specific well-known card when available: `https://host/.well-known/agents/{agent_id}/agent-card.json`
- Generic single-agent well-known card: `https://agent-host/.well-known/agent-card.json`

For InnomightLabs-to-InnomightLabs usage, the user will usually provide:

```text
https://api.innomightlabs.com/a2a/agents
```

and one API key per registry host when invocation should be allowed.

Do not infer `https://host/a2a/agents` from `https://host/.well-known/agent-card.json`. A generic well-known Agent Card represents one callable A2A server/agent. If a registry is needed, it must be configured as a registry URL or explicitly returned by a documented registry integration.

## Models

Add skill-local Pydantic models in `api/src/skills/agent2agent_client/models.py`.

```python
class RegistryConfig(BaseModel):
    registry_set_name: str
    registry_urls: list[AnyHttpUrl]
    default_credentials: dict[str, CredentialConfig] = Field(default_factory=dict)

class DiscoverAgentsRequest(BaseModel):
    keyword: str
    limit: int = 10
    cursor: str | None = None
    include_cards: bool = False

class DiscoveredAgent(BaseModel):
    agent_ref: str
    registry_url: str
    card_url: str | None = None
    service_url: str
    name: str
    description: str | None = None
    skills: list[A2ASkillSummary] = Field(default_factory=list)

class DiscoverAgentsResponse(BaseModel):
    keyword: str
    items: list[DiscoveredAgent]
    next_cursor: str | None = None
    searched_registries: list[str]

class SendMessageRequest(BaseModel):
    agent_ref: str
    message: str
    context_id: str | None = None
    task_id: str | None = None
    timeout_seconds: int = 60
    max_response_chars: int = 12000

class ResumeMessageRequest(BaseModel):
    pending_call_id: str

class PendingA2ACall(BaseModel):
    pending_call_id: str
    owner_email: str
    agent_id: str
    installed_skill_id: str
    conversation_id: str
    actor_email: str
    actor_id: str
    agent_ref: str
    message: str
    context_id: str | None = None
    task_id: str | None = None
    required_security: list[dict[str, Any]]
    status: Literal["pending_auth", "credential_saved", "completed", "failed", "expired"]
    result: dict[str, Any] | None = None
    error: str | None = None
    ttl: int
```

The `agent_ref` must be opaque to the LLM. Encode a small JSON payload with base64url:

```json
{
  "registry_url": "https://api.example.com/a2a/agents",
  "service_url": "https://api.example.com/a2a/agents/agent_123",
  "card_url": "https://api.example.com/a2a/agents/agent_123/card",
  "name": "Research Agent"
}
```

Do not put credentials in `agent_ref`.

## Discovery Algorithm

Action: `discover_agents`

Inputs:

```json
{
  "keyword": "gmail",
  "limit": 10,
  "cursor": null,
  "include_cards": false
}
```

Flow:

1. Parse and normalize install config.
2. Decode cursor into per-registry offsets/cursors.
3. For each configured registry URL:
   - If URL is `/a2a/agents`, call it directly with `query=<keyword>`, `limit`, and cursor.
   - If the registry returns embedded `agentCard`, use it for keyword matching and candidate metadata.
   - If the registry returns `agentCardUrl`, retain it for `get_agent_card` and refreshes.
   - If URL is an agent-scoped card URL, fetch it and treat it as a single candidate.
   - If URL ends with `/.well-known/agent-card.json`, fetch it and treat it as a single generic Agent Card candidate. Do not derive `/a2a/agents` from the well-known URL.
4. Normalize each candidate into `DiscoveredAgent`.
5. Apply simple case-insensitive keyword containment matching against:
   - agent `name`
   - agent `description`
   - skill `id`
   - skill `name`
   - skill `description`
   - skill `tags`
6. Return results in registry order, capped at `limit` where `limit` defaults to 10 and is clamped to 10.
7. If more matches exist, return `next_cursor`. The agent should call the same action again with the same `keyword` and returned cursor.

Do not use natural language search, semantic scoring, vector ranking, or LLM ranking inside the skill for v1. Discovery is a simple keyword search. The reasoning agent can page through results and decide which agent to inspect or call.

## Agent Card Fetching

Action: `get_agent_card`

Inputs:

```json
{
  "agent_ref": "<opaque-agent-ref>"
}
```

Flow:

1. Decode `agent_ref`.
2. Fetch `card_url` if present; otherwise use the already-fetched embedded card from discovery. Do not guess `{service_url}/agent-card` for InnomightLabs registry results; the registry must provide `agentCardUrl` and/or embedded `agentCard`.
3. Validate protocol version is `1.0.0`.
4. Return sanitized fields:
   - `name`
   - `description`
   - selected `supportedInterfaces`
   - `capabilities`
   - `defaultInputModes`
   - `defaultOutputModes`
   - `skills`
   - credential requirement names, not values

Do not return full metadata blindly. Keep allowlisted metadata only when it is part of a documented integration contract.

## Message Sending

Action: `send_message`

Inputs:

```json
{
  "agent_ref": "<opaque-agent-ref>",
  "message": "Please summarize the latest unread email threads.",
  "context_id": "optional-shared-context",
  "task_id": "optional-task-id",
  "timeout_seconds": 60
}
```

Flow:

1. Decode `agent_ref`.
2. Fetch or reuse the selected Agent Card and inspect `securitySchemes` plus `security`.
3. Resolve a compatible credential:
   - Exact `service_url` credential.
   - Exact `card_url` credential.
   - Exact registry URL credential.
   - Normalized origin fallback, for example `https://api.innomightlabs.com`.
   - No credential only if the Agent Card declares no required security.
4. If no compatible credential exists:
   - Current phase: return `ok=false`, `auth_required=true`, and a bounded message asking the user to add an API key to the skill installation.
   - OAuth/credential phase: create a `PendingA2ACall` record and return `pending_call_id` plus `connect_url`.
   - Do not ask the LLM or user to paste credentials into chat.
5. Select a compatible interface from the Agent Card. Prefer `JSONRPC` for current InnomightLabs agents. Use `HTTP+JSON` only when the card advertises it and the standard operation route is expected to exist.
6. For JSON-RPC, POST to `{service_url}` with method `SendMessage`.
7. Body:

```json
{
  "jsonrpc": "2.0",
  "id": "request-id",
  "method": "SendMessage",
  "params": {
    "message": {
      "role": "ROLE_USER",
      "parts": [{"kind": "text", "text": "..."}],
      "contextId": "...",
      "taskId": "..."
    },
    "configuration": {
      "acceptedOutputModes": ["text/plain"]
    }
  }
}
```

8. For HTTP+JSON, POST the `params` object to `{service_url}/message:send`.
9. Return compact structured data:

```json
{
  "ok": true,
  "agent_name": "Remote Agent",
  "task_id": "...",
  "context_id": "...",
  "state": "TASK_STATE_COMPLETED",
  "response_text": "...",
  "truncated": false
}
```

For v1, use non-streaming `SendMessage` over JSON-RPC for InnomightLabs agents. Add streaming only after the skill runtime has a clear UX for streamed nested agent output.

## Credential Challenge And Resume Flow

This is the next phase. The first implementation returns a structured `auth_required` result when credentials are missing or unsupported, but it does not create pending calls or collect credentials through a browser route yet. This keeps phase one focused on the A2A client contract and API-key/no-auth communication.

### Flow

1. Agent calls `send_message`.
2. Skill detects missing credential for the selected remote Agent Card.
3. Skill stores `PendingA2ACall`:

```text
PK = User#{owner_email}
SK = A2AClientPendingCall#{pending_call_id}
GSI2PK = A2AClientPendingCall#{pending_call_id}
GSI2SK = A2AClientPendingCall#{pending_call_id}
ttl = now + 30 minutes
```

4. Skill returns:

```json
{
  "ok": false,
  "auth_required": true,
  "pending_call_id": "a2apending_...",
  "agent_name": "Remote Agent",
  "required_security": [
    {
      "scheme_name": "agentApiKey",
      "type": "apiKey",
      "in": "header",
      "name": "Authorization"
    }
  ],
  "connect_url": "https://api.innomightlabs.com/skills/agent2agent_client/connect/start?pending_call_id=a2apending_...",
  "resume_instruction": "After the user completes this connection, call resume_message with pending_call_id."
}
```

5. The assistant tells the user to open the `connect_url`.
6. The user authenticates to InnomightLabs dashboard if needed.
7. The credential page shows:
   - remote agent name
   - remote service URL
   - required security scheme
   - credential input appropriate to the scheme
8. User submits credential.
9. Backend stores the credential encrypted against the installed skill and remote agent selector.
10. Backend marks the pending call `credential_saved`.
11. Frontend redirects back to the original conversation with `pending_call_id` in the URL, or shows a button that sends “Continue the pending A2A request”.
12. Agent calls `resume_message` with `pending_call_id`.
13. Skill reloads `PendingA2ACall`, resolves the newly stored credential, sends the original A2A message, stores the result on the pending call, and returns the final response to the agent.

### Why Not Auto-Resume Silently

Automatically invoking the agent from the OAuth/API-key callback would require a background agent run outside the normal chat request lifecycle. That is possible later, but it touches conversation streaming, user notification, and duplicate-run handling. For first release, the safer path is:

- complete credential capture in the browser
- return to the conversation
- have the agent call `resume_message`
- execute exactly one pending request under the normal skill runtime

This still “connects back” to the previous state because `pending_call_id` preserves the exact original `agent_ref`, message, context id, conversation id, actor metadata, and required security.

### Idempotency

`resume_message` must be idempotent:

- If pending call is `completed`, return the stored result.
- If pending call is `failed`, return the stored failure.
- If pending call is `pending_auth`, return `auth_required` again.
- If pending call is expired/missing, return a clear error asking the user to retry discovery/send.

### Pending Payload Privacy

The pending call stores the delegated message because it must resume exactly. Apply these controls:

- TTL should be short, initially 30 minutes.
- Do not store credentials in the pending call.
- Store only the target request, not full local conversation history.
- Never expose pending call contents through the connect URL.
- Require dashboard auth and owner match before showing the credential page.

## Credentials

Do not require users to provide credentials for every discovered agent during skill installation. Discovery and credential provisioning should be separated. The install form provides trusted registry URLs and optional defaults. Per-agent credentials are captured only when a selected agent actually needs them.

Use a simple phased credential model:

### Current Phase Credential Support

Support:

- No authentication, only when the Agent Card has no `security` requirement.
- API key / bearer token credentials from encrypted skill install config.
- OAuth-required response with `unsupported_auth=true` until explicit providers are chosen.

Do not support in v1:

- Per-agent credential capture through a skill-owned connect URL.
- Pending-call resume through `resume_message`.
- Arbitrary remote OAuth dynamic client registration.
- Refresh-token lifecycle for unknown remote providers.
- The LLM choosing or constructing OAuth URLs itself.

Credentials provided at install time are stored through the existing `AgentSkill.encrypted_secrets` path via `attr.secret: "true"`.

Config shape after validation:

```json
{
  "registry_set_name": "Internal A2A Network",
  "registry_url": "https://api.innomightlabs.com/a2a/agents",
  "registry_urls": "https://partner.example.com/a2a/agents",
  "default_credentials": {
    "https://api.innomightlabs.com": "pk_live_..."
  }
}
```

Per-agent credentials saved through the connect URL should be stored as separate encrypted credential records rather than mutating the installed skill config blob. This avoids rewriting skill install identity and lets users add/remove remote agent credentials independently.

Proposed credential item:

```text
PK = User#{owner_email}
SK = A2AClientCredential#{installed_skill_id}#{credential_id}
GSI2PK = A2AClientCredentialLookup#{owner_email}#{installed_skill_id}
GSI2SK = Target#{normalized_service_url_or_origin}#{scheme_name}
```

Fields:

```json
{
  "credential_id": "a2acred_...",
  "agent_id": "local-owner-agent-id",
  "installed_skill_id": "agent2agent_client:...",
  "target": "https://api.example.com/a2a/agents/agent_123",
  "target_origin": "https://api.example.com",
  "scheme_name": "agentApiKey",
  "scheme_type": "apiKey",
  "encrypted_secret": "...",
  "created_at": "...",
  "updated_at": "..."
}
```

For the current InnomightLabs A2A server, use bearer credentials as:

```http
Authorization: Bearer <key>
```

Credential resolution order:

1. Exact `service_url`.
2. Exact `card_url`.
3. Exact registry URL.
4. Registry origin/host fallback.
5. No auth only when the selected Agent Card has no required security.
6. Missing credential challenge when the selected Agent Card requires auth.

Do not log credentials. Do not include credentials in action results, `agent_ref`, task artifacts, or error messages.

### OAuth Handling

A2A OAuth support has two implemented paths:

- Inbound InnomightLabs A2A server authentication with the OAuth 2.0 client credentials grant.
- Outbound remote-agent authorization with OAuth 2.0 authorization code plus PKCE, callback storage, and refresh-token reuse.

Inbound InnomightLabs A2A servers publish two alternative security requirements in each Agent Card:

- `oauth2ClientCredentials`: A2A `oauth2SecurityScheme` with `clientCredentials`, token URL `/a2a/oauth/token`, metadata URL `/a2a/oauth/.well-known/oauth-authorization-server`, and scopes `a2a:message` and `a2a:tasks`.
- `agentApiKey`: legacy Bearer API-key compatibility.

Token request:

```http
POST /a2a/oauth/token
Content-Type: application/x-www-form-urlencoded
Authorization: Basic base64(<agent_api_key_id>:<agent_public_key>)

grant_type=client_credentials&scope=a2a:message%20a2a:tasks
```

`client_secret_post` is also accepted with `client_id` and `client_secret` form fields. The server validates the secret against the existing active `AgentApiKey` record, then issues a short-lived JWT access token with:

- `iss`: `${API_BASE_URL}/a2a/oauth`
- `aud`: `innomightlabs:a2a`
- `token_use`: `a2a_access_token`
- `agent_id`, `client_key_id`, `owner_email`
- space-delimited `scope`
- `exp`, `iat`, and random `jti`

Protected A2A routes accept either the legacy opaque key or the OAuth Bearer token. OAuth tokens are validated for signature, issuer, audience, expiry, route `agent_id`, and required scope. The backing API key is reloaded on each request so disabled or deleted keys stop authorizing new calls even before existing JWTs expire.

Route scopes:

- `POST /a2a/agents/{agent_id}/message:send`: `a2a:message`
- `POST /a2a/agents/{agent_id}/message:stream`: `a2a:message`
- task list/get/cancel/subscribe routes: `a2a:tasks`
- JSON-RPC endpoint: both `a2a:message` and `a2a:tasks` because the method is selected inside the request body.

Configuration:

- `A2A_OAUTH_ACCESS_TOKEN_TTL_SECONDS`: access-token lifetime in seconds, clamped from 60 seconds to 24 hours. Default: `3600`.
- `API_BASE_URL`: used for the OAuth issuer, token endpoint, metadata endpoint, and Agent Card URLs. It must match the public origin clients use, otherwise issuer validation will fail.

Outbound `agent2agent_client` behavior:

- For `apiKeySecurityScheme` or Bearer `httpAuthSecurityScheme`, configured `default_credentials` are sent as `Authorization: Bearer <value>` unless the value already starts with `Bearer ` or `Basic `.
- For A2A `oauth2SecurityScheme.clientCredentials`, configured credentials can be `client_id:client_secret` or JSON with `client_id`/`client_secret`. The skill exchanges them at the card's token URL, sends only `Authorization: Bearer <access_token>` to the remote A2A endpoint, and never includes tokens in action results.
- For A2A `oauth2SecurityScheme.authorizationCode`, configured credentials must include the OAuth client id and optional client secret, either as `client_id:client_secret` or JSON with `client_id`/`client_secret`.
- When no valid target-scoped token is stored, `send_message` returns `auth_required=true` with `credential_setup_url` set to the remote provider's authorization URL. The URL is built by the backend from the Agent Card flow and encrypted state; the LLM never constructs OAuth URLs or asks for authorization codes.
- The authorization URL uses `redirect_uri=${API_BASE_URL}/skills/agent2agent_client/oauth/callback`. The callback exchanges the code, stores access and refresh tokens encrypted in `A2ARemoteOAuthCredential` records scoped by `owner_email + installed_skill_id + target_origin`, and redirects back with `a2a_oauth=success|error`.
- Future calls load the saved target credential. If the token is expiring soon and a refresh token exists, the skill refreshes it, persists rotated tokens, and sends only `Authorization: Bearer <access_token>` to the remote A2A endpoint.
- OAuth authorization and token URLs must share an origin with the target service URL or one of the configured registry URLs. This prevents a remote Agent Card from redirecting client secrets or authorization flows to an unrelated service.
- Discovery and Agent Card fetches use configured direct Bearer/API-key credentials for matching registry/card origins. OAuth client credentials are not sent directly to discovery endpoints.

Edge cases:

- Missing OAuth client configuration returns `auth_required=true` and a skill configuration link when the runtime context contains `agent_id` and `installed_skill_id`.
- Missing delegated authorization returns `auth_required=true` and the backend-generated remote authorization URL.
- Unsupported OAuth flows such as device code, password, mTLS, and OpenID Connect currently return `unsupported_auth=true` unless a direct Bearer token is configured.
- Token exchange failures return `auth_required=true` with a bounded error preview and do not expose the client secret.
- OAuth tokens with insufficient scope return `403` with `WWW-Authenticate: Bearer` challenge metadata.
- Revoked backing API keys invalidate OAuth tokens on the next protected A2A call.

Deferred pending-call replay phase: create a pending call and return:

```json
{
  "ok": false,
  "auth_required": true,
  "pending_call_id": "a2apending_...",
  "agent_name": "Remote Agent",
  "security_scheme": "oauth2",
  "connect_url": "https://api.innomightlabs.com/skills/agent2agent-client/oauth/start?...",
  "message": "Authorization is required before this agent can be called."
}
```

The reasoning agent can then tell the user to open the returned `connect_url`. The current implementation asks the user to retry after OAuth completion instead of replaying the original request automatically.

```text
owner_email + installed_skill_id + remote_agent_origin/service_url + security_scheme
```

Future hardening:

- Add credential aliases so users do not need to key secrets by raw URL.
- Add per-agent credential mapping when one registry lists agents that require different API keys.
- Add dynamic OAuth client registration for remote providers that are not explicitly allowlisted.

## Safety And Privacy

The skill allows one agent to send information to another agent, potentially outside the current user’s account. The system prompt and action validation must enforce these rules:

- Do not send secrets, tokens, OAuth credentials, raw API keys, or unrelated private conversation history.
- Summarize context instead of forwarding full transcripts.
- Include only the minimum data needed for the remote agent to perform the delegated task.
- Prefer configured InnomightLabs registries over arbitrary user-provided URLs.
- Require explicit user intent before sending sensitive content to remote external agents.
- Bound input size and response size.
- Use explicit HTTP timeouts.
- Reject non-HTTPS URLs in production unless `ENVIRONMENT=local`.

SSRF guardrails:

- Allow `http://localhost` only in local development.
- In production, reject private IP ranges, link-local IPs, and non-HTTP(S) schemes.
- Follow redirects only if the final URL still passes the same checks.

## Caching

V1 can fetch live on every `discover_agents` call with short timeouts. Add in-memory request-level deduping only.

V1.1 can add short TTL cache:

```text
cache key = owner_email + agent_id + installed_skill_id + registry_url
ttl = 5 minutes
```

Do not persist Agent Cards initially. Agent discovery should reflect newly enabled/disabled agents quickly, and persisted cards create stale trust data.

## Error Handling

Return structured action errors where practical:

- Invalid install config: `ValueError("Invalid Agent2Agent registry URL: ...")`
- Registry unavailable: include redacted URL and timeout status.
- Unsupported protocol: `ValueError("Only A2A protocolVersion 1.0.0 is supported")`
- Missing credential: `ValueError("No API key configured for selected A2A agent")`
- Remote task failed: return `ok=false`, `state=TASK_STATE_FAILED`, and bounded `response_text`.

Network failures should not abort discovery across all registries. `discover_agents` should include partial results and a `registry_errors` list.

## Implementation Plan

1. Add `api/src/skills/agent2agent_client/manifest.yml`.
2. Add `models.py` for install config and action request/response validation.
3. Add `client.py`:
   - safe URL validation
   - Agent Card security inspection
   - no-auth and bearer/API-key credential resolution
   - structured OAuth-required response when OAuth is required but unavailable
   - Agent Card GET
   - A2A JSON-RPC `SendMessage` POST
   - HTTP+JSON `message:send` POST only for cards that explicitly advertise HTTP+JSON
4. Add `discovery.py`:
   - registry URL classification
   - `/a2a/agents` pagination
   - registry `agentCardUrl` handling
   - registry embedded `agentCard` handling
   - generic single-card handling for well-known Agent Cards
   - simple keyword containment filtering
   - opaque `agent_ref` encoding/decoding
5. Add `credentials.py`:
   - credential lookup by service URL, card URL, registry URL, and origin.
   - structured `auth_required` result for missing or unsupported credentials.
6. Defer skill-owned `router.py` to OAuth/credential phase:
   - `GET /skills/agent2agent_client/connect/start?pending_call_id=...`
   - `GET /skills/agent2agent_client/connect/{pending_call_id}`
   - `POST /skills/agent2agent_client/connect/{pending_call_id}`
7. Add `actions.py`:
   - `discover_agents`
   - `get_agent_card`
   - `send_message`
   - `resume_message` placeholder
8. Defer SPA credential page to OAuth/credential phase:
   - opens from `connect_url`.
   - renders remote agent/security details.
   - captures credential without showing it to the LLM.
   - redirects back to the originating conversation with `pending_call_id`.
9. Add tests:
   - manifest loads.
   - install config parses newline registry URLs and encrypted default credential map.
   - discovery from `/a2a/agents` paginated endpoint.
   - discovery uses embedded `agentCard`, stores `agentCardUrl`, and does not guess card paths.
   - well-known Agent Card input is treated as one candidate and does not infer `/a2a/agents`.
   - keyword matching checks agent name, description, skills, and tags.
   - pagination returns at most 10 results and provides `next_cursor` when more matches exist.
   - disabled or malformed cards are ignored with registry errors.
   - `send_message` posts A2A `1.0.0` JSON-RPC shape with `Authorization: Bearer`.
   - `send_message` returns `auth_required` when credentials are missing.
   - `send_message` returns `unsupported_auth=true` for OAuth/non-API-key auth in this phase.
   - credentials are not returned in action output or logs.
   - production URL validation rejects localhost/private addresses.
10. Add a developer-manual notebook section after implementation showing:
   - install skill with `http://localhost:1455/a2a/agents`
   - discover agents
   - get selected card
   - send message with a stable `context_id`
   - missing credential connect URL
   - resume pending message after credential save

## Testing Plan

Focused tests:

```bash
cd api
uv run pytest tests/test_agent2agent_client_skill.py -v
```

Relevant regression tests:

```bash
cd api
uv run pytest tests/test_a2a_discovery.py tests/test_a2a_invocation.py -v
```

Full backend:

```bash
cd api
uv run pytest -v
```

## V1 Decisions

- Build one repeatable `agent2agent_client` skill.
- Require discovery before delegation in the skill prompt.
- Allow arbitrary external registry URLs in v1.
- Support multiple configured registry URLs in one install.
- Allow multiple installed skill instances when the user wants separate registry sets.
- Use non-streaming JSON-RPC `SendMessage` first.
- Use installed skill encrypted secrets for registry/agent API keys.
- Support per-registry and origin-level bearer credentials in the current phase.
- Defer per-agent credential records, credential connect URL, and pending-call resume flow to the OAuth/credential phase.
- Do not allow direct `service_url` calls in v1; require opaque `agent_ref` from `discover_agents`.
- Do not mirror remote A2A tasks into the local A2A task UI in v1; the local skill action result is enough.
- Do not add OAuth provider support until we choose explicit allowlisted providers. OAuth-required agents should return `auth_required` and `unsupported_auth=true`.
- Return opaque `agent_ref` from discovery and require it for `send_message`.
- Do not persist discovered cards in v1.
- Do not expose every discovered agent as a separate static tool.
