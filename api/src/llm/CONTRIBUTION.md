# LLM Module Guide

`src/llm/` is the boundary to the model vendors. It owns the provider clients that stream a response, the
provider-neutral event, message and tool shapes, model catalogs per provider, credential loading, and how
conversation history is windowed. Agents (`src/agents/`) call into it; it holds no agent or account state.

## Layout

```text
src/llm/
  providers/
    __init__.py      PROVIDERS (every provider, in Settings order), provider(name), find_provider(name)
    provider.py      Provider (one provider's parts), ModelCatalog, CredentialSource, StoredCredentials, OAuthSignIn
    <name>/          one package per provider:
      __init__.py      the Provider value: name, title, settings form, chat, catalog, refusal rule, ...
      chat.py          the LLMProvider that streams a response
      catalog.py       its ModelCatalog: the models the account's credentials can use
    bedrock/         Claude via AWS (catalog also used by chat to map a model name to an id)
    anthropic/       Anthropic API key
    openai/          ChatGPT sign-in: Codex Responses API; credentials.py refreshes the OAuth token
    openai_api/      OpenAI with an API key: the same Responses wire, its own endpoint and key; images.py draws with
                     `gpt-image-*` on the images endpoint, streamed
    gemini/          Gemini API key; images.py draws with `gemini-*-image` through `generateContent`
    ollama/          user-hosted Ollama (native /api/chat NDJSON); connection.py: endpoint validation and headers
    grok/            xAI with an API key: the Responses wire for chat; images.py draws on xAI's images endpoint
  wire/              wire formats more than one provider speaks, used by composition:
    sse.py             sse_events: the JSON of each `data:` line
    responses.py       the Responses API: input/tool conversion, responses_body, stream_chat, the refusal rule
    responses_images.py  ResponsesToolImages: drawing with the Responses `image_generation` tool
    images_api.py      generate_images: OpenAI's `images/generations` shape (xAI serves it), b64 pictures, not streamed
  chat.py            LLMProvider ABC (the chat contract), LLMEvent, StopReason, stop_reason_of
  images.py          ImageGenerator (Provider.images) and what it takes and gives back
  models.py          ModelInfo, ModelCapability (chat, image_understanding, image_generation, image_editing),
                     chat_capabilities
  model_fallback.py  ModelFallbackProvider: retries a vendor-refused stored model on a catalog substitute
  router.py          GET /llm/models/{provider}
  credentials.py     load_provider_credentials: the provider's CredentialSource
  messages.py        normalize_messages / split_system_messages: provider-neutral ChatMessage blocks
  tools.py           ToolDefinition and to_openai / to_anthropic / to_bedrock / to_ollama converters
  events.py          SSEEvent, SSEEventType, tool_call_events (what a run log keeps), capped_events
  conversation_strategy.py  ConversationStrategy, FixedWindowStrategy (history windowing)
```

## Conventions

**Provider contract.** A provider implements `async stream_response(messages, credentials, tools, model)` and yields
`LLMEvent`s: `text`, `tool_use`, `usage`, and one `stop` whose `content` is a `StopReason` (`end_turn`,
`max_tokens`, `content_filter`). Map the vendor's reasons with `stop_reason_of(raw, known)`; anything that is not a
limit is `end_turn`. Usage is its own event because some vendors report it after the stop (Bedrock).
Messages arrive in the agent loop's Bedrock-style blocks (`toolUse`, `toolResult`); convert them with `messages.py` and
`tools.py` rather than hand-parsing in each provider. The first `system` message is the system prompt.

**One definition per provider.** Everything that differs by provider is a field of its `Provider`
(`providers/provider.py`): name, title, settings form, chat client, catalog, how credentials load, the refusal rule, an
OAuth sign-in, the thinking knob. `PROVIDERS` lists them; `provider(name)` and `find_provider(name)` find one. Settings,
the model pickers, credential loading and the fallback all read from it, so no code outside `providers/` names a
provider (`tests/test_providers_registry.py` and the SPA's `noHardcodedProviders.test.ts` fail if one does). A new
need that differs by provider becomes a field, not an `if`.

**Provider names** (`Provider.name`) are stored as `Agent.agent_provider`, as `ProviderSettings` keys and in the
account's model settings, so a name never changes.

**Credentials.** A chat client receives a plain `credentials` dict and never touches storage. Credentials are stored
encrypted in `ProviderSettings` (`src/settings`) and loaded by `load_provider_credentials`, which asks the provider's
`CredentialSource`: `StoredCredentials` decrypts them; the ChatGPT sign-in's refreshes an expired token first
(`providers/openai/credentials.py`). The agent side resolves them once per turn in `agents/provider_session.py`. Never
log a credentials dict.

**Model catalogs.** Each provider's `catalog.py` lists `ModelInfo`s, offered only once the account has configured the
provider; `form_options.py` (agent forms) and `router.py` read them through `PROVIDERS`. Bedrock is no exception: its
catalog lists with the account's AWS keys, never the server's own AWS identity. A catalog must fall back (static list
or configured `settings.openai_models`) instead of failing the form: `form_options` still offers the provider if
listing raises, but an empty picker is a bad experience. The Codex catalog is cached per account for
`CATALOG_TTL_SECONDS`. Filtering rules for the OpenAI API list (`NON_CHAT_MARKERS` etc. in
`providers/openai_api/catalog.py`) record what the live API refused and when it was checked; update the date when you
re-check.

**Capabilities come from the catalog.** Each catalog tags its models with `ModelCapability`: `CHAT` for a model that
can hold a conversation, `IMAGE_UNDERSTANDING`, `IMAGE_GENERATION`. It reads the vendor's own field where there is
one (Anthropic `capabilities.image_input`, Bedrock `inputModalities`, Codex `input_modalities`, Ollama `/api/show`) and
otherwise applies a dated rule beside its parsing (OpenAI API and Gemini publish none). xAI lists its chat and image
models apart (`/v1/language-models`, `/v1/image-generation-models`), so Grok's image models are `IMAGE_GENERATION` only.
The OpenAI API's `gpt-image-*` models and Gemini's `*-image` / `nano-banana` models are the same, by name, since
neither listing has a modality field. ChatGPT sign-in
chat models are `CHAT` and `IMAGE_GENERATION`: they host the Responses drawing tool, the only way that backend draws. The agent picker offers `CHAT`
models, Image Reading `CHAT` + `IMAGE_UNDERSTANDING`, Image Generation `IMAGE_GENERATION`, and a fallback substitute
must be `CHAT`. A model that only draws stays in the catalog, tagged, rather than being filtered out. Only a provider
with `images` may tag `IMAGE_GENERATION` (`tests/test_providers_registry.py` checks it).

**Stored models go stale.** Vendors retire models and gate them per account, so wrap a provider that runs a stored
model in `ModelFallbackProvider(provider(name), provider_settings)`. It tries the stored model, and on a vendor refusal
(`Provider.refuses_model`) retries once on the first suitable catalog model, remembering the swap for an hour. Set
`default_model` on a chat client that has one. See the wiki page `LLM-Model-Fallback`.

**Router.** `GET /llm/models/{provider}` returns `[]` for an unknown or unconfigured provider so callers can probe.
It scopes by `principal.account_id`.

**Conversation strategy.** `FixedWindowStrategy(max_words)` keeps the newest user/assistant messages within a word
budget, returns `[]` once `session_timeout_minutes` has elapsed since the last message (the agent can then use its
recall tool), and renders attachments as `<attached_file>` blocks. Architectures own system prompts and memory;
strategies only select history.

**Events.** `SSEEventType` is the wire vocabulary the SPA and widget consume. Adding a type means updating the SPA
(and `embed/` if the widget shows it), and deciding whether it belongs in `RECORDED_EVENT_TYPES`. A TOOL_CALL_RESULT
carries `started_at`/`completed_at` for when the tool itself ran; the agentic loop and consent continuation set them.

## How to add a provider

1. `providers/<name>/chat.py`: subclass `LLMProvider`, implement `stream_response` using `normalize_messages`,
   `split_system_messages` and the matching `ToolDefinition.to_*` (add a converter in `tools.py` if the wire format is
   new). Emit `usage` and exactly one `stop`, and set `default_model`. Model on `anthropic/chat.py` (its own SDK) or
   `openai_api/chat.py` (a known wire format from `wire/`).
2. `providers/<name>/catalog.py`: a class with `list_models(provider_settings)` that falls back rather than raises.
   Read saved credentials with `stored_credentials(provider_settings)`.
3. `providers/<name>/__init__.py`: the `Provider` value with its settings form, chat, catalog and a dated
   `refuses_model` rule. Set `oauth` and `credentials` only for a provider signed into (see `openai/`), and `images`
   for one that draws.
4. List it in `PROVIDERS` (`providers/__init__.py`). Settings, the pickers and the SPA pick it up from there.
5. Tests: a chat test beside `tests/test_anthropic_provider.py`, a catalog test like `tests/test_openai_models.py`.
   To stand in for a provider's parts elsewhere, use `tests/llm_doubles.py` (`use_provider`, `use_chat_everywhere`).

## Testing

```bash
uv run pytest tests/test_llm_*.py tests/test_*_provider.py tests/test_providers_registry.py tests/test_openai_models.py \
  tests/test_provider_session.py tests/test_conversation_strategy.py tests/test_form_options_provider_models.py -q
uv run ruff check src/llm && uv run mypy src/llm
```

Provider tests mock the HTTP/boto layer (httpx, boto3 stubs); no test calls a vendor. Catalog tests use moto only where
DynamoDB is involved (provider settings via `dynamodb_table`). Do not add live-network tests.

## Do / Don't

- Do keep providers stateless and credentials-in, events-out.
- Do convert through `messages.py`/`tools.py`; one place per vendor format conversion.
- Do reuse `wire/` when a vendor speaks a known format: build your URL, headers and body, then call it. Don't
  subclass another provider's chat client, and don't copy a parser.
- Do put anything that differs by provider on its `Provider`; don't branch on a provider's name anywhere.
- Don't import from `src/agents` here; the dependency runs agents -> llm.
- Don't fail a form render because a vendor's listing endpoint is down; fall back.
- Don't log or return credentials; the `/llm/models` response is `ModelInfo` only.
- Comments say why (what the vendor does and when it was verified), not what.
