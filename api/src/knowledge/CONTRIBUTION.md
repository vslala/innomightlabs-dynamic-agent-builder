# Knowledge Contribution Guide

`knowledge/` owns knowledge bases (KBs): their metadata, crawl jobs, steps, pages, content chunks, and the agent links. Users create a KB, crawl a site or upload files, and agents search it. Crawling itself lives in `src/crawler/`, vectors in `src/vectorstore/`; this module is the data model, HTTP API and access rules around them.

## Layout

```text
src/knowledge/
  __init__.py     Re-exports models, repositories, schemas, routers, service
  models.py       Enums, entities (KnowledgeBase, CrawlJob, CrawlStep, CrawledPage, ContentChunk, AgentKnowledgeBase), request/response models
  repository.py   One repository class per entity
  access.py       require_kb / kb_with / visible_kbs / readable_by_agent: who may reach a KB
  service.py      KnowledgeBaseService: soft delete (Pinecone + chunks + links + shares), file upload ingest
  router.py       /knowledge-bases/* and agent_kb_router (agent<->KB links), search, crawl jobs
  schemas.py      Form schemas (create KB, crawl config, content upload)
  crawl_launch.py launch_crawl: Lambda or in-process, shared with blueprints
  recrawl.py      recrawl(): read a KB's site again with its last settings; the `knowledge_base` skill's action
  run_state.py    CrawlJobStateService: heartbeat and stale-job failing
```

## Conventions

- Keys (documented at the top of `models.py` and `repository.py`):
  - KB: `pk=Account#{account_id}`, `sk=KnowledgeBase#{kb_id}`. Always read through `find_in_account`.
  - CrawlJob / ContentChunk / uploads: `pk=KnowledgeBase#{kb_id}`, `sk=CrawlJob#{id}` / `Chunk#{id}` / `Upload#...`.
  - CrawlStep / CrawledPage: `pk=CrawlJob#{job_id}`, `sk=Step#...` / `Page#{url_hash}`.
  - Agent link: `pk=Agent#{agent_id}`, `sk=KnowledgeBase#{kb_id}`, `gsi2_pk=KnowledgeBase#{kb_id}`, `gsi2_sk=Agent#{agent_id}` (the reverse lookup uses index `gsi2`).
- Access: every route gets its KB from a dependency in `router.py` built with `kb_with(action)`: `can_describe_kb`, `can_read_kb`, `can_update_kb`, `can_crawl_kb`, `can_delete_kb` (actions `knowledge:Describe|Get|Update|Crawl|Delete`, defined in `src/iam/actions.py`; share roles in `src/iam/shares.py`). Creation checks `knowledge:Create`. A KB the caller cannot see is 404, one they can see but not act on is 403. KBs are private to their owner unless shared; admins see metadata only (`KnowledgeBaseAccess`: owner, shared, admin).
- An agent searches only KBs `readable_by_agent` returns: the link outlives a share, so reads are checked against the agent owner each time.
- Delete is soft: status `DELETED`, 30-day `ttl` (`SOFT_DELETE_TTL_DAYS`), vectors/chunks/links/shares removed first. `DELETED` KBs count as missing everywhere.
- Forms: `schemas.py` builds `Form`/`FormInput` (see `src/form_models.py`), served at `GET .../forms/<name>`; keep field names stable.
- Crawl settings (`crawl_job_*`, `pinecone_*`, `embedding_*`) are in `config/settings.py`. A heartbeat failing means the job was stopped: `CrawlJobStoppedError`.
- `access.py` registers `RESOLVERS["knowledge-base"]` at import so shares can resolve a KB. Importing the module is what wires it.

## Add a KB endpoint

1. Pick the action and dependency: `kb: Annotated[KnowledgeBase, Depends(can_update_kb)]` in `router.py`. Add a new action only in `iam/actions.py` and the role tuples in `iam/shares.py`.
2. Put DynamoDB access in the matching repository class in `repository.py`; put anything touching several stores in `KnowledgeBaseService`.
3. Add request/response models to `models.py`. Look at `POST /{kb_id}/search` or the content-upload route for a complete example.
4. Test in `tests/test_knowledge_access.py` style: members, shares, cross-account 404.

## Testing

```bash
uv run pytest tests/test_knowledge_access.py tests/test_agent_knowledge_links.py tests/test_crawl_job_liveness.py tests/test_crawl_launch.py -q
uv run ruff check src/knowledge && uv run mypy src/knowledge
```

Fixtures: `dynamodb_table`, `test_client` (moto), plus `AccountService`, `IamService`, `ShareRepository` and `owner_headers` for shared-account cases. Pinecone and embeddings are faked or patched; never call the real services.

## Do / Don't

- Do look KBs up by account (`find_in_account`); never by `kb_id` alone.
- Do keep behaviour near the data: derived fields and key properties live on the models.
- Do use conditional or transactional writes for invariants.
- Don't check permissions inside repositories or models; do it in the router dependency.
- Don't re-export new names in `__init__.py` unless other modules need them.
- Don't rename form field names or key shapes: stored items and the SPA depend on them.
