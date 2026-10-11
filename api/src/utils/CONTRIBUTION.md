# Contributing to `utils/`

Holds the DynamoDB number conversion helpers. There is no `__init__.py`; import as `from src.utils.dynamodb import ...`.
Keep it this small: a helper only belongs here if several domains need it and no domain owns it.

```text
utils/
  dynamodb.py   convert_decimals (Decimal to int/float, recursive), convert_floats_to_decimals (inverse)
```

## Conventions

- DynamoDB returns every number as `Decimal` and rejects Python `float` on write. Run `convert_decimals` on items
  read for JSON responses, and `convert_floats_to_decimals` on anything derived from `model_dump(mode="json")`
  before `put_item`.
- Both are pure and recursive over dicts and lists; `convert_floats_to_decimals` goes through `Decimal(str(x))` to
  avoid binary float noise.
- Boundary rule: convert in the repository (read or write), not in routers or models.

## How to add a helper

Add a pure function to `dynamodb.py` if it is DynamoDB-specific; otherwise prefer the module that uses it, or
`src/common/` for cross-domain helpers (see `src/common/CONTRIBUTION.md`). Do not create a catch-all.

## Testing

```bash
uv run pytest -q -k "decimal or dynamodb"
uv run ruff check src/utils && uv run mypy src/utils
```

There is no dedicated `tests/test_utils_*.py`. Add one (plain pytest, no moto needed) when you change behaviour.

## Do / Don't

- Do keep helpers pure and typed.
- Don't convert numbers in the router; don't add unrelated utilities here.
