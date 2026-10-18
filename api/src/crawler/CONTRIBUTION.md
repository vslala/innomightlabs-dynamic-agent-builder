# Crawler Contribution Guide

`crawler/` keeps a knowledge base matching a site. It discovers URLs, fetches and extracts each page, and chunks it.
It embeds only what's new and writes it, and it removes what the site says is gone, recording progress as it goes.
The worker is started by `knowledge/crawl_launch.py` (in-process or Lambda). It writes through the `knowledge`
repositories and the `vectorstore` clients. The design and its reasons are in
[docs/LLD-knowledge-freshness.md](../../../docs/LLD-knowledge-freshness.md).

## Layout

```text
src/crawler/
  __init__.py       Public exports
  worker.py         CrawlerWorker: discovery, the per-page read (PageRead), checkpoints, steps and progress
  page_index.py     PageIndex: the only code that writes, removes or marks a page, in the order that's safe to stop
  page_chunks.py    chunk_id (content-addressed), prepare_page (which chunks are new), text_hash, vectors_for
  extractor.py      fetch() -> Fetched with a FetchOutcome (OK, NOT_MODIFIED, GONE, FAILED); HTML -> ExtractedContent
  discovery.py      Sitemap parsing and link crawling (UrlDiscovery)
  robots.py         robots.txt parsing and rules
  events.py         CrawlEvent and one builder function per event type
  chunking/
    base.py         ChunkingStrategy ABC, ChunkingConfig, ContentChunkData
    hierarchical.py The one strategy; get_chunking_strategy(name) factory
```

## Conventions

- **Search can only say what DynamoDB has.** Search finds vectors in Pinecone and returns the text of their chunks in
  DynamoDB, and it drops a vector with no chunk. So deleting a chunk is what takes text out of answers, and a vector
  left behind is inert. Every write keeps that in mind.
- **One door for writes.** Pages change only through `PageIndex`: `write` (a page as read now), `remove` (the site said
  it's gone), `seen` (read again and unchanged), `failed` (a read that proves nothing). Don't write chunks or vectors
  for a page anywhere else. Uploads go through `PageIndex.write` too.
- **The write order** (`page_index.py`):
  1. embed the new chunks;
  2. move everything the write touches into `pending_ids`: what it writes, what it deletes, and anything an earlier
     write left pending;
  3. upsert their vectors (`upsert` raises if any batch fails);
  4. put their chunks;
  5. delete the chunks the page lost (the commit point);
  6. save the page;
  7. delete the old vectors.

  A run that stops anywhere leaves a page the next write finishes. Pending ids are never trusted to exist: a write
  rewrites the ones the page still has and deletes the rest, so `chunk_ids` only lists chunks that fully exist.
  `remove` marks the page pending the same way before it deletes.
- **The page ledger is the truth.** `KnowledgePage` lists each page's chunk ids, so stale chunks are found without
  reading the knowledge base's chunks. A knowledge base from before the ledger is adopted on its first `load()`.
- **Only the site deletes.** A page is removed only when it answers 404 or 410, redirects to another site, or is now
  disallowed by robots.txt. A timeout, a 5xx, a 403, a page with no text and a page that gives no chunks are all
  `FAILED`: it keeps the chunks of its last good read, and the ledger counts the failures (`needs_attention`).
- **Not found is not gone.** After discovery, `_pages_to_verify` appends this source's pages that discovery missed
  (up to `max_pages`, least recently read first) to the run's URLs. They're read like any page, so an unlinked or
  capped page answers 200 and is kept. A crawl only verifies pages whose `source` is its own; uploads are never verified.
- **Chunk ids say what the chunk says.** `chunk_id(kb, url, title, level, content, occurrence)`: unchanged text keeps
  its id wherever it moves, and an edit makes a new chunk instead of overwriting one. Don't add positional inputs.
  Anything the vector or its metadata is made from must be an input.
- **Unchanged pages are skipped only when settled.** A settled page has validators sent back (ETag, Last-Modified), so
  it may answer 304, and it's skipped when its `text_hash` matches. A page with pending ids or failed reads is always
  read in full.
- **One crawl per knowledge base.** Jobs are created with `create_crawl_job`, which takes the knowledge base's
  `CrawlLease`. The worker takes it again before starting and renews it on every heartbeat. It stops with
  `CrawlJobStoppedError` if another job holds it, and releases it when the job ends.
- Long crawls checkpoint (`CrawlCheckpoint`) so Lambda can continue. The checkpoint holds the run's URLs, including
  the pages to verify.
- Embeddings and Pinecone are lazy properties on `CrawlerWorker`, and `extractor` and `robots` are attributes, so
  import stays cheap and tests can inject fakes.
- Outbound fetches respect robots.txt and `CrawlConfig` limits (max pages, depth). Honour them in any new fetching code.
- Chunk strategies are selected by name in `get_chunking_strategy` (unknown names fall back to hierarchical). The enum
  of names is `ChunkingStrategy` in `knowledge/models.py`.

## Add a chunking strategy

1. Subclass `ChunkingStrategy` in `chunking/<name>.py`, implementing the abstract method(s) from `chunking/base.py`,
   returning `ContentChunkData`.
2. Add it to the `strategies` dict in `get_chunking_strategy` (`hierarchical.py` today) and export from
   `chunking/__init__.py`.
3. Add the value to `ChunkingStrategy` in `knowledge/models.py` and the crawl config form in `knowledge/schemas.py`.
4. Test in `tests/crawler/test_chunking.py`.

The strategy's name is part of `text_hash`, so switching a crawl to another strategy re-chunks every page once.

Adding a pipeline event: add a member to `CrawlEventType` and a builder next to the others in `events.py`.

## Testing

```bash
uv run pytest tests/crawler tests/test_crawl_lease.py tests/test_crawl_job_liveness.py tests/test_crawl_launch.py tests/test_knowledge_uploads.py -q
uv run ruff check src/crawler && uv run mypy src/crawler
```

`tests/crawler/fakes.py` gives a fake site (pages, links, robots.txt, ETags), a fake index with Pinecone's contract
(failing upserts and deletes on demand) and counting embeddings. Use `a_crawl(monkeypatch)`: `read(url)` runs one page
through the real worker, and `crawl()` runs a whole job. Never fetch real sites.

- `test_reading_a_page_again.py`: what's embedded on a re-read (edits, insertions, retitles, content ids).
- `test_page_outcomes.py`: gone, failed, moved, and failed vector writes and deletes.
- `test_keeping_pages_current.py`: whole crawls removing, keeping and verifying pages, adoption, crash recovery.
- `test_unchanged_pages.py`: 304s and text hashes, and never skipping an unsettled page.
- `test_fetch_outcomes.py`: how an HTTP response classifies.

## Do / Don't

- Do keep stages pure where possible (extractor and chunkers take data in, return data out).
- Do pass `CrawlJob`/`kb_id`/`account_id` explicitly; the worker has no request context.
- Don't call Pinecone or Bedrock at import time.
- Don't delete a page for not being found, for failing, or for any reason but the site's own answer.
- Don't add a second chunker "just in case"; add one when a KB needs it.
- Don't swallow errors silently: a failed read is recorded on the page (`PageIndex.failed`) and in a failed
  `CrawledPage`.
