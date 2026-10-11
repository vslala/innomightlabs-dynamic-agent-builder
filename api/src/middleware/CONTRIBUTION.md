# Contributing to `middleware/`

Holds app-wide Starlette middleware that is not domain specific. Today that is one class: request id handling.
No `__init__.py`; import as `from src.middleware.request_id import RequestIdMiddleware`. Auth and rate-limit
middleware live with their domains (`src/auth`, `src/rate_limits/middleware.py`).

```text
middleware/
  request_id.py   RequestIdMiddleware: read or create X-Request-Id, set logging context, echo on the response
```

## Conventions

- Registered in `main.py` with `app.add_middleware(...)`. Order matters: the last added runs outermost, so check
  `main.py` before adding one that must see (or not see) the request id.
- Read the incoming `X-Request-Id` or make one (`new_request_id`), store it on `request.state.request_id` and in
  the logging contextvar, and always clear the contextvar in `finally` so it cannot leak into background work.
- `src/exceptions.py` reads `request.state.request_id` (falling back to the contextvar) for 500 responses, so
  the id also appears in error bodies. The unhandled-exception path adds the header itself.
- Built on `BaseHTTPMiddleware`; keep it simple and don't buffer or read bodies.

## How to add a middleware

1. New file here named for what it does, a `BaseHTTPMiddleware` subclass with `dispatch`.
2. Register it in `main.py` and decide its order relative to `RequestIdMiddleware`.
3. Anything that needs domain data (user, subscription) belongs in that domain's module instead.

## Testing

```bash
uv run pytest tests/test_auth_middleware.py -q
uv run ruff check src/middleware && uv run mypy src/middleware
```

Use `test_client` and assert the `X-Request-Id` response header (echoed when sent, generated when absent). There
is no dedicated test for this class yet.

## Do / Don't

- Do clean up per-request context in `finally`.
- Don't put business logic or DynamoDB access in middleware.
- Don't swallow exceptions here; `src/exceptions.py` shapes error responses.
