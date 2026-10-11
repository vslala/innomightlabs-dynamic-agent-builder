# Contributing to `contact/`

Owns the two public contact forms: `innomightlabs.com` (`POST /contact/submit`) and `innomight.com`
(`POST /contact/enquiry`). Both run one pipeline: an issue in a private GitHub enquiries repo, an email to the
site's inbox, and a confirmation to the sender. The routes are public (no auth), so the IP rate limit is the guard.

```text
contact/
  router.py          Routes, both request models, ContactSite constants, the shared record_enquiry pipeline, email content
  github_service.py  GitHubService.create_issue: httpx call to the GitHub issues API (ENQUIRIES_REPO)
```

## Conventions

- No repository or DynamoDB item: the GitHub issue is the record. Rate-limit state lives in `src/rate_limits`.
- Each form is a Pydantic model that satisfies the `ContactEnquiry` Protocol in `router.py` (`category`,
  `category_name`, `greeting_name`, `message`, `issue_title`, `issue_body`, `details`). `record_enquiry` only
  knows the Protocol, so the pipeline has no per-form `if`.
- Order matters: acquire `RateLimiter(CONTACT_RATE_LIMIT)` first (one submission per 5 minutes per IP, shared by
  both forms); creating the issue is fatal (502, and `limiter.release(decision)` so the sender can retry); the two
  emails are not fatal (log a warning, still return success).
- Emails use `MessageEmail` from `src/email/message.py` and `send_email` from `src/email`. Do not build HTML here.
- Errors are `HTTPException` (429, 502). The 502 detail points the sender at the site's inbox.
- `Enquiry.website` is a honeypot: a filled value returns the normal success response without doing any work.
- Config: `settings.github_token` (`GITHUB_TOKEN`, see `src/config/CONTRIBUTION.md` for adding variables).
  The repo owner and `ENQUIRIES_REPO` are constants in `github_service.py`; enquiries carry personal data, so keep
  them in a private repo.

## How to add a third contact form (or a new category)

- New category: add it to `ContactCategory` and `CONTACT_CATEGORY_NAMES` (or `EnquiryTopic` and `ENQUIRY_TOPIC_NAMES`)
  in `router.py`, and check the SPA/www form sends the new value.
- New form: add a `ContactSite` constant (label, name, inbox, url), a Pydantic model implementing the Protocol
  properties, and a route that calls `record_enquiry(model, SITE, request)`. Copy `Enquiry` / `submit_enquiry`.

## Testing

```bash
uv run pytest tests/test_contact_enquiry.py -q
uv run ruff check src/contact && uv run mypy src/contact
```

`tests/test_contact_enquiry.py` patches `src.contact.router.GitHubService.create_issue` (`AsyncMock`) and
`src.contact.router.send_email`; no network and no moto needed beyond the `test_client` fixture. Cover: success,
GitHub failure (502 and slot released), email failure (still 200), the honeypot, and the 429 cooldown.

## Do / Don't

- Do release the rate-limit slot when the work fails; do not release it after the issue exists.
- Do keep per-form wording in the model properties, shared flow in `record_enquiry`.
- Don't send email other than through `send_email` / `MessageEmail`, and don't log the message body.
- Don't make email failure fail a submission once the issue is recorded.
