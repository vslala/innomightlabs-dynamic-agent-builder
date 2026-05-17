# OpenAI OAuth (ChatGPT/Codex) Integration in Innomightlabs

## Why We Built This

We wanted users to connect their existing ChatGPT/Codex subscription without asking them to paste an OpenAI API key.  
That requires OAuth (authorization code + PKCE), token storage on the backend, token refresh, and a runtime provider that calls the correct inference endpoint for this token type.

This post documents the full flow implemented in our app.

---

## The Core Distinction: OAuth Token vs Platform API Key

A ChatGPT/Codex OAuth token is not the same as an OpenAI Platform API key.

- Platform API key flow uses: `https://api.openai.com/v1/responses`
- ChatGPT/Codex OAuth flow uses: `https://chatgpt.com/backend-api/codex/responses`

If you call the Platform endpoint with a ChatGPT OAuth token, you will see scope/permission failures.

---

## End-to-End Architecture

### Internal app routes

1. `POST /auth/openai/start` (authenticated)
2. Browser redirects to OpenAI authorize URL
3. OpenAI redirects back to `GET /auth/callback`
4. Backend exchanges code for tokens
5. Backend stores encrypted provider credentials in DynamoDB
6. User returns to SPA settings page with success/error flag

### External OpenAI endpoints

- Authorize: `https://auth.openai.com/oauth/authorize`
- Token exchange/refresh: `https://auth.openai.com/oauth/token`
- Inference (Codex OAuth): `https://chatgpt.com/backend-api/codex/responses`

---

## OAuth Start (`POST /auth/openai/start`)

The backend generates PKCE values:

- `state`
- `code_verifier`
- `code_challenge = BASE64URL(SHA256(code_verifier))`

Then it encrypts/signs a state payload and returns:

```json
{
  "authorize_url": "https://auth.openai.com/oauth/authorize?...params..."
}
```

The SPA immediately redirects the browser to this `authorize_url`.

### Authorize URL parameters used

- `response_type=code`
- `client_id=<OPENAI_OAUTH_CLIENT_ID>`
- `redirect_uri=<OPENAI_OAUTH_REDIRECT_URI>`
- `scope=openid profile email offline_access`
- `code_challenge=<pkce_challenge>`
- `code_challenge_method=S256`
- `state=<encrypted_state_payload>`
- optional flags:
  - `id_token_add_organizations=true|false`
  - `codex_cli_simplified_flow=true|false`
  - `originator=<string>`

Example shape:

```text
https://auth.openai.com/oauth/authorize
?response_type=code
&client_id=app_xxx
&redirect_uri=http%3A%2F%2Flocalhost%3A1455%2Fauth%2Fcallback
&scope=openid%20profile%20email%20offline_access
&code_challenge=...
&code_challenge_method=S256
&state=...
&id_token_add_organizations=true
&codex_cli_simplified_flow=true
&originator=pi
```

---

## OAuth Callback (`GET /auth/callback`)

OpenAI redirects with:

- `code`
- `state`
- or `error` + `error_description`

The backend:

1. Decrypts and validates `state`
2. Verifies anti-CSRF/state integrity
3. Exchanges `code` for tokens:

`POST https://auth.openai.com/oauth/token`

`application/x-www-form-urlencoded` body:

- `grant_type=authorization_code`
- `code=<auth_code>`
- `client_id=<OPENAI_OAUTH_CLIENT_ID>`
- `redirect_uri=<OPENAI_OAUTH_REDIRECT_URI>`
- `code_verifier=<pkce_code_verifier>`

4. Stores encrypted credentials in provider settings (`auth_type="oauth"`)
5. Redirects to SPA with result:
   - success: `.../dashboard/settings?openai_oauth=success`
   - error: `.../dashboard/settings?openai_oauth=error`

---

## Credential Storage Model

Stored as `ProviderSettings` in DynamoDB:

- `pk = User#<email>`
- `sk = ProviderSettings#OpenAI`
- `auth_type = oauth`
- `encrypted_credentials = <encrypted json>`

Credential JSON schema (`OpenAICredentials` pydantic model):

- `access_token`
- `refresh_token`
- `expires_at` (ISO timestamp)
- `account_id` (best-effort metadata)
- `id_token` (optional)
- `scope` (optional)
- `token_type` (optional)

All credentials are encrypted at rest.

---

## Refresh Token Flow

When token is expired or close to expiry:

`POST https://auth.openai.com/oauth/token`

Form body:

- `grant_type=refresh_token`
- `refresh_token=<stored_refresh_token>`
- `client_id=<OPENAI_OAUTH_CLIENT_ID>`

Returned token set replaces stored credentials atomically (including rotated refresh token).

---

## Runtime Inference Provider (`src/llm/providers/openai.py`)

### Endpoint

Runtime sends inference to:

- `settings.openai_oauth_responses_url`
- default: `https://chatgpt.com/backend-api/codex/responses`

### Request payload requirements (critical)

For ChatGPT/Codex backend, this payload shape is required:

- `instructions` must be present
- `store` must be `false`
- `stream` must be `true`

Example payload:

```json
{
  "model": "gpt-5.4",
  "instructions": "You are a helpful assistant.",
  "store": false,
  "stream": true,
  "input": [
    {
      "role": "user",
      "content": [
        { "type": "input_text", "text": "Hello" }
      ]
    }
  ]
}
```

### Role-aware content mapping

We must send different text block types by role:

- `user` -> `input_text`
- `assistant` -> `output_text`

If assistant history is sent as `input_text`, backend returns:

- `Invalid value: 'input_text'. Supported values are: 'output_text' and 'refusal'.`

### Streaming response parsing

We parse SSE events such as:

- `response.output_text.delta` -> text streaming
- `response.output_item.added` -> tool call registration
- `response.function_call_arguments.delta/done` -> tool args
- `response.completed` -> stop event

---

## Model Strategy

We do not fetch models from `GET /v1/models` for this OAuth flow.

Reason:

- OAuth token from ChatGPT/Codex is not a standard Platform API-key surface.
- We use an environment-driven allowlist of known-compatible model IDs.

Current default list:

- `gpt-5.4`
- `gpt-5.3-codex`
- `gpt-5.2-codex`
- `gpt-5.2`
- `gpt-5.1-codex-max`
- `gpt-5.1-codex-mini`

Also implemented:

- backend fallback if an old/stale agent model (for example `gpt-4.1`) is encountered
- fallback model = first configured OpenAI model from settings

---

## Environment Variables

Main variables:

- `OPENAI_OAUTH_CLIENT_ID`
- `OPENAI_OAUTH_SCOPES` (default `openid profile email offline_access`)
- `OPENAI_OAUTH_ID_TOKEN_ADD_ORGANIZATIONS`
- `OPENAI_OAUTH_CODEX_CLI_SIMPLIFIED_FLOW`
- `OPENAI_OAUTH_ORIGINATOR`
- `OPENAI_OAUTH_REDIRECT_URI`
- `OPENAI_OAUTH_RESPONSES_URL`
- `OPENAI_MODELS` (comma-separated or JSON list)

Environment-specific variants are supported in `.envrc`:

- `LOCAL_*`
- `DEV_*`
- `PROD_*`

---

## Common Errors and What They Mean

### 1) Redirect URI mismatch

Error:

- `redirect_uri does not match pre-registered redirect urls`

Cause:

- `OPENAI_OAUTH_REDIRECT_URI` does not match OAuth client registration exactly.

---

### 2) Unsupported model

Error:

- `The 'gpt-4.1' model is not supported when using Codex with a ChatGPT account.`

Cause:

- Stale or incompatible model ID.

Fix:

- Use configured compatible model list.
- Keep runtime fallback enabled.

---

### 3) Missing payload requirements

Errors:

- `Instructions are required`
- `Store must be set to false`
- `Stream must be set to true`

Cause:

- Codex backend contract not met.

---

### 4) Wrong content block type

Error:

- `Invalid value: 'input_text'. Supported values are: 'output_text' and 'refusal'.`

Cause:

- Assistant history encoded with wrong content block type.

Fix:

- Use role-aware mapping (`assistant -> output_text`).

---

## Security Notes

- PKCE (`S256`) is mandatory.
- OAuth state is encrypted/signed and validated on callback.
- Tokens are encrypted before DynamoDB storage.
- Refresh token updates are persisted atomically.
- OpenAI credentials are marked as `auth_type="oauth"` to separate from API key providers.

---

## Final Result

With this design, users can:

- connect OpenAI via ChatGPT/Codex OAuth from Settings,
- avoid API key management,
- run inference through OAuth-backed Codex endpoint,
- and keep provider credentials securely managed server-side.

