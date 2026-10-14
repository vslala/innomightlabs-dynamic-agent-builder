# Contributing to `common/`

Small helpers and constants shared by several domains that no single domain owns: pagination, SSE, time, an SSRF-safe
HTTP client, shared limits. The loose top-level files of `src/` (errors, encryption, form schema types, logging
format) are documented at the end of this file.

```text
common/
  __init__.py     Re-exports Paginated, PaginationParams, as_aware_utc and the constants
  constants.py    CAPACITY_WARNING_THRESHOLD, COMPACTION_TARGET, DEFAULT_PAGE_SIZE, MAX_PAGE_SIZE, MAX_TOOL_ITERATIONS
  pagination.py   PaginationParams, Paginated[T], encode_cursor / decode_cursor, InvalidCursor
  sse.py          sse_response(events): StreamingResponse with SSE headers
  time.py         as_aware_utc(): naive datetime is UTC; aware is converted to UTC
  outbound.py     async_client() / sync_client(): httpx clients that refuse non-public destinations
```

## Conventions

- **Cursors.** DynamoDB `LastEvaluatedKey` is base64 JSON. `decode_cursor(cursor, key_names=("pk","sk"))` accepts only
  those exact string keys (pass the GSI key names for index queries) and raises `InvalidCursor`, which
  `src/exceptions.py` maps to 400. Repositories decode, routers return `Paginated[...]`. Examples:
  `src/messages/repositories/dynamodb.py`, `src/knowledge/repository.py`.
- **Outbound HTTP.** Any URL supplied by a user, agent or skill config must go through `outbound.async_client()` or
  `sync_client()`. They resolve the host, reject non-public addresses, connect to the checked address (rebinding
  safe), check each redirect, and ignore env proxies. Blocked connects surface as `httpx.ConnectError`. Tests: `tests/test_outbound.py`.
- **Staleness checks** use `as_aware_utc` so naive and aware stored timestamps can be subtracted.
- Streaming routes return `sse_response(...)` (see `src/agents/router.py`).

## How to add a helper

Add it only when a second domain needs it; otherwise keep it in the first one. New file or function here, re-export
from `__init__.py` only if widely used, and add a `tests/test_<name>.py`. A new constant goes in `constants.py` with a
comment on units/meaning.

## Testing

```bash
uv run pytest tests/test_outbound.py tests/test_crypto.py tests/test_form_options.py -q
uv run ruff check src/common src/exceptions.py && uv run mypy src/common
```

## Do / Don't

- Do use `decode_cursor`/`encode_cursor` for every paginated DynamoDB list; don't invent cursor formats.
- Do use `outbound` clients for untrusted URLs; don't use bare `httpx.AsyncClient` for them.
- Don't add domain logic here, and don't let `common` import from domain modules.

## Shared top-level files in `src/`

```text
src/
  exceptions.py        register_exception_handlers(app), UserFacingError, client_error_message, GENERIC_ERROR_MESSAGE
  crypto.py            Fernet encrypt/decrypt; encrypt_secret_fields / decrypt_secret_fields driven by a Form
  form_models.py       Schema-driven form types: Form, FormInput, FormInputType, SelectOption, validation and options models
  form_options.py      hydrate_form_options / validate_form_options; one resolver per FormOptionSourceType
  form_validation.py   validate_submission (every problem at once), validate_form_value (formats, limits, options, upload ids), parse_email_list
  logging_config.py    CloudWatchJsonFormatter, configure_cloudwatch_logging (Lambda); see src/logging for the rest
```

- **`exceptions.py`.** Registered once in `main.py`. `HTTPException` gives `{detail, path}`; validation errors give
  422 with `errors`; `InvalidCursor` gives 400; anything else gives 500 with `GENERIC_ERROR_MESSAGE` and the
  `request_id`, with the real exception only in logs. To show a message to the user, raise `UserFacingError`
  (or a subclass) with text written for them; check with `client_error_message(exc)`. Never put raw provider or DynamoDB text in a response.
- **`crypto.py`.** Key is derived (PBKDF2) from `ENCRYPTION_KEY`, falling back to `JWT_SECRET`; changing either makes
  stored values undecryptable. Secret form fields (`FormInputType` password-style) are encrypted before storage and
  decrypted on use; do not log them.
- **Forms.** Schemas are built in the owning domain (for example `knowledge/schemas.py`) from `form_models.py`,
  served at `GET /<resource>/{id}/forms/<form-name>`. Keep field `name`s stable. A new `FormInputType` must be added
  in the SPA too. Dynamic choices: set `FormOptionsSource` with a `FormOptionSourceType` value, add a resolver in
  `form_options.py` and register it in `FORM_OPTIONS_RESOLVERS`; dependent fields use `options_filter=FormOptionsFilter(...)`
  and `validate_form_options` rejects mismatched pairs. Tests: `tests/test_form_options.py`, `tests/test_crypto.py`.
- **`logging_config.py` vs `src/logging/`.** The former is the Lambda JSON formatter, the latter the default setup;
  `main.py` picks one with `is_lambda()`.
