# Conversations

Owns the `Conversation` entity (one chat thread between a member and an agent) and the `/conversations` API: create, list, read, rename, delete, page messages, and serve generated images. The messages inside a conversation live in `src/messages/`; chat turns that write to them live in `src/agents/`.

## Layout

```text
src/conversations/
  __init__.py     re-exports models, ConversationRepository, router
  models.py       Conversation + subtypes (AutomationConversation, ApiConversation), request/response models
  repository.py   ConversationRepository: all DynamoDB access, offset-cursor paging
  router.py       /conversations endpoints; module-level repositories
```

There is no `service.py`: the endpoints are thin enough to call the repository directly.

## Conventions

**Keys.** One item per conversation, in the starter's member partition:

- `pk = Account#{account_id}#Member#{created_by}` (built by `member_partition` in `src/accounts/owner.py`)
- `sk = CONVERSATION#{conversation_id}`
- `gsi2_pk = Conversation#{conversation_id}`, `gsi2_sk = Conversation` (lookup by id alone)

A conversation belongs to the member who started it, even on a shared agent. Callers always name the partition (`Owner.member_pk`, `Agent.owner_partition`, `ApiConversation.partition_for(...)`), so a request can only reach its own conversations.

**Subtypes.** `Conversation` is the base; `AutomationConversation` (`conversation_type="automation"`, carries `automation_id`/`automation_run_id`) and `ApiConversation` (public `/v1` API; `created_by = secret-key:{key_id}[:{end_user_id}]`, so it lands in a pseudo-member partition) extend it. `ConversationRepository._from_dynamo_item` picks the class from `conversation_type` / `entity_type`; a new subtype must set a distinct `entity_type` in `to_dynamo_item` and be added there.

**Two lookups, on purpose.** `find_by_id(conversation_id, partition)` is a GetItem for request handling. `get(conversation_id)` goes through gsi2 and ignores ownership: use it only inside work already running in a conversation (skill actions, schedules, image generation), never for an id that came from a request. gsi2 is eventually consistent.

**Access.** `own_partition` (router) derives the partition from the `Principal` (`get_principal`), so even an admin only sees their own conversations. Creating one calls `require_agent(principal, agent_id, "agents:Chat", ...)` from `src/agents/access.py`. Missing or foreign ids return 404, not 403.

**Writes.** `save` is create-or-update (read, keep `created_at`, put). Prefer the narrow updates `touch` (bump `updated_at`) and `update_context` (set `context`, conditional on existence): `save` would overwrite fields changed since the object was loaded.

**Listing.** `find_all_by_user_paginated` queries the whole partition, sorts by `updated_at or created_at`, filters with the `keep` callback, then slices by an offset cursor (base64 `{"offset": n}`). Bad cursors raise `InvalidCursor` (`src/common/pagination.py`). The router's `keep` hides Ila's conversations (`ILA_AGENT_ID`) and, unless `include_automation=true`, automation runs.

**Messages.** The router holds `message_repository = get_message_repository("dynamodb")` and turns messages into responses with `MessageResponseFactory`. `find_visible_messages_newest_first` drops legacy `role="system"` rows; see `src/messages/CONTRIBUTION.md`.

**Delete.** The router deletes the messages (`delete_by_conversation`), then the conversation's S3 media (`ConversationMediaStorage`; a failure is logged, not surfaced), then the conversation row; only a failed row delete is a 500.

## How to add a field or endpoint

1. Field: add it to `Conversation` (and `ConversationResponse` if exposed), write it in `to_dynamo_item`, read it with `item.get(...)` in `from_dynamo_item` so old rows still load. Repeat in each subtype that re-implements those methods (they do not call `super()` for reading).
2. Endpoint: add a function to `router.py` taking `partition: Partition` (or the `Principal`), call `conversation_repository.find_by_id(conversation_id, partition)` and raise `HTTPException(404, "Conversation not found")` if it is `None`. Follow `update_conversation` for a write.
3. New query shape: add a method to `ConversationRepository` with the access pattern in its docstring list.

## Testing

```bash
uv run pytest tests/test_conversations_*.py tests/test_conversation_strategy.py -q
uv run ruff check src/conversations && uv run mypy src/conversations
```

Tests run on moto through the `dynamodb_table`, `conversation_repository`, `test_client` and `auth_headers` fixtures in `tests/conftest.py`. Paging and cursor behaviour is in `tests/test_conversations_repository.py`; HTTP behaviour in `tests/test_conversations_router.py`.

## Do / Don't

- Do pass the partition explicitly; don't add a "find by id across members" path to a request handler.
- Do use `touch` / `update_context` for single-field changes.
- Do keep the 404-for-foreign-ids behaviour so ids are not probeable.
- Don't add a service layer until a second caller needs the logic.
- Don't add a GSI for a new listing; the member partition already answers it.
- Don't write ASCII diagrams in docstrings or docs; Mermaid only.
