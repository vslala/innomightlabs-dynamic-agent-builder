# Low Level Design: OpenAI OAuth Provider (Backend-Owned PKCE)

Date: 2026-03-09  
Status: Draft  
Owner: InnomightLabs API

## Summary
This change adds OpenAI as a first-class LLM provider using backend-owned OAuth PKCE instead of user-supplied API keys.

The backend now:
- Starts OAuth with `POST /auth/openai/start`
- Stores PKCE session state in a short-lived signed/encrypted httpOnly cookie
- Handles callback at `GET /auth/openai`
- Exchanges code for tokens and persists encrypted credentials in `ProviderSettings` with `auth_type="oauth"`
- Refreshes tokens before model listing and inference when near expiry

The SPA now renders a dedicated OpenAI connect/reconnect/disconnect card in Settings.

## Route Contracts

### `POST /auth/openai/start`
Auth: required (`Authorization: Bearer <jwt>`)  
Body:
```json
{
  "return_to": "https://app.example.com/dashboard/settings"
}
```
Response:
```json
{
  "authorize_url": "https://auth.openai.com/oauth/authorize?..."
}
```
Behavior:
- Generates `state`, `code_verifier`, `code_challenge`
- Stores encrypted cookie `openai_oauth_pkce` with:
  - `state`
  - `code_verifier`
  - `user_email`
  - `return_to`
  - `expires_at`

### `GET /auth/openai`
Public callback endpoint.  
Query params: `code`, `state`, `error`

Behavior:
- Validates cookie and state
- Exchanges code at `https://auth.openai.com/oauth/token`
- Saves provider settings:
  - `provider_name = OpenAI`
  - `auth_type = oauth`
  - `encrypted_credentials` JSON payload with:
    - `access_token`
    - `refresh_token`
    - `expires_at` (ISO timestamp)
    - `account_id` (best effort from token payload)
    - `id_token` (optional)
    - `scope`
    - `token_type`
- Redirects to `${return_to}?openai_oauth=success|error`

## Provider Settings Contract
`ProviderSettings` now includes:
- `auth_type: "api_key" | "oauth"` (defaults to `api_key` for backward compatibility)

OpenAI records use `auth_type="oauth"`.

## Runtime Token Refresh
`ensure_valid_openai_credentials(...)` handles token freshness:
- Checks `expires_at`
- If near expiration and `refresh_token` exists, calls token refresh
- Persists rotated refresh token and updated expiry atomically
- Returns valid credentials for immediate API call use

Integrated in:
- `KrishnaMiniArchitecture.handle_message(...)`
- `KrishnaMemGPTArchitecture.handle_message(...)`
- `agents` schema endpoint model loading for OpenAI model pickers

## OpenAI Model Listing
Live model listing is fetched from:
- `GET https://api.openai.com/v1/models`

The app uses the current OAuth access token and gracefully falls back to an empty list if unavailable.

## SPA UX
Settings page OpenAI card:
- `Connect` -> calls `POST /auth/openai/start`, redirects browser to returned URL
- `Reconnect` -> same flow as Connect
- `Disconnect` -> deletes `/settings/providers/OpenAI`
- Callback status is read via query param `openai_oauth=success|error`

Bedrock/Anthropic continue using schema-driven credential forms.

## Environment Variables
Backend:
- `OPENAI_OAUTH_CLIENT_ID`
- `OPENAI_OAUTH_SCOPES` (default `openid profile email offline_access`)
- `OPENAI_OAUTH_ID_TOKEN_ADD_ORGANIZATIONS`
- `OPENAI_OAUTH_CODEX_CLI_SIMPLIFIED_FLOW`
- `OPENAI_OAUTH_ORIGINATOR`
- `OPENAI_OAUTH_REDIRECT_URI`

Terraform variables were added to pass these into Lambda env.

## Cookie Security
OAuth PKCE cookie settings:
- `HttpOnly=true`
- `SameSite=lax`
- `Secure=true` outside `dev/local`
- `Max-Age=600`
- Path scoped to `/auth/openai`

## Safety Notes
- Account ID extraction from access token is non-authoritative metadata only.
- OpenAI OAuth authorize parameter contract is environment-driven to avoid hardcoded coupling.
- Manual `POST /settings/providers/OpenAI` is rejected; OpenAI setup must go through OAuth.
