# Memory

Owns the MemGPT-style memory of the `krishna-memgpt` architecture: named core-memory blocks (line-based text loaded into the system prompt every turn) and archival memory (long-term, searched on demand). Memory is scoped per agent and per user. The agent tools that read and write it are in `src/tools/native/`; the nightly job that tidies it is `src/dream/`.

## Layout

```text
src/memory/
  __init__.py     re-exports models, MemoryRepository, MemoryCompactionService
  models.py       MemoryBlockDefinition, CoreMemory, ArchivalMemory, CapacityWarningTracker (each with pk/sk and dynamo (de)serialisation)
  repository.py   MemoryRepository: all DynamoDB access, build_agent_user_pk
  snapshot.py     frozen dataclasses: one consistent read of core memory for prompt rendering
  compaction.py   MemoryCompactionService: capacity warnings and LLM auto-compaction of a full block
  router.py       /agents/{agent_id}/memory-blocks: list, create, delete custom blocks; read/write block content
```

## Conventions

**Keys.** Everything for one agent and one user shares a partition, `pk = Agent#{agent_id}#User#{user_id}`:

| Item | sk |
| --- | --- |
| `MemoryBlockDefinition` | `MemoryBlockDef#{agent_id}:{user_id}:{block_name}` |
| `CoreMemory` | `CoreMemory#{block_id}` (same block id) |
| `ArchivalMemory` | `Archival#{iso_created_at}#{memory_id}` |
| `CapacityWarningTracker` | `CapacityWarning#{block_id}` |
| archival hash index | `pk = Agent#..#User#..#Hash#{sha256}`, `sk = Archival#{memory_id}` |

`build_block_id` and `build_agent_user_pk` are the only places these strings are composed for lookups; models expose `pk`/`sk` properties. The hash-index item makes `insert_archival` idempotent: identical content returns the existing row with `is_new=False`. Deleting an archival row also deletes its hash item (and `delete_all_for_user` deletes hash items first so an interrupted run can be retried).

**The `user_id` is whoever the memory is about.** In the router it is `request.state.user_email`; in a chat turn it is the turn's `actor_id` (an end user or API key). The router checks `require_agent(principal, agent_id, "agents:Chat", ...)`, so a member keeps their own memory with any agent they can chat with. Memory is never shared across users.

**Blocks.** `human` and `persona` are default blocks (`is_default=True`, created by `initialize_default_blocks`, idempotent). Default blocks cannot be deleted (`ValueError`, surfaced as 400). Custom block names match `^[a-z][a-z0-9_]*$` (see `CreateMemoryBlockRequest`); LLM-supplied names go through `normalize_block_name` in `src/tools/native/handlers.py`.

**Lines and capacity.** Core content is `lines: list[str]`, edited by 1-indexed line number. `save_core_memory` recomputes `word_count` and `updated_at`; do not set them by hand. Capacity is `word_count / word_limit`; `CAPACITY_WARNING_THRESHOLD` and `COMPACTION_TARGET` come from `src/common`. A block that stays near capacity for `TURNS_BEFORE_AUTO_COMPACT` (3) turns is archived, summarised by the LLM and replaced.

**Snapshots.** `CoreMemorySnapshot.of(block_defs, memories)` joins definitions with contents once per turn so prompt rendering never re-reads DynamoDB. Put capacity rules (`nearing_capacity`) on the snapshot, not in prompt code.

**Known limits.** `search_archival` queries the whole archival partition and filters by substring in Python; `delete_archival` and `find_archival_by_hash` use a `FilterExpression` on `memory_id` after the key query. Keep archival volumes in mind before adding features that call them in a loop.

## How to add a memory item type or field

1. Add a Pydantic model in `models.py` with `pk` (reuse the agent/user partition), a distinct `sk` prefix, `to_dynamo_item` and `from_dynamo_item`.
2. Add `get_`/`save_`/`delete_` methods to `MemoryRepository`, deleting dependants together (as `delete_block_definition` also removes `CoreMemory#...`).
3. Make sure `delete_all_for_user` still removes it (it queries the whole partition, so a shared `pk` is enough).
4. Expose it through a tool (`src/tools/native/`) or an endpoint in `router.py`, which takes `MemoryRepository` and `AgentRepository` via `Depends(get_memory_repository)` / `Depends(get_agent_repository)`.

## Testing

```bash
uv run pytest tests/test_memory_models.py tests/test_dream_actions.py tests/test_krishna_memgpt_*.py -q
uv run ruff check src/memory && uv run mypy src/memory
```

Tests build `MemoryRepository()` over moto using the `dynamodb_table` fixture (`tests/conftest.py`). There is no dedicated router test file yet; add `tests/test_memory_router.py` with `test_client` and `auth_headers` for new endpoints.

## Do / Don't

- Do keep one partition per (agent, user) so a user's whole memory is one query and one delete.
- Do make writes idempotent (hash index, `line_exists`, "delete of a missing row is success").
- Do compose block ids and partition keys with the helpers, not string literals in new code.
- Don't change `lines` without `save_core_memory`; it owns the word count.
- Don't put LLM calls in the repository; compaction takes the provider as an argument.
- Don't add a search backend for archival memory until the substring search is shown to be the bottleneck.
