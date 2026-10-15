# LLM Module Guide

`src/llm/` is the boundary to the model vendors. It owns the provider clients that stream a response, the
provider-neutral event, message and tool shapes, model catalogs per provider, credential loading, and how
conversation history is windowed. Agents (`src/agents/`) call into it; it holds no agent or account state.

## Layout

```text
src/llm/
  providers/
    base.py          LLMProvider ABC, LLMEvent, StopReason, stop_reason_of
    factory.py       get_llm_provider(name): the name -> provider map
    bedrock.py       Bedrock (Claude via AWS)
    anthropic.py     Anthropic API key
    openai.py        OpenAI via Codex/ChatGPT OAuth (Responses API)
    openai_api.py    OpenAI with an API key; subclass of openai.py, own endpoint and key
    gemini.py        Gemini API key
    ollama.py        user-hosted Ollama (native /api/chat NDJSON)
  models.py          ModelInfo, ModelsService (catalogs), PROVIDER_MODEL_SOURCES, find_model_source
  model_fallback.py  ModelFallbackProvider: retries a vendor-refused stored model on a catalog substitute
  router.py          GET /llm/models/{provider}
  credentials.py     load_provider_credentials (decrypt, OpenAI token refresh)
  ollama.py          OllamaConnection: endpoint validation and headers, shared by chat and discovery
  messages.py        normalize_messages / split_system_messages: provider-neutral ChatMessage blocks
  tools.py           ToolDefinition and to_openai / to_anthropic / to_bedrock / to_ollama converters
  events.py          SSEEvent, SSEEventType, recorded_events (what the run log keeps)
  conversation_strategy.py  ConversationStrategy, FixedWindowStrategy (history windowing)
```

## Conventions

**Provider contract.** A provider implements `async stream_response(messages, credentials, tools, model)` and yields
`LLMEvent`s: `text`, `tool_use`, `usage`, and one `stop` whose `content` is a `StopReason` (`end_turn`,
`max_tokens`, `content_filter`). Map the vendor's reasons with `stop_reason_of(raw, known)`; anything that is not a
limit is `end_turn`. Usage is its own event because some vendors report it after the stop (Bedrock).
Messages arrive in the agent loop's Bedrock-style blocks (`toolUse`, `toolResult`); convert them with `messages.py` and
`tools.py` rather than hand-parsing in each provider. The first `system` message is the system prompt.

**Credentials.** A provider receives a plain `credentials` dict and never touches storage. Credentials are stored
encrypted in `ProviderSettings` (`src/settings`), decrypted by `load_provider_credentials`; only `OpenAI` goes through
`ensure_valid_openai_credentials`, which refreshes the OAuth token. The agent side resolves them once per turn in
`agents/provider_session.py`. Never log a credentials dict. Provider forms for the settings page are in
`src/settings/schemas.py` (`PROVIDER_SCHEMAS`).

**Provider names** are the exact strings `Bedrock`, `Anthropic`, `OpenAI`, `OpenAIAPI`, `Gemini`, `Ollama`. They are used as
`Agent.agent_provider`, as `ProviderSettings` keys, in `get_llm_provider`, in `PROVIDER_MODEL_SOURCES` and in
`PROVIDER_SCHEMAS`. A typo in one is a runtime `ValueError` or a provider that silently never lists models.

**Model catalogs.** `ModelsService` has one `get_<provider>_models` per provider returning `ModelInfo`.
`PROVIDER_MODEL_SOURCES` is the single list of providers that need user settings; `form_options.py` (agent forms) and
`router.py` both iterate it, so a provider is picked up everywhere by adding one entry. Bedrock is always offered and
is special-cased. A catalog method must fall back (static list or configured `settings.openai_models`) instead of
failing the form: `form_options` still offers the provider if listing raises, but an empty picker is a bad experience.
The Codex catalog is cached per account for `OPENAI_CATALOG_TTL_SECONDS`. Filtering rules for the OpenAI API list
(`OPENAI_API_NON_CHAT_MARKERS` etc.) record what the live API refused and when it was checked; update the date when
you re-check.

**Stored models go stale.** Vendors retire models and gate them per account, so wrap a provider that runs a stored
model in `ModelFallbackProvider(get_llm_provider(name), name, provider_settings)`. It tries the stored model, and on a
vendor refusal (`MODEL_REFUSALS`, one rule per vendor) retries once on the first suitable catalog model, remembering the
swap for an hour. Set `default_model` on a provider that has one. See the wiki page `LLM-Model-Fallback`.

**Router.** `GET /llm/models/{provider}` returns `[]` for an unknown or unconfigured provider so callers can probe.
It scopes by `principal.account_id`.

**Conversation strategy.** `FixedWindowStrategy(max_words)` keeps the newest user/assistant messages within a word
budget, returns `[]` once `session_timeout_minutes` has elapsed since the last message (the agent can then use its
recall tool), and renders attachments as `<attached_file>` blocks. Architectures own system prompts and memory;
strategies only select history.

**Events.** `SSEEventType` is the wire vocabulary the SPA and widget consume. Adding a type means updating the SPA
(and `embed/` if the widget shows it), and deciding whether it belongs in `RECORDED_EVENT_TYPES`.

## How to add a provider

1. `providers/<name>.py`: subclass `LLMProvider`, implement `stream_response` using `normalize_messages`,
   `split_system_messages` and the matching `ToolDefinition.to_*` (add a converter in `tools.py` if the wire format is new).
   Emit `usage` and exactly one `stop`. Model on `anthropic.py` (simple) or `openai_api.py` (reuse by subclassing).
2. Register it in `providers/factory.py`. Set `default_model` and add a `ModelRefusal` in `model_fallback.py`.
3. Add a settings form in `src/settings/schemas.py` (`PROVIDER_SCHEMAS`) so accounts can store credentials.
4. Add `get_<name>_models` to `ModelsService` and a `ProviderModelSource` entry in `PROVIDER_MODEL_SOURCES`.
5. If credentials need refresh or parsing beyond decrypt-and-JSON, extend `credentials.py`. A catalog (sync) that needs
   refreshed credentials calls the `*_blocking` loader there (`load_openai_credentials_blocking`), never the stored token.
6. Add a provider test beside `tests/test_anthropic_provider.py` / `tests/test_gemini_provider.py` and a catalog test
   like `tests/test_openai_models.py`.

## Testing

```bash
uv run pytest tests/test_llm_*.py tests/test_*_provider.py tests/test_openai_models.py tests/test_provider_session.py \
  tests/test_conversation_strategy.py tests/test_form_options_provider_models.py -q
uv run ruff check src/llm && uv run mypy src/llm
```

Provider tests mock the HTTP/boto layer (httpx, boto3 stubs); no test calls a vendor. Catalog tests use moto only where
DynamoDB is involved (provider settings via `dynamodb_table`). Do not add live-network tests.

## Do / Don't

- Do keep providers stateless and credentials-in, events-out.
- Do convert through `messages.py`/`tools.py`; one place per vendor format conversion.
- Do subclass when a vendor speaks another's protocol (`OpenAIAPIProvider`); do not copy the stream parser.
- Do add the new provider name to every map (factory, schemas, model sources) in the same change.
- Don't import from `src/agents` here; the dependency runs agents -> llm (note `models.py` already imports the image
  capability registry for `capabilities`; do not add more).
- Don't fail a form render because a vendor's listing endpoint is down; fall back.
- Don't log or return credentials; the `/llm/models` response is `ModelInfo` only.
- Comments say why (what the vendor does and when it was verified), not what.
