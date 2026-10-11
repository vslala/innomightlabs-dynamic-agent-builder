# Smart Suggestions Contribution Guide

`smart_suggestions/` drafts a form field's value with an LLM when the user types a plain-language request in the dashboard (a cron expression, agent instructions, an AWS CLI command policy). It owns the per-account settings that choose which provider and model do the drafting, and one strategy per suggestion type. The field is opted in from the owning module's form schema; the SPA shows a "Suggest" button for it.

## Layout

```text
src/smart_suggestions/
  router.py       /smart-suggestions: settings (GET/PUT), settings form schema, POST suggestion
  service.py      SmartSuggestionService: loads settings + credentials, streams the model, delegates parsing
  strategies.py   One strategy per suggestion type, the registry, JSON extraction helper
  models.py       Settings and request/response models, SmartSuggestionType constants
  schemas.py      Form for the settings page (enabled, provider, model)
  repository.py   SmartSuggestionSettingsRepository (one item per account)
```

## Conventions

- **Keys.** Settings are one item per account: `pk=Account#{account_id}`, `sk=SmartSuggestionSettings`. No GSIs.
- **Access.** Any member may read settings and request a suggestion (`get_principal`). Saving settings requires `settings:Manage` through the `settings_manager` dependency from `src/settings/access.py`; the provider credentials used belong to the account.
- **Errors.** `SmartSuggestionNotConfiguredError` (disabled, no model, provider not set up) becomes 400. `SmartSuggestionError` (bad or empty model output, unknown type) becomes 422. Strategies raise `SmartSuggestionError`; the router maps it.
- **Settings form.** `schemas.py` reuses the `AGENT_MODEL_PROVIDERS` and `AGENT_MODELS` option sources with `options_filter=FormOptionsFilter(field="provider_name")`. The PUT handler calls `validate_form_options`, so a mismatched provider and model is rejected.
- **Strategy shape.** A strategy has `suggestion_type`, `build_messages(request)` (system prompt demanding a single JSON object, user payload as JSON) and `parse_response(raw, request)`. Parse with a small Pydantic payload model via `_extract_json_object`, which strips `<think>` blocks and depth-matches braces. Then validate the value with the real domain validator (cron: `validate_schedule_expression`; AWS policy: `parse_policy`) so the user never gets an invalid suggestion.
- **Selection.** `SmartSuggestionStrategyRegistry` is a dict built from a list of strategies. Do not branch on `suggestion_type` anywhere else.
- Tools are never passed to the model (`tools=None`); the service concatenates only `text` events.

## How to add a suggestion type

1. Add a constant to `SmartSuggestionType` and the same value to the `Literal` on `SmartSuggestionRequest.suggestion_type` in `models.py`.
2. Write a payload model and a strategy class in `strategies.py` (copy `CronExpressionSuggestionStrategy`), validate with the domain's own validator, and add it to the list in `SmartSuggestionStrategyRegistry`.
3. Opt the field in where its form is built, as `src/automations/triggers/schemas.py` does for `cron_expression`:
   `smart_suggestion=SmartSuggestionConfig(suggestion_type=..., button_label=..., prompt_placeholder=...)` (`src/form_models.py`).
4. Add tests to `tests/test_smart_suggestions.py`: parse a good response, reject a bad one, and assert the form field declares the suggestion.

## Testing

```bash
uv run pytest tests/test_smart_suggestions.py -q
uv run ruff check src/smart_suggestions && uv run mypy src/smart_suggestions
```

Strategies are tested as plain functions on canned model output; no LLM is called. Settings round trips use `dynamodb_table` (moto); the endpoint test replaces the service with a fake.

## Do / Don't

- Do validate model output with the same code that will later consume the value.
- Do keep prompts inside the strategy that uses them.
- Don't parse model output with "first `{` to last `}`"; use `_extract_json_object`.
- Don't add provider-specific code here; go through `get_llm_provider` and `load_provider_credentials`.
- Don't store suggestions; they are returned and discarded.
