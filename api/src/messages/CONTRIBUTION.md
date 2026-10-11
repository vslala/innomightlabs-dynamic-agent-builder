# Messages

Owns the `Message` entity (one chat turn row: user, assistant or system), its API response models, and the repositories that store them. Conversations (`src/conversations/`) reference messages by `conversation_id`; the agent runtime (`src/agents/`) writes them and replays them to the LLM.

## Layout

```text
src/messages/
  __init__.py                    re-exports Message, MessageResponse, repositories
  models.py                      Message, MessageKind, Attachment, MessageImage, MessageCanvasArtifact, response models, upload limits
  repository.py                  re-export shim for the repositories package
  responses.py                   MessageResponseFactory: builds image/canvas URLs for a response
  repositories/
    base.py                      MessageRepository Protocol (the contract)
    dynamodb.py                  DynamoDBMessageRepository (production)
    in_memory.py                 InMemoryMessageRepository (transient, with compaction)
    compaction.py                TemplateMessageCompactionStrategy for the in-memory repo
    factory.py                   get_message_repository(name) -> "dynamodb" | "in_memory"
    templates/context_compaction.j2   Jinja template for the compacted summary
```

## Conventions

**Keys.** All rows of a conversation share one partition:

- `pk = CONVERSATION#{conversation_id}`
- `sk = MESSAGE#{iso_timestamp}#{message_id}` for chat rows
- `sk = AUDIT#{iso_timestamp}#{message_id}` for tool-call audit rows

`Message.kind` (`MessageKind.CHAT` / `TOOL_AUDIT`) chooses the prefix. Audit rows are written on every tool call and can be large, so they sit under their own prefix and never appear in conversation queries. Only `find_audit_by_conversation` and `delete_by_conversation` read them. Messages are not keyed by account: access is checked on the conversation first (see `src/conversations/router.py`), then messages are read by conversation id.

**Protocol first.** Callers depend on `MessageRepository` (`base.py`) and get an implementation from `get_message_repository(...)`. A new method goes on the Protocol, then on both implementations. The DynamoDB repository also paginates with `decode_cursor` / `encode_cursor` (`src/common/pagination.py`) over `LastEvaluatedKey`.

**Never trust one query page.** `find_by_conversation` and `delete_by_conversation` follow `LastEvaluatedKey` through `_query_all`. A single query returns at most 1 MB, and truncating silently fed the LLM a partial conversation (see `api/docs/LLD-agent-runtime-refactor.md`, P0.1).

**Responses.** `Message.to_response()` is the plain mapping; `MessageResponseFactory.to_response` adds image URLs (`/conversations/{id}/messages/{message_id}/images/{image_id}`) and canvas URLs. Use the factory in routers so URLs are consistent. The S3 storage client is created lazily.

**Attachments.** `ALLOWED_EXTENSIONS`, `MAX_FILE_SIZE`, `MAX_FILES`, `MAX_TOTAL_SIZE` and the validators in `models.py` are the single source for upload limits.

**In-memory repo.** Used where nothing should persist. `save` compacts when the estimated tokens exceed `context_token_limit`, replacing old messages with one summary built from `context_compaction.j2` (Jinja `StrictUndefined`, so a missing variable fails loudly).

## How to add a repository method

1. Add the signature to `MessageRepository` in `repositories/base.py`.
2. Implement it in `dynamodb.py` using the `pk`/prefix helpers (`_pk`, `_query_all`, `_query_page`); implement it in `in_memory.py` with the same ordering semantics.
3. Add a case to `tests/test_in_memory_message_repository.py` and, for paging or DynamoDB behaviour, `tests/test_message_repository_paging.py`.

To add a message field: add it to `Message`, write it in `to_dynamo_item` only when set (as `images` is), read it with a default in `from_dynamo_item`, and add it to `MessageResponse` and `to_response`.

## Testing

```bash
uv run pytest tests/test_messages.py tests/test_message_*.py tests/test_in_memory_message_repository.py tests/test_llm_message_models.py -q
uv run ruff check src/messages && uv run mypy src/messages
```

DynamoDB tests use moto through `dynamodb_table`; no network. `tests/test_message_response_factory.py` covers URL building.

## Do / Don't

- Do query by `pk` plus a prefix; don't scan.
- Do follow `LastEvaluatedKey` whenever you need "all" rows.
- Do keep audit data under `AUDIT#`; don't write tool-call rows with `kind=CHAT`.
- Do keep the Protocol, DynamoDB and in-memory implementations in step.
- Don't add a third repository backend or a registry beyond the two-entry dict in `factory.py` without a real caller.
- Don't build image or canvas URLs by hand outside `MessageResponseFactory`.
