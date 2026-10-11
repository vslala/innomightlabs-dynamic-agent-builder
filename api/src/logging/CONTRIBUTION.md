# Contributing to `logging/`

Owns local/Railway log setup and request-id propagation into log lines. No `__init__.py`; import with
`from src.logging.request_id import ...` and `from src.logging.config import configure_logging`. The package is
named `logging` under `src`, so inside it always use absolute imports (`import logging` is the stdlib).

```text
logging/
  config.py      configure_logging(): root level from LOG_LEVEL, one line format with [request_id], filter attachment
  request_id.py  ContextVar request id, new_request_id/set_request_id/get_request_id, RequestIdFilter
```

## Conventions

- `main.py` picks the setup once at import: `configure_cloudwatch_logging` (JSON, from `src/logging_config.py`) when
  `is_lambda()`, else `configure_logging()`. Don't configure logging anywhere else.
- Request id lives in a `ContextVar`, so it follows `await`s. `src/middleware/request_id.py` sets it per request and
  clears it in `finally`. `RequestIdFilter` stamps `record.request_id` (`-` when unset); the format string depends on it.
- `configure_logging` does not replace handlers that already exist (uvicorn); it only fills a missing formatter and
  adds the filter.
- Modules log with `log = logging.getLogger(__name__)`. Level comes from the `LOG_LEVEL` env var, read directly here.

## How to add a log field

Set it on the record in a filter (like `RequestIdFilter`), add `%(field)s` to `log_format` in `config.py`, and add it
to `CloudWatchJsonFormatter` in `src/logging_config.py` so both formats agree.

## Testing

```bash
uv run pytest tests/test_auth_middleware.py -q
uv run ruff check src/logging && uv run mypy src/logging
```

No test targets this package directly. Assert on records with pytest's `caplog`; remember `caplog` records carry
`request_id` only when the filter is attached.

## Do / Don't

- Do log with the module logger and `%s` style or f-strings as neighbouring code does; never log credentials or tokens.
- Don't call `set_request_id` outside the middleware (and background jobs that need correlation, clearing afterwards).
- Don't call `logging.basicConfig` in modules.
