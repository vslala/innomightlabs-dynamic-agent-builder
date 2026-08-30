# Low Level Design: A2A Client OAuth DCR Consent Flow

Date: 2026-08-30
Status: Plan
Owner: InnomightLabs API / Skills
Jira: KAN-5

## Goal

Complete OAuth 2.x support for the `agent2agent_client` skill so an InnomightLabs agent can connect to OAuth-protected A2A gateways, starting with Atlassian Rovo A2A.

The target user experience is:

1. User installs the Agent2Agent Client skill.
2. If the user asks to connect during installation, the backend discovers the remote Agent Card, performs Dynamic Client Registration when required, creates a PKCE/state session, and returns a consent URL.
3. The user grants permission at the provider authorization URL.
4. The callback exchanges the authorization code, stores encrypted access/refresh tokens, and marks the pending connection complete.
5. `send_message` and `resume_message` use the stored grant and refresh token without exposing OAuth secrets to the LLM.

If the backend cannot complete DCR or authorization setup automatically, the install/action response must return a specific setup URL and error reason. The model should give that link to the user; it must not ask the user to paste tokens, auth codes, client secrets, PKCE verifiers, or refresh tokens.

## Current Gap

The first OAuth pass supports authorization-code consent and token refresh, but it assumes a preconfigured `client_id` / `client_secret`. That does not satisfy Atlassian Rovo A2A, because Rovo requires Dynamic Client Registration and does not support manual OAuth client creation as a substitute.

The current implementation also rejects OAuth endpoints that are not on the target A2A origin. Rovo uses:

- A2A / Agent Card origin: `https://a2a.atlassian.com`
- OAuth authorization/token origin: `https://auth.atlassian.com`

The next implementation should keep A2A OAuth generic, with Atlassian behavior flowing from Agent Card and OAuth metadata rather than hardcoded Rovo branches.

## Target Architecture

Keep the feature inside the skill package:

```text
api/src/skills/agent2agent_client/
  actions.py
  client.py
  credentials.py
  discovery.py
  dcr.py
  oauth.py
  pending.py
  router.py
  models.py
  manifest.yml
```

Use shared platform code only for generic install response plumbing and secret handling. Do not add Atlassian-specific logic to shared routers.

## Install-Time Flow

Extend the A2A skill install form with optional connection intent:

```yaml
form:
  - input_type: choice
    name: connect_on_install
    label: Connect during installation
    values: ["no", "yes"]
    value: "no"
    attr:
      optional: "true"
      expose_to_runtime: "false"
  - input_type: text
    name: initial_agent_card_url
    label: Agent Card URL to connect
    attr:
      placeholder: https://a2a.atlassian.com/.well-known/agent.json
      optional: "true"
      expose_to_runtime: "true"
      usage_context_label: Initial A2A card
```

Install behavior:

1. `POST /agents/{agent_id}/skills?skill_id=agent2agent_client` stores the skill as usual.
2. If `connect_on_install != "yes"`, return the normal installed skill response.
3. If `connect_on_install == "yes"`, require either `initial_agent_card_url` or exactly one configured registry URL that is a direct Agent Card URL.
4. Fetch the Agent Card and derive OAuth metadata from it.
5. Run DCR if the provider requires it and no reusable registration exists.
6. Create a connection session and return a post-install continuation object containing the authorization URL.

Extend `InstalledSkillResponse` with an optional field:

```python
class SkillPostInstallAction(BaseModel):
    type: Literal["oauth_authorization_required", "setup_required"]
    url: str
    label: str
    message: str
    pending_call_id: str | None = None

class InstalledSkillResponse(BaseModel):
    ...
    post_install_action: SkillPostInstallAction | None = None
```

This keeps the install API compatible: existing clients ignore the optional field; the SPA can immediately navigate or show a button.

If DCR cannot be completed automatically, return:

```json
{
  "type": "setup_required",
  "url": "<metadata registration URL or provider docs URL when available>",
  "label": "Complete A2A OAuth setup",
  "message": "The remote A2A provider requires Dynamic Client Registration, but registration failed: <bounded reason>."
}
```

For Atlassian Rovo, successful setup should return the Atlassian authorization URL, not a manual Developer Console URL.

## OAuth Metadata and DCR

Add `dcr.py` with:

- `discover_oauth_metadata(card, service_url, registry_config) -> A2AOAuthMetadata`
- `registration_required(metadata, card) -> bool`
- `find_client_registration(owner_email, installed_skill_id, provider_key)`
- `register_client(metadata, redirect_uri, scopes) -> A2AClientRegistration`
- `save_client_registration(record)`

Metadata resolution order:

1. OAuth metadata URL advertised by the Agent Card security scheme.
2. Authorization server metadata derived from the authorization URL issuer when standards allow it.
3. Registration endpoint directly advertised in the card/security metadata.

Do not hardcode Atlassian endpoints when they are present in the card or metadata.

DCR request should include:

```json
{
  "client_name": "InnomightLabs Agent2Agent Client",
  "redirect_uris": ["https://<api-base>/skills/agent2agent_client/oauth/callback"],
  "grant_types": ["authorization_code", "refresh_token"],
  "response_types": ["code"],
  "scope": "<space-delimited scopes from card>",
  "token_endpoint_auth_method": "none",
  "code_challenge_methods_supported": ["S256"]
}
```

Adjust fields based on the provider metadata. If the provider returns `client_secret`, encrypt it and use it for token exchange. If it returns a public client, do not invent a secret.

Registration reuse key:

```text
User#{owner_email}
A2AClientRegistration#{installed_skill_id}#{provider_key}
```

`provider_key` should be a stable hash of issuer/authorization-server metadata plus target origin, not only the registry URL.

Stored encrypted registration payload:

- client id
- client secret, if present
- registration access token, if present
- registration client URI, if present
- issuer / auth server origin
- authorization URL
- token URL
- registration endpoint
- redirect URI
- scopes
- created/updated timestamps
- expiry timestamp if provided

## URL and SSRF Policy

Replace the current same-origin OAuth endpoint rule with a metadata-bound policy:

- Allow same-origin endpoints when the Agent Card, target service URL, and OAuth URLs share an origin.
- Allow cross-origin OAuth endpoints when they are declared by trusted OAuth metadata reachable from the Agent Card security scheme.
- Apply the existing A2A URL validation before fetching Agent Cards, metadata, registration endpoints, token endpoints, and authorization endpoints.
- Require HTTPS except local development allowlist.
- Do not follow arbitrary redirects to private IPs, loopback, link-local, or unsupported schemes.
- Record the resolved issuer/auth-server origin in the registration and grant.

This allows `a2a.atlassian.com` to use `auth.atlassian.com` without blindly trusting arbitrary card-provided token URLs.

## State, PKCE, and Pending Call Store

The current state is encrypted and expiring, but KAN-5 requires persisted, single-use state and pending-call resume.

Add `pending.py` with records:

```text
User#{owner_email}
A2AOAuthState#{state_id}

User#{owner_email}
A2APendingCall#{pending_call_id}
```

State fields:

- state id, random and opaque
- owner email
- agent id
- installed skill id
- provider key
- target origin
- code verifier, encrypted
- redirect URI
- return URL
- pending call id, optional
- created/expiry timestamps
- consumed timestamp

Pending call fields:

- pending call id, random and opaque
- owner email
- agent id
- installed skill id
- sanitized original action name
- sanitized original action arguments
- selected agent ref
- target service URL / card URL
- provider key
- status: `waiting_for_oauth`, `ready`, `consumed`, `expired`, `failed`
- created/expiry timestamps

Rules:

- State must be consumed atomically before code exchange.
- Replayed, expired, missing, or wrong-owner state must fail.
- Pending call IDs must be user-scoped and never reveal target tokens.
- Store only data required to replay the A2A call.

## Runtime Flow

### `send_message`

1. Resolve `agent_ref`, fetch/sanitize Agent Card, and identify service URL.
2. If static Bearer/API-key credentials satisfy the card, keep existing behavior.
3. If OAuth authorization-code is required:
   - Find encrypted OAuth grant by owner + installed skill + provider key.
   - If valid or refreshable, attach `Authorization: Bearer <access_token>`.
   - If missing, create a pending call, run DCR if needed, create state/PKCE, and return `auth_required`.
4. Send the A2A request through `A2AHttpClient`.
5. On `401` from an OAuth target:
   - Refresh once if a refresh token exists.
   - Retry once with the new access token.
   - If refresh fails permanently, invalidate the grant and return `auth_required`.

`auth_required` response should include:

```json
{
  "ok": false,
  "auth_required": true,
  "credential_setup_url": "<authorization URL>",
  "credential_setup_label": "Connect Agent2Agent OAuth",
  "pending_call_id": "<opaque id>",
  "message": "This remote agent requires OAuth. Open the link to grant permission, then call resume_message with pending_call_id."
}
```

### OAuth callback

1. Validate and atomically consume state.
2. Load encrypted code verifier and provider/client registration.
3. Exchange code at the discovered token endpoint.
4. Persist encrypted token grant scoped to owner + installed skill + provider key + target origin.
5. Mark pending call `ready` when a pending call exists.
6. Redirect to the original return URL with `a2a_oauth=success` and `pending_call_id`.

The callback must never return tokens to the browser, LLM, logs, or redirect query string.

### `resume_message`

1. Validate `pending_call_id`, owner, agent, installed skill, status, and expiry.
2. Mark pending call as consumed atomically.
3. Resolve the stored agent ref and saved OAuth grant.
4. Execute the original `send_message` operation with the fresh credential.
5. Return the normal `SendMessageResponse`.

If the grant is missing or refresh fails, create a new state and return another `auth_required` response.

## Installation Failure and DCR Link Semantics

There are two different "links" the backend may return:

- **Authorization URL**: preferred successful DCR path. User grants consent here.
- **Setup/DCR URL**: fallback when automated DCR cannot proceed. This should be a provider registration endpoint, metadata URL, or docs URL with a bounded explanation. It is not a place to paste credentials into chat.

For Atlassian Rovo, automated DCR should be the normal path. A fallback setup URL should only appear if:

- Agent Card cannot be fetched.
- OAuth metadata cannot be fetched or validated.
- Registration endpoint is absent despite the card requiring DCR.
- Registration endpoint rejects the client metadata.
- Redirect URI is not acceptable.
- Network/SSRF policy blocks the endpoint.

## Data Model

Add or extend Pydantic models in `agent2agent_client/oauth.py`, `dcr.py`, and `pending.py`:

- `A2AOAuthMetadata`
- `A2AClientRegistration`
- `A2AClientRegistrationRecord`
- `A2AOAuthStateRecord`
- `A2APendingCallRecord`
- `A2ARemoteOAuthGrant`

Keep token grants separate from skill `default_credentials`. Skill form secrets are suitable for static credentials and optional provider overrides, not user OAuth grants.

## Manifest and Prompt Updates

Update `manifest.yml`:

- Change `resume_message` description from reserved to active.
- Add install fields for optional connect-on-install.
- Keep `default_credentials` for legacy/static Bearer/API-key compatibility.
- Update prompt to say:
  - use `credential_setup_url` exactly as returned;
  - after OAuth success, call `resume_message` with `pending_call_id` when available;
  - never ask for auth codes, state, access tokens, refresh tokens, client ids, client secrets, or PKCE verifiers.

## API Changes

Skill-owned routes under `/skills/agent2agent_client`:

- `GET /oauth/callback`
- `POST /oauth/start`
- `GET /oauth/status/{pending_call_id}`

`POST /oauth/start` allows the SPA to start or restart OAuth for an installed A2A skill without invoking `send_message`. It should accept:

```json
{
  "agent_id": "...",
  "installed_skill_id": "...",
  "agent_card_url": "https://a2a.atlassian.com/.well-known/agent.json",
  "return_to": "https://app.../dashboard/agents/..."
}
```

It returns the same continuation shape used by install and `auth_required`.

## Tests

Add focused tests for:

- Rovo Agent Card discovery without credentials.
- OAuth authorization-code detection from Agent Card.
- DCR metadata discovery and registration request body.
- Reuse of existing client registration.
- Cross-origin auth server allowed when metadata-bound.
- Cross-origin token endpoint rejected when not metadata-bound.
- Install with `connect_on_install=yes` returns authorization URL.
- Install DCR failure returns setup-required URL and bounded reason.
- PKCE S256 generation.
- State persistence, expiry, owner binding, and replay rejection.
- Callback code exchange with correct `code_verifier`.
- Encrypted grant storage with access token, refresh token, expiry, scopes, target/provider key, and client id.
- `send_message` returns `auth_required` with `pending_call_id` when grant is absent.
- `resume_message` consumes pending call and executes original request.
- Expired access token refreshes and persists rotated refresh token.
- Refresh failure invalidates grant and returns new `auth_required`.
- Tokens, client secrets, auth codes, state payloads, and PKCE verifier never appear in model-visible responses.
- Existing unauthenticated agents still work.
- Existing static Bearer/API-key credentials still work.

Run at minimum:

```bash
cd api
uv run pytest tests/test_agent2agent_client_skill.py tests/test_a2a_discovery.py tests/test_a2a_invocation.py
uv run python -m py_compile src/skills/agent2agent_client/actions.py src/skills/agent2agent_client/oauth.py src/skills/agent2agent_client/dcr.py src/skills/agent2agent_client/pending.py src/skills/agent2agent_client/router.py
```

## Implementation Order

1. Add response/model support for optional post-install continuation.
2. Add `dcr.py` and registration storage.
3. Replace OAuth endpoint same-origin checks with metadata-bound URL policy.
4. Add persisted state and pending-call storage in `pending.py`.
5. Wire install-time `connect_on_install` flow.
6. Wire `send_message` to create pending calls and return authorization URLs.
7. Update callback to consume persisted state and mark pending calls ready.
8. Implement active `resume_message`.
9. Add refresh retry/invalidation behavior.
10. Update manifest prompt and docs.
11. Add tests for the full acceptance criteria.

## Done Criteria

The feature is done when:

- Installing the A2A client skill with Rovo connect enabled returns a valid Atlassian consent URL produced after DCR.
- The callback stores encrypted access and refresh tokens.
- A pending Rovo `send_message` can be resumed without the model seeing credentials.
- Subsequent Rovo calls use refresh tokens automatically.
- Static credential and unauthenticated A2A behavior remain unchanged.
- KAN-5 acceptance criteria are covered by tests.
