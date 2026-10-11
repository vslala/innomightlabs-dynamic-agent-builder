# Contributing to `config/`

Owns every setting the API reads from the environment. `settings.py` defines the `Settings` dataclass, parses env
vars once in `Settings.from_env()`, and exposes a module-level `settings` singleton. Code imports
`from src.config import settings`; it does not call `os.getenv` itself.

```text
config/
  __init__.py   Re-exports settings, Settings, ConfigValidationError
  settings.py   Settings dataclass (fields grouped by feature), from_env(), validate_* methods, A2A normalisers
```

## Conventions

- Add a field to `Settings` with a default where it can have one, then read it in `from_env()` with a default in code.
  Env var names are UPPER_SNAKE of the field (`downloads_manifest_key` is `DOWNLOADS_MANIFEST_KEY`).
- `from_env()` has local helpers: `env_bool`, `parse_env_list`, `parse_env_json_map`, `parse_env_email_list`. Use
  them; cast numbers with `int(os.getenv(NAME, "900"))`.
- Required-ness is per feature, not at import: `validate_core`, `validate_google_oauth`, `validate_pinecone` raise
  `ConfigValidationError(missing_vars, feature)`, called where the feature is used. Add a `validate_<feature>` for a
  feature that cannot work without a value; optional features (Stripe, Mailjet) default to `""`.
- `ENVIRONMENT=dev` additionally reads `client_secret*.json` at the repo root for Google OAuth; never print it.
- Convention over configuration: add a variable only when it genuinely varies per environment. Otherwise make it a
  constant near its use.

## How to add an env var

1. Field in `Settings` (`settings.py`) and the `os.getenv` line in `from_env()`.
2. Railway: `set_railway_var "NAME" "$(get_var_default 'NAME' 'default')"` (or `get_var` for secrets) in
   `scripts/deploy_prod_railway.sh`. Values come from `.envrc`.
3. Local: `export NAME=...` in `scripts/deploy_local.sh`.
4. Lambda event handlers, only if a Lambda needs it: `variable` in `terraform/variables.tf`, entry in the
   `environment` block of `terraform/lambda.tf`, and a `write_kv` in `scripts/generate_tfvars.sh`.
   Example to copy: `DOWNLOADS_*` or `MAILJET_*`, present in all of these.
5. Never commit a real value; secrets are read from the environment only.

## Testing

```bash
uv run pytest tests/test_widget_guest_auth.py -q   # example of tests that tune settings
uv run ruff check src/config && uv run mypy src/config
```

Tests override values with `monkeypatch.setattr(settings, "field", value)` on the singleton; tests do not
reload the module. `tests/conftest.py` sets the base env before import.

## Do / Don't

- Do give every field a safe default or a `validate_*` guard; don't let a missing optional variable crash startup.
- Do comment why a value is what it is (see the Dream and reaper fields).
- Don't read `os.environ` elsewhere (`src/crypto.py` is a legacy exception); don't add the var to only one of
  settings, Railway script and Terraform.
