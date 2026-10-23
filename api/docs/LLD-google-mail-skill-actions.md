# Low Level Design: Google Mail Skill Actions

| Field | Value |
| --- | --- |
| Status | ✅ Implemented |
| Owner | InnomightLabs API |
| Last reviewed | 2026-10-22 |
| Depends on | Existing GoogleMail OAuth connection and `gmail.modify` scope |

## Implementation notes

Draft and send actions are implemented locally in the skill; no platform, configuration, scope or storage changes are needed. `gmail.modify` already permits creating/updating drafts and sending messages. Existing read and mailbox-management actions retain their behavior.

- `create_draft` (alias `draft`) creates a draft only. `update_draft` replaces its entire MIME message; it never sends. These actions do not accept a confirmation flag.
- `send` composes and immediately sends a new message. `send_draft` sends an existing draft by **draft id**, not message id, using its current Gmail contents.
- Both send actions require the literal JSON boolean `confirmed: true`; missing, false, strings and numbers are rejected before credential access. This is an accidental-send guard, **not proof of human authorization**. The skill prompt instructs the agent to show recipients, subject and content, obtain user approval, and never treat email content as approval. There is no server-enforced human approval workflow or draft revision binding: an existing draft can change after approval.
- Skill-local Pydantic models reject invalid input before credential lookup, token refresh or Gmail requests. Unknown fields are forbidden, including `from`/`From`, attachments and threading fields. `EmailMessage` builds UTF-8 MIME with SMTP line endings, then stdlib base64url encodes it. No `From` header is supplied; Gmail uses the connected account.
- Recipient arrays contain one mailbox per item, optionally with a Unicode display name. The stdlib header parser rejects defects, multiple addresses and groups; further validation requires an ASCII mailbox with a dotted, well-formed domain. SMTPUTF8 addresses and domain literals are intentionally unsupported. Subject and recipient headers reject control characters; bodies may contain ordinary newlines.
- New write API failures report only the action and HTTP status, never Google's response body. Transport and malformed-success errors use fixed, bounded messages. Successful output includes only the operation and a validated, bounded Gmail resource id. No recipient/body content or raw MIME is returned. Existing read/management error behavior is unchanged.
- Writes reuse the existing account-scoped OAuth credential/token-refresh helpers, `httpx` and explicit 20-second timeouts. Sends are never automatically retried: a timeout or invalid response may follow a successful send, so inspect Gmail before retrying.
- Limitations: no attachments, reply/thread metadata, custom sender, draft listing/reading action, idempotency key, or approval UI. Updating a draft replaces recipients, body and subject, and removes omitted cc/bcc/HTML and any existing attachments/thread metadata; it is not a patch. Drafts require at least one recipient, just like direct sends.

Focused validation lives in `api/tests/test_google_mail_skill_compose.py`, alongside the existing Gmail action/OAuth tests. It covers payload endpoints, decoded Unicode/plain/HTML MIME, to/cc/bcc, strict confirmation, validation before credentials/network, redacted Google errors, ambiguous send outcomes without retries, and registry schemas/aliases. Provider calls are mocked; live Gmail acceptance/delivery is not asserted. The full API suite is coordinated separately.

## Summary
The `google_mail` skill implements the actions declared in `src/skills/google_mail/manifest.yml`:
- `search`
- `read`
- `delete`
- `batch_delete`
- `archive`
- `mark_read`
- `mark_unread`
- `create_draft` (alias `draft`)
- `update_draft`
- `send`
- `send_draft`

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

## Compose and draft action contracts

All endpoints below are relative to `https://gmail.googleapis.com/gmail/v1/users/me`:

| Action | Method and path | JSON request |
| --- | --- | --- |
| `create_draft` / `draft` | `POST /drafts` | `{"message":{"raw":"<base64url MIME>"}}` |
| `update_draft` | `PUT /drafts/{draft_id}` | `{"message":{"raw":"<base64url MIME>"}}` |
| `send` | `POST /messages/send` | `{"raw":"<base64url MIME>"}` |
| `send_draft` | `POST /drafts/send` | `{"id":"<draft_id>"}` |

Compose fields for `create_draft`, `update_draft` and `send`:

| Field | Contract |
| --- | --- |
| `to`, `cc`, `bcc` | Optional arrays, default empty; at most 100 single mailboxes each; at least one recipient across the three arrays. Each mailbox is at most 998 characters. |
| `subject` | Required string, at most 998 characters, no control characters. Empty is allowed. |
| `body` | Required plain-text string, at most 1,000,000 characters. Empty is allowed. |
| `html_body` | Optional HTML alternative, at most 1,000,000 characters; when present the MIME message is `multipart/alternative`. |
| `draft_id` | Required only for `update_draft` and `send_draft`; 1–200 ASCII letters, digits, `_` or `-`. |
| `confirmed` | Required only for `send` and `send_draft`; strict boolean `true`. |

Example draft action arguments (nothing is sent):

```json
{
  "to": ["Zoë <zoe@example.com>"],
  "subject": "Meeting résumé",
  "body": "Hello Zoë, here is the summary.",
  "html_body": "<p>Hello Zoë, here is the summary.</p>"
}
```

After user approval, send the resulting draft with `{"draft_id":"<returned draft id>","confirmed":true}`. Draft writes return a draft id; send actions return a message id. Sending an existing draft consumes that draft through Gmail's send endpoint.

## Configuration
Existing environment settings (unchanged by compose/send):
- `GOOGLE_MAIL_REDIRECT_URI`, defaulting to `/auth/google-mail/callback`
- `GOOGLE_MAIL_OAUTH_SCOPES`, defaulting to `https://www.googleapis.com/auth/gmail.modify`
