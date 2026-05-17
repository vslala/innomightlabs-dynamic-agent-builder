# Low Level Design: Google Mail Skill Actions

Date: 2026-05-06  
Status: Implemented  
Owner: InnomightLabs API

## Summary
The `google_mail` skill implements the actions declared in `src/skills/google_mail/manifest.yml`:
- `search`
- `read`
- `delete`
- `batch_delete`
- `archive`
- `mark_read`
- `mark_unread`

The implementation keeps skill-specific behavior in `src/skills/google_mail/`. It shares only generic application infrastructure: `ProviderSettingsRepository`, encrypted credential storage, app settings for the Google OAuth client, and `httpx`.

## Skill Boundary
Skill-owned files:
- `src/skills/google_mail/actions.py`: Gmail API calls, body/header extraction, credential refresh orchestration.
- `src/skills/google_mail/models.py`: Gmail credential and action argument models.
- `src/skills/google_mail/oauth.py`: Gmail OAuth state, authorization URL, token exchange, and credential persistence helpers.
- `src/skills/google_mail/manifest.yml`: action contracts and OAuth provider name.

External dependencies intentionally kept minimal:
- `src.settings.repository.ProviderSettingsRepository` to load owner-scoped OAuth credentials.
- `src.crypto.decrypt/encrypt` to read and persist encrypted credentials.
- `src.config.settings` for Google OAuth client credentials, Gmail scopes, redirect URI, and refresh.
- `src.skills.oauth_providers` for catalog-exposed OAuth start metadata.

## OAuth Connection
Gmail connection uses the same backend-owned Google OAuth pattern as Google Drive. The SPA does not hardcode the OAuth start URL. `GET /skills` returns `oauth_start_path` from provider metadata:

```json
{
  "skill_id": "google_mail",
  "oauth_provider_name": "GoogleMail",
  "oauth_start_path": "/auth/google-mail/start"
}
```

The add-skill UI calls that path generically with `agent_id`, `skill_id`, and `return_to`. The callback redirects with a generic `skill_oauth` status plus provider-specific compatibility params:

```text
?skill_oauth=success&google_mail_oauth=success&agent_id=...&skill_id=google_mail
```

The callback persists encrypted credentials under `ProviderSettings#GoogleMail`.

## Credential Lookup
Runtime receives owner context from `SkillRuntimeService` and resolves:

```python
repo.find_by_provider(owner_email, "GoogleMail")
```

Credentials are validated with `GoogleMailCredentials` from the skill-local models file. If the token is expiring and a refresh token is present, the skill refreshes with `https://oauth2.googleapis.com/token` and saves the updated encrypted credentials back to `ProviderSettings`.

## Actions
`search` calls:

```text
GET https://gmail.googleapis.com/gmail/v1/users/me/messages
```

It supports:
- raw Gmail query text via `query`
- `recent_20` shortcut
- `page_size` clamped to 1-50
- `page_token`
- `start_date` / `end_date` mapped to `after:` / `before:`
- `newer_than` / `older_than`
- sender, recipient, subject, category, labels, unread, attachments, spam/trash inclusion

Search results fetch Gmail metadata for each returned id and include id, thread id, labels, subject, from, to, date, snippet, and next page token.

`read` calls:

```text
GET https://gmail.googleapis.com/gmail/v1/users/me/messages/{message_id}?format=full
```

It returns message ids, labels, common headers, and the decoded body. Multipart payload extraction prefers `text/plain`, then falls back to stripped `text/html`, then snippet text. Output is truncated to `MAX_READ_CHARACTERS`.

Mutating actions use Gmail labels:
- `delete`: `POST .../messages/{message_id}/trash`
- `batch_delete`: `POST .../messages/batchModify` with `addLabelIds=["TRASH"]` and `removeLabelIds=["INBOX"]`, chunked up to 1000 ids per request. This keeps the action non-permanent and compatible with the `gmail.modify` scope.
- `archive`: `POST .../messages/{message_id}/modify` with `removeLabelIds=["INBOX"]`
- `mark_read`: `POST .../messages/{message_id}/modify` with `removeLabelIds=["UNREAD"]`
- `mark_unread`: `POST .../messages/{message_id}/modify` with `addLabelIds=["UNREAD"]`

`batch_delete` validates that at least one message id is provided, strips whitespace from ids, preserves input order, ignores duplicate ids, and reports the duplicate count in the action result. The optional `chunk_size` argument is clamped to Gmail's 1-1000 id batch range. Any failed batch request raises a `RuntimeError` with the Gmail status code and a bounded response preview.

## Configuration
New environment settings:
- `GOOGLE_MAIL_REDIRECT_URI`, defaulting to `/auth/google-mail/callback`
- `GOOGLE_MAIL_OAUTH_SCOPES`, defaulting to `https://www.googleapis.com/auth/gmail.modify`
