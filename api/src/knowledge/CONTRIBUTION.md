# Knowledge Contribution Guide

`knowledge/` owns knowledge bases (KBs): their metadata, crawl jobs, steps, pages, content chunks, and the agent links. Users create a KB, crawl a site or upload files, and agents search it. Crawling itself lives in `src/crawler/`, vectors in `src/vectorstore/`; this module is the data model, HTTP API and access rules around them.

## Layout

```text
src/knowledge/
  __init__.py     Re-exports models, repositories, schemas, routers, service
  models.py       Enums, entities (KnowledgeBase, CrawlJob, CrawlLease, CrawlStep, CrawledPage, KnowledgePage, ContentChunk,
                  AgentKnowledgeBase), request/response models
  repository.py   One repository class per entity
  access.py       require_kb / kb_with / visible_kbs / readable_by_agent: who may reach a KB
  service.py      KnowledgeBaseService: soft delete (Pinecone + chunks + pages + links + shares), file upload ingest
                  (through crawler/page_index.py, so an upload is a page like any other)
  router.py       /knowledge-bases/* and agent_kb_router (agent<->KB links), search, crawl jobs, pages
  schemas.py      Form schemas (create KB, crawl config, content upload)
  crawl_launch.py create_crawl_job (takes the KB's crawl lease, or CrawlAlreadyRunning) and launch_crawl (Lambda or
                  in-process); shared by the routes, blueprints and recrawl
  recrawl.py      recrawl(): read a KB's site again with its last settings; the `knowledge_base` skill's action
  run_state.py    CrawlJobStateService: the crawl lease (hold, release), heartbeat and stale-job failing
  documents.py    The KB's follow-up for `src/documents/`: index a read document as a page, take the page out before
                  the document is deleted; owner_of(kb)
```

## Conventions

- Keys (documented at the top of `models.py` and `repository.py`):
  - KB: `pk=Account#{account_id}`, `sk=KnowledgeBase#{kb_id}`. Always read through `find_in_account`.
  - CrawlJob / ContentChunk / uploads: `pk=KnowledgeBase#{kb_id}`, `sk=CrawlJob#{id}` / `Chunk#{id}` / `Upload#...`.
    Job ids are random, so the newest job is found by reading the partition's jobs and sorting (`find_all_by_kb`).
  - KnowledgePage (a page as it is now: its chunk ids, state (live, failing, gone, duplicate), validators): `pk=KnowledgeBase#{kb_id}`,
    `sk=KnowledgePage#{url_hash}`, saved conditionally on its `version`. `sk=KnowledgePagesAdopted` marks a KB whose
    older chunks have been given pages. Gone pages expire after `GONE_PAGE_DAYS`.
  - CrawlLease (the one crawl a KB runs): `pk=KnowledgeBase#{kb_id}`, `sk=CrawlLease`, claimed with a conditional put
    (free, lapsed, or already this job's). It's its own item, so saving the KB can't erase it.
  - CrawlStep / CrawledPage (what one run did): `pk=CrawlJob#{job_id}`, `sk=Step#...` / `Page#{url_hash}`.
  - Agent link: `pk=Agent#{agent_id}`, `sk=KnowledgeBase#{kb_id}`, `gsi2_pk=KnowledgeBase#{kb_id}`, `gsi2_sk=Agent#{agent_id}` (the reverse lookup uses index `gsi2`).
- Access: every route gets its KB from a dependency in `router.py` built with `kb_with(action)`: `can_describe_kb`, `can_read_kb`, `can_update_kb`, `can_crawl_kb`, `can_delete_kb` (actions `knowledge:Describe|Get|Update|Crawl|Delete`, defined in `src/iam/actions.py`; share roles in `src/iam/shares.py`). Creation checks `knowledge:Create`. A KB the caller cannot see is 404, one they can see but not act on is 403. KBs are private to their owner unless shared; admins see metadata only (`KnowledgeBaseAccess`: owner, shared, admin).
- An agent searches only KBs `readable_by_agent` returns: the link outlives a share, so reads are checked against the agent owner each time.
- Uploads are documents (`src/documents/`, docs/LLD-documents.md): `POST .../content-upload` stores the file and answers
  202; it is read and indexed in the background, and `GET .../documents` shows its status. A document is the page
  `file://{kb_id}/{filename}`. Deleting a document takes its page out first (`KnowledgeBaseService.remove_page`).
  `ContentUpload` rows (`GET .../uploads`) are history from before documents; new uploads don't write them.
- Delete is soft: status `DELETED`, 30-day `ttl` (`SOFT_DELETE_TTL_DAYS`). **The vectors go first, and if they can't be
  deleted nothing else is** (`DeleteResult.retryable`, 503 from the route, the KB stays as it was): chunks are what
  record that vectors exist, so deleting them first leaves vectors nothing can find. Pinecone not being configured
  counts as "can't" for a KB with content. Then chunks, pages, links and shares go. `DELETED` KBs count as missing everywhere.
- A deleted KB's namespace left by the old behaviour: `scripts/reconcile_kb_vectors.py --deleted` (dry run by default).
- Forms: `schemas.py` builds `Form`/`FormInput` (see `src/form_models.py`), served at `GET .../forms/<name>`; keep field names stable.
- Crawl settings (`crawl_job_*`, `pinecone_*`, `embedding_*`) are in `config/settings.py`. A heartbeat failing, or the
  lease taken by another job, means the job was stopped: `CrawlJobStoppedError`.
- Create crawl jobs only with `create_crawl_job`: a second crawl of a KB is refused while one holds its lease (409 from
  the route, a message from `recrawl`, an error from a blueprint apply). The lease lapses after
  `crawl_job_stale_timeout_seconds` if its worker died.
- Crawl jobs and pages are listed a page at a time (`Paginated`, `limit` and `cursor`): `GET .../crawl-jobs` (5 newest by
  default) and `GET .../pages` (filter by `state`, `search`), with `GET .../pages/counts` for the tabs. Job keys are random
  and page keys are hashes, so neither order is a DynamoDB sort order: the repository reads the partition, sorts, and
  the cursor holds the last item's place in that order (`created_at`; or rank and address). Don't make a list in this
  module return everything; the SPA shows a few and loads more. `GET .../pages/detail?url=` gives one page with its
  chunks in page order (what the dashboard's side panel shows) and the pages that say the same.
- A KB's stats count what it holds (its pages with chunks, from the ledger), not what the last run read.
- `access.py` registers `RESOLVERS["knowledge-base"]` at import so shares can resolve a KB. Importing the module is what wires it.

## Add a KB endpoint

1. Pick the action and dependency: `kb: Annotated[KnowledgeBase, Depends(can_update_kb)]` in `router.py`. Add a new action only in `iam/actions.py` and the role tuples in `iam/shares.py`.
2. Put DynamoDB access in the matching repository class in `repository.py`; put anything touching several stores in `KnowledgeBaseService`.
3. Add request/response models to `models.py`. Look at `POST /{kb_id}/search` or the content-upload route for a complete example.
4. Test in `tests/test_knowledge_access.py` style: members, shares, cross-account 404.

## Testing

```bash
uv run pytest tests/test_knowledge_access.py tests/test_agent_knowledge_links.py tests/test_crawl_job_liveness.py tests/test_crawl_launch.py tests/test_crawl_lease.py tests/test_knowledge_recrawl.py tests/test_knowledge_uploads.py tests/test_knowledge_delete.py -q
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
