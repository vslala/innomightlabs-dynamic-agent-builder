# Contributing to `db/`

Owns DynamoDB connection access: one place that decides region and endpoint, and caches boto3 connections per
thread. Every repository in the API gets its table handle from here. The table itself (single-table design,
`pk`/`sk` plus GSIs) is described in `api/README.md`.

```text
db/
  __init__.py   Exports get_dynamodb_resource, get_dynamodb_client, reset_dynamodb_connections
  dynamodb.py   Thread-local cached resource/client; honours settings.dynamodb_endpoint for local DynamoDB
```

## Conventions

- Repositories do this in `__init__` (see `email/pending_email.py`):
  `self.dynamodb = get_dynamodb_resource(); self.table = self.dynamodb.Table(settings.dynamodb_table)`.
  Never call `boto3.resource("dynamodb")` directly: an uncached resource costs a new connection pool and TLS handshake.
- The cache is per thread (`threading.local`), not global: boto3 resources are not documented thread-safe and some
  repository work runs in `asyncio.to_thread`.
- `settings.dynamodb_endpoint` set means local DynamoDB (dummy credentials); otherwise AWS in `settings.aws_region`.
  See `../LOCAL_DYNAMODB.md`.
- Key design, item shapes and queries belong in the owning module's `repository.py`, not here. Decimal handling is in `src/utils/dynamodb.py`.

## How to add a new connection helper

Only needed for another boto3 service wrapper. Add it in `dynamodb.py` using `_connection_kwargs()` and a new
thread-local attribute, export it from `__init__.py`, and extend `reset_dynamodb_connections()` to clear it.

## Testing

```bash
uv run pytest tests/test_dynamodb_connections.py -q
uv run ruff check src/db && uv run mypy src/db
```

`tests/conftest.py`'s `mock_aws_context` calls `reset_dynamodb_connections()` before and after each test, because
each test has its own moto context and a connection cached under an earlier one must not be reused. The
`dynamodb_table` fixture builds the table.

## Do / Don't

- Do always go through `get_dynamodb_resource` / `get_dynamodb_client`.
- Do call `reset_dynamodb_connections()` in any test that creates its own `mock_aws` context.
- Don't share a resource across threads yourself; don't store it in module globals.
