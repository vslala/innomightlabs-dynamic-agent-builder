# Contributing to `runtime/`

Environment detection for the one process that runs both on Railway and on AWS Lambda. No `__init__.py`; import as
`from src.runtime.env import is_lambda`. Not to be confused with `src/scheduler/runtime.py` (Railway reapers) or
`src/agents/tool_runtime/`.

```text
runtime/
  env.py   is_lambda(): True when AWS_LAMBDA_FUNCTION_NAME is set
```

## Conventions

- Call sites read as `if is_lambda():` instead of `os.getenv(...)` checks scattered about. `main.py` uses it to
  choose CloudWatch JSON logging over the plain formatter.
- This is deliberately not part of `Settings`: it detects where we run, it is not configuration. A value an
  operator chooses belongs in `src/config/settings.py`.

## How to add a check

Add a small boolean function to `env.py` with a docstring and one env lookup. Add it only when two call sites need it.

## Testing

```bash
uv run ruff check src/runtime && uv run mypy src/runtime
```

No tests exist. If you add logic, test with `monkeypatch.setenv` / `delenv("AWS_LAMBDA_FUNCTION_NAME")`.

## Do / Don't

- Do keep functions to a single env lookup.
- Don't branch on `is_lambda()` deep in domain code when a setting would do; the Railway API is the primary runtime.
