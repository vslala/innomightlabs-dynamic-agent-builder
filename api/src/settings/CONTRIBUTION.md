# Settings Module

Owns the account's provider credentials (Bedrock, Anthropic, OpenAI API key, Gemini, Ollama, plus OAuth-backed providers stored by other modules), the Agent2Agent outbound trust list, and a member's default agent. Credentials belong to the account: its admins connect them (`settings:Manage`) and every member's agents use them. `src/llm/` and the skills read them through `ProviderSettingsRepository`.

## Layout

```text
src/settings/
  __init__.py            exports ProviderSettings, ProviderSettingsRepository
  access.py              MANAGE_SETTINGS, settings_manager dependency, may_manage_settings (OAuth callbacks)
  models.py              ProviderSettings, Agent2AgentSettings, DefaultAgentPreference + responses
  repository.py          one repository per item type, plus get_*_repository dependency functions
  schemas.py             provider form schemas (PROVIDER_SCHEMAS), A2A settings form
  agent2agent_policy.py  origin parsing/normalisation and Agent2AgentPolicy
  router.py              /settings/...: access, providers, agent2agent, default-agent
```

## Conventions

- **Keys.** Provider settings: `pk = Account#{account_id}`, `sk = ProviderSettings#{provider_name}`. A2A: `pk = Account#{account_id}`, `sk = Agent2AgentSettings`. Default agent is per member: `pk = member_partition(account_id, user_id)` (`Account#{id}#Member#{user_id}`, from `src/accounts/owner.py`), `sk = DefaultAgentPreference`. Repositories repeat the key strings of the model's `pk`/`sk`; keep them in step.
- **Access.** Reads use `get_principal` (any member may see what is configured). Writes use `Depends(settings_manager)`, which calls `principal.require("settings:Manage")` and answers 403. `GET /settings/access` tells the SPA whether to show controls. Flows that finish in a later request (OAuth callbacks) re-check with `may_manage_settings(user_id, account_id)`. The default agent is the member's own preference and requires `agents:Chat` on the chosen agent via `require_agent`.
- **Credentials.** The request body is a `dict` validated against the provider's `Form`: every non-optional field must be present and non-empty. The JSON is encrypted with `src.crypto.encrypt` before storage; responses expose only `is_configured` and timestamps, never credentials. `OpenAI` and `GoogleDrive` are rejected here because they connect through OAuth routes in `src/auth/`.
- **Forms.** Provider forms are `form_models.Form` values in `schemas.py` with `submit_path` and `FormInput`s; optional fields set `attr={"optional": "true"}`. The SPA renders them with `SchemaForm`, so keep `name`s stable.
- **Errors.** Unknown provider and missing fields give `HTTPException(400)`. `Agent2AgentPolicyError` (a `ValueError`) and pydantic `ValidationError` map to 400 in the route.
- **Default agent** is stored without an existence check; callers treat a deleted `agent_id` as unset.
- **Saves** read the existing item to preserve `created_at` and set `updated_at`. `updated_by` is the audit user id.

## How to add a provider

1. Add a `*_PROVIDER_FORM` in `schemas.py` (copy `ANTHROPIC_PROVIDER_FORM`) with `submit_path="/settings/providers/<Name>"`, and register it in `PROVIDER_SCHEMAS`. `SUPPORTED_PROVIDERS` follows from it.
2. Implement the LLM side in `src/llm/providers/` and the model catalog in `src/llm/models.py`; read the credentials with `decrypt` there.
3. For an OAuth provider, set `submit_path` to the auth route, reject it in `save_provider_settings` like `OpenAI`, and store `ProviderSettings(auth_type="oauth")` from the auth module.
4. Add the provider to the SPA settings page if it needs custom UI.
5. Test in a new `tests/test_<provider>_settings.py` (see `tests/test_ollama_settings.py`).

## Testing

```bash
uv run pytest tests/test_account_settings_access.py tests/test_default_agent_settings.py tests/test_ollama_settings.py tests/test_superuser_settings.py -q
uv run ruff check src/settings && uv run mypy src/settings
```

Tests use `dynamodb_table` (moto), `test_client` and `auth_headers`. Shared-account behaviour (admin vs member) is in `test_account_settings_access.py`.

## Do / Don't

- Do guard every write route with `settings_manager`; do not hand-roll role checks.
- Do encrypt anything secret before it reaches the repository.
- Do add a new env var in `src/config/settings.py`, never read `os.environ` in this module.
- Don't return stored credentials from any endpoint, including to admins.
- Don't branch on provider name in the router beyond the OAuth rejections; put per-provider shape in `schemas.py`.
