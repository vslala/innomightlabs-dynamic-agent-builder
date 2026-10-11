# Contributing to `email/`

Owns outbound email through Mailjet: transactional lifecycle emails (welcome, subscription, payment failed), the
guest transcript, and plain text-first messages (contact enquiries). Other modules call the `*_safe` helpers or
`send_email`; they never talk to Mailjet directly. Jinja templates live in `api/assets/templates/emails/`.

```text
email/
  __init__.py       `send_email` (plain text + optional html; returns bool) and public re-exports
  service.py        EmailService (Mailjet client, `{{var}}` substitution into templates) and EmailTemplate enum
  helpers.py        The `*_safe` functions: look up user, build variables, send, enqueue a retry on failure
  pending_email.py  EmailType enum, PendingEmail and PendingEmailRepository (failed sends, TTL 1 day)
  message.py        MessageEmail / EmailLink dataclasses and the Jinja environment (StrictUndefined, autoescape)
assets/templates/emails/   _layout.html, message.html (Jinja) and the per-email HTML files
```

## Conventions

- **Always send through a `*_safe` helper** in `helpers.py` for lifecycle emails: it catches errors, logs, and on
  failure calls `_handle_email_failure`, which writes a `PendingEmail` for retry. Callers (webhooks, signup) never
  see an exception. `send_guest_transcript_email_safe` is the exception: one attempt only, because the guest closer
  in `src/widget` owns bounded retries; do not enqueue guest data as `PendingEmail`.
- Two template systems coexist. Lifecycle emails use `EmailService.send_email(..., EmailTemplate, variables)` with
  `{{name}}` placeholders replaced by plain string substitution (no escaping). Text-first emails use `MessageEmail`
  (`.html()` and `.text()`), rendered by Jinja with `autoescape` and `StrictUndefined`, extending `_layout.html`;
  prefer this for anything containing a user's own words.
- Pending emails: `pk = sk = PENDING_EMAIL#{email_id}`, `created_at` stored as a string, `ttl` attribute for
  expiry. Nothing in `src` currently drains `list_all`; verify before assuming retries happen.
- Config: `settings.mailjet_api_key`, `settings.mailjet_secret_key`, `settings.frontend_url` (links). Sender is
  `noreply@innomightlabs.com`.
- Errors: `send_email` and `EmailService.send_email` return `bool` and swallow exceptions; `PendingEmailRepository`
  logs and re-raises on write failures.

## How to add a lifecycle email

1. Add `assets/templates/emails/<name>.html` (copy `welcome.html`).
2. Add a member to `EmailTemplate` in `service.py` and to `EmailType` in `pending_email.py`.
3. Add `send_<name>_email_safe` to `helpers.py`, following `send_welcome_email_safe`: build `template_variables`, send,
   and on failure call `_handle_email_failure`. Export it in `__init__.py`.
4. Call it from the owning flow (for example `src/payments`), not the other way round.

For a plain message email, build a `MessageEmail` and call `send_email(to, subject, m.text(), html=m.html())` as
`src/contact/router.py` does; add a new Jinja template only if `message.html` cannot express it.

## Testing

```bash
uv run pytest tests/test_widget_guest_email.py tests/test_contact_enquiry.py -q
uv run ruff check src/email && uv run mypy src/email
```

Patch `Client` (Mailjet) or `send_email` rather than calling the network. Use the `dynamodb_table` fixture (moto)
for `PendingEmailRepository` tests, and assert the pending item exists after a forced failure.

## Do / Don't

- Do use `*_safe` helpers; don't call `EmailService` from routers or webhooks.
- Do pass the plain-text part alongside HTML.
- Don't put user-supplied text through `_replace_variables`; use `MessageEmail`.
- Don't add a Jinja variable without supplying it (`StrictUndefined` raises).
