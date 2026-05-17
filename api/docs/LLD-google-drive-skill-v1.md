# Low Level Design: Google Drive Skill v1

Date: 2026-03-16  
Status: Draft  
Owner: InnomightLabs API

## Summary
This change adds a first-party Google Drive skill with owner-scoped OAuth credentials and three initial actions:
- `search`
- `read`
- `delete` (trash only)

The skill is installed per agent, but Google Drive access is stored per user in `ProviderSettings` under `provider_name="GoogleDrive"` with encrypted OAuth credentials. Runtime always resolves Drive credentials from the agent owner.

## Backend Changes

### OAuth flow
- Add `api/src/auth/google_drive_oauth.py` with:
  - `GoogleDriveCredentials`
  - `GoogleDriveOAuthState`
  - encrypted state encode/decode helpers
  - auth code exchange
  - token refresh
  - `ensure_valid_google_drive_credentials(...)`
- Add routes in `api/src/auth/router.py`:
  - `POST /auth/google-drive/start`
  - `GET /auth/google-drive/callback`
- Reuse Google client id/secret but add:
  - `GOOGLE_DRIVE_REDIRECT_URI`
  - `GOOGLE_DRIVE_OAUTH_SCOPES`

### Skill metadata and install guards
- Extend `SkillManifest` and `SkillCatalogItemResponse` with OAuth metadata.
- Return `oauth_connected` from `GET /skills` based on the signed-in user.
- Block installing `google_drive` unless the installing user has `ProviderSettings#GoogleDrive`.

### Runtime execution
- Pass `owner_email` through skill runtime context in `SkillRuntimeService.handle_tool_call(...)`.
- Drive handlers load provider settings using `owner_email`, not `actor_email`.

### Google Drive skill files
- `api/src/skills/google_drive/manifest.yml`
- `api/src/skills/google_drive/actions.py`

Implemented actions:
- `search`: Drive `files.list`
- `read`: Google Docs export, text-like file download, PDF extraction
- `delete`: `trashed=true` patch

## SPA Changes
- Update [`spa/src/pages/dashboard/AgentDetail.tsx`](/Users/vslala/src/code/projects/innomightlabs/innomightlabs-prod/spa/src/pages/dashboard/AgentDetail.tsx) to:
  - surface OAuth-backed skills in the add-skill dialog
  - show `Connect Google Drive` when the skill is not yet connected
  - redirect to Google OAuth via `POST /auth/google-drive/start`
  - handle callback query params and auto-install the skill on success

## Read Behavior
- Supported:
  - Google Docs via text export
  - text-like MIME types via download + UTF-8 decode with replacement
  - PDFs via `pypdf`
- Not supported:
  - arbitrary binary file content
- Response includes file metadata and extracted text.
- Extracted text is truncated to a safe max length.

## Test Coverage
- OAuth start returns a Google authorize URL with encoded state.
- OAuth callback persists `ProviderSettings#GoogleDrive`.
- Token refresh updates stored credentials.
- Skill catalog reports OAuth requirements and connection status.
- Install fails before OAuth and succeeds after OAuth.
- Runtime actions use owner credentials.
- `read` supports docs/text/PDF and rejects unsupported binaries.
- `delete` trashes files rather than permanently deleting them.
