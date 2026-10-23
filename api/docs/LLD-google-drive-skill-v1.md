# Low Level Design: Google Drive Skill v1

| Field | Value |
| --- | --- |
| Status | ✅ Implemented (live Google write verification pending) |
| Owner | InnomightLabs API |
| Last reviewed | 2026-10-22 |
| Depends on | Existing GoogleDrive OAuth connection, Drive v3 API, skill registry |

Original design date: 2026-03-16.

## Implementation notes (2026-10-22)

The original v1 proposal below is retained as historical design context. The skill now exposes
`search`, `read`, `create`, `update` (alias `modify`), and `delete` (trash only).
Credentials are account-scoped: actions reuse `_get_access_token(context)`, which loads
`ProviderSettings#GoogleDrive` through `account_of(context)` and the existing token-refresh helper.
The owner/user-scoping statements below describe the original design, not the current credential lookup.
No OAuth, settings, platform, or frontend changes are required for these write actions. Google must
have granted a write-capable Drive scope, and the connected account must have permission on the target;
Google permission/scope failures are surfaced without widening or replacing credentials.

### Write contract and decisions

- Arguments live in `api/src/skills/google_drive/models.py`; Pydantic rejects unknown fields, blank
  names/ids, invalid types, unsupported creation MIME types, and empty updates before OAuth or HTTP.
- `create` requires `name`; optional fields are `content`, `mime_type` (default `text/plain`),
  `description`, and one `parent_folder_id`. The parent is sent as `parents: [id]`; omitting it uses
  Drive's default destination. Names/ids are trimmed; content/description whitespace is preserved.
- Text content is UTF-8. Supported media types are `text/*` with a valid simple MIME subtype, plus
  exactly `application/json`, `application/xml`, `application/javascript`,
  `application/x-javascript`, `application/rtf`, `application/x-sh`, and `application/sql`.
  The caller supplies the serialized content; the skill does not validate JSON/XML/RTF syntax.
- Text creation uses `POST /upload/drive/v3/files?uploadType=multipart` with a `multipart/related`
  JSON metadata part and a UTF-8 media part. Omitted content creates an empty text file.
- `application/vnd.google-apps.document` creation imports supplied content as `text/plain` while
  setting the target metadata MIME type to Google Docs. Omitted content creates a blank Doc through
  metadata-only `POST /drive/v3/files`. This is plain-text import, not rich-text/structured Docs editing.
- `application/vnd.google-apps.folder` creation uses metadata-only `POST /drive/v3/files`; any
  non-null content, including an empty string, is rejected. Other native creation types are unsupported.
- `update`/`modify` requires `file_id` and at least one of `name`, `description`, or `content`.
  Omitted fields stay unchanged. Explicit null update fields are invalid. An empty description clears
  it; empty content clears a supported text file. A name must remain nonblank.
- Metadata-only updates use `PATCH /drive/v3/files/{id}` and work for native files, folders, and binary
  files too, subject to Google permissions. They never download or replace the file body.
- Content replacement first fetches the stored MIME type. Only the text-like types above are accepted;
  then one multipart `PATCH /upload/drive/v3/files/{id}?uploadType=multipart` sends both requested
  metadata changes and the entire replacement body. Unsupported/missing MIME types fail before any
  mutation, including when a rename was supplied in the same request. No caller-supplied MIME override.
- **Native Google Docs/Sheets/Slides, folders, shortcuts, PDFs, and arbitrary binary bodies cannot be
  replaced here.** Drive media update is not treated as an editor for native documents. No append,
  partial edits, formatting, file moves, MIME changes, sharing/permissions, binary uploads, or resumable
  uploads are implemented. Native body editing needs a dedicated Google editor API integration.
- Writes retain explicit 30-second HTTP timeouts, bearer-token authentication, `supportsAllDrives`,
  and bounded 400-character Google error previews. Results return the existing compact file summary
  with entry id, name, MIME type, parents and web link when Google supplies them. Transport errors
  propagate; there are no automatic retries that could duplicate creates.

Examples:

```json
{"action":"create","arguments":{"name":"notes.txt","content":"Meeting notes\n","parent_folder_id":"folder-id"}}
{"action":"create","arguments":{"name":"Meeting notes","mime_type":"application/vnd.google-apps.document","content":"Plain-text import"}}
{"action":"create","arguments":{"name":"Reports","mime_type":"application/vnd.google-apps.folder"}}
{"action":"modify","arguments":{"file_id":"text-file-id","content":"Full replacement","description":"Updated"}}
{"action":"update","arguments":{"file_id":"google-doc-id","name":"Renamed Doc"}}
```

### Validation

`api/tests/test_google_drive_skill_writes.py` covers argument validation before OAuth, manifest
registration/alias dispatch, actual multipart request encoding, text and native creation, Unicode and
empty content, metadata-only updates, stored-MIME rejection without mutation, OAuth failures, and
bounded Google errors for writes and metadata fetches. Existing action and OAuth tests remain unchanged.

Commands from `api/`:

```bash
uv run pytest tests/test_google_drive_skill_actions.py tests/test_google_drive_skill_writes.py tests/test_google_drive_oauth.py -q
uv run ruff check src/skills/google_drive/actions.py src/skills/google_drive/models.py tests/test_google_drive_skill_writes.py
uv run mypy src/skills/google_drive/actions.py src/skills/google_drive/models.py tests/test_google_drive_skill_writes.py
uv run mypy --follow-imports=silent src/skills/google_drive/actions.py src/skills/google_drive/models.py tests/test_google_drive_skill_writes.py
uv run pytest -q
```

Focused Drive tests: **93 passed**. Ruff passed. Scoped mypy with `--follow-imports=silent` passed
for all three changed Python files; this suppresses diagnostics from imported, out-of-scope modules.

Live Google writes have not been exercised. The full API suite hit a 180-second execution limit at
roughly 51% with no failures shown before timeout. Mypy also traverses imported modules; unrelated
errors in `src/auth/app_tokens.py` and `src/llm/providers/gemini.py` prevent a clean project-context run.

### Related documentation

- [Skill development guide](../src/skills/CONTRIBUTION.md)
- [Skill manifest contract](../src/skills/SKILL_MANIFEST.md)

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
- Update [`spa/src/pages/dashboard/AgentDetail.tsx`](../../spa/src/pages/dashboard/AgentDetail.tsx) to:
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
