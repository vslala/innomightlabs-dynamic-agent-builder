# Crawler Contribution Guide

`crawler/` turns a URL into searchable chunks: discover URLs, fetch and extract content, chunk it, embed it, and upsert vectors to Pinecone, recording progress as it goes. The worker is started by `knowledge/crawl_launch.py` (in-process or Lambda). It writes through the `knowledge` repositories and the `vectorstore` clients.

## Layout

```text
src/crawler/
  __init__.py       Public exports
  worker.py         CrawlerWorker: the whole pipeline, checkpoints, events; generate_chunk_id
  discovery.py      Sitemap parsing and link crawling (UrlDiscovery)
  robots.py         robots.txt parsing and rules
  extractor.py      HTML -> ExtractedContent / ExtractedSection
  events.py         CrawlEvent and one builder function per event type (SSE)
  chunking/
    base.py         ChunkingStrategy ABC, ChunkingConfig, ContentChunkData
    hierarchical.py The one strategy; get_chunking_strategy(name) factory
```

## Conventions

- Pipeline order: discovery, fetch, extract, chunk, embed, upsert. Each stage emits a `CrawlEvent` and records a `CrawlStep`/`CrawledPage` through the knowledge repositories. The crawler owns no DynamoDB keys of its own.
- Long crawls checkpoint (`CrawlCheckpoint`) so Lambda can continue; the worker heartbeats via `CrawlJobStateService` and stops when `CrawlJobStoppedError` is raised.
- `generate_chunk_id(kb_id, source_url, chunk_index, level)` is deterministic: re-crawling a page overwrites its chunks and vectors rather than duplicating them. Do not change its inputs.
- Embeddings and Pinecone are lazy properties on `CrawlerWorker` so import stays cheap and tests can inject fakes.
- Outbound fetches respect robots.txt and `CrawlConfig` limits (max pages, depth). Honour them in any new fetching code.
- Chunk strategies are selected by name in `get_chunking_strategy` (unknown names fall back to hierarchical). The enum of names is `ChunkingStrategy` in `knowledge/models.py`.

## Add a chunking strategy

1. Subclass `ChunkingStrategy` in `chunking/<name>.py`, implementing the abstract method(s) from `chunking/base.py`, returning `ContentChunkData`.
2. Add it to the `strategies` dict in `get_chunking_strategy` (`hierarchical.py` today) and export from `chunking/__init__.py`.
3. Add the value to `ChunkingStrategy` in `knowledge/models.py` and the crawl config form in `knowledge/schemas.py`.
4. Test in `tests/crawler/test_chunking.py`.

Adding a pipeline event: add a member to `CrawlEventType` and a builder next to the others in `events.py`.

## Testing

```bash
uv run pytest tests/crawler tests/test_crawl_job_liveness.py tests/test_crawl_launch.py -q
uv run ruff check src/crawler && uv run mypy src/crawler
```

`tests/crawler/` has pure unit tests (chunking, robots). There is no `CrawlerWorker` test yet: `tests/test_crawl_launch.py` and `tests/test_crawl_job_liveness.py` cover launching and job liveness. If you add worker tests, inject fake embeddings and Pinecone through the lazy properties and never fetch real sites.

## Do / Don't

- Do keep stages pure where possible (extractor and chunkers take data in, return data out).
- Do pass `CrawlJob`/`kb_id`/`account_id` explicitly; the worker has no request context.
- Don't call Pinecone or Bedrock at import time.
- Don't add a second chunker "just in case"; add one when a KB needs it.
- Don't swallow errors silently: record them with `page_error_event` and a failed `CrawledPage`.
