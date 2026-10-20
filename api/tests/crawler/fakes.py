"""A site, an index and an embedding model to crawl against, so tests drive the real worker without the network.

`a_crawl(monkeypatch)` gives a knowledge base and a worker wired to these fakes, with:

- `read(url)`: one page through the worker, as a run of its own would read it;
- `crawl()`: a whole crawl job, discovery to completion, over the pages the site links to (`site.linked`).
"""

from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import AsyncIterator

from src.crawler.discovery import DiscoveredUrl
import httpx

from src.crawler.extractor import ContentExtractor, ExtractedContent, Fetched, FetchOutcome
from src.crawler.page_fetch import PageFetch, page_from_response, readable
from src.crawler.robots import RobotsTxt
from src.crawler.worker import CrawlContext, CrawlerWorker, PageRead
from src.knowledge.crawl_launch import create_crawl_job
from src.knowledge.models import CrawlConfig, CrawlJob, CrawlSourceType, KnowledgeBase, KnowledgePage
from src.knowledge.repository import ContentChunkRepository, CrawlJobRepository, KnowledgeBaseRepository, KnowledgePageRepository
from src.vectorstore.embeddings import EmbeddingResult
from src.vectorstore.pinecone_client import VectorStoreError
from tests.mock_data import TEST_USER_EMAIL, kb_fields, user_id_for

SITE = "https://example.com"


def read_response(url: str, response: httpx.Response) -> Fetched:
    """What the extractor makes of the response a fetch of `url` ended on, without going to the network."""
    extractor, page = ContentExtractor(), page_from_response(response)
    content = extractor.extract(page.url, page.html) if readable(url, page) else None
    return extractor._outcome(url, PageFetch(page, content))


def paragraphs(count: int, *, edit: int | None = None, topic: str = "plans, seats and billing") -> str:
    """A page of `count` paragraphs long enough to chunk on their own; `edit` changes one of them."""
    return "\n\n".join(
        f"Paragraph {n}: " + ("EDITED " if n == edit else "") + f"{topic} explained at length. " * 12
        for n in range(count)
    )


@dataclass(frozen=True)
class Redirect:
    to: str


@dataclass
class FakeSite:
    """What each URL answers (page text, an HTTP status, or a `Redirect`), which of them the site links to, and what
    its robots.txt disallows."""

    pages: dict[str, object] = field(default_factory=dict)
    linked: list[str] = field(default_factory=list)
    #: Every page's title.
    title: str = "Pricing"
    #: Whether the site sends ETags (and so answers 304 to one that still matches).
    etags: bool = False
    disallowed: set[str] = field(default_factory=set)
    fetched: list[str] = field(default_factory=list)

    async def fetch(self, url: str, *, etag: str | None = None, last_modified: str | None = None) -> Fetched:
        self.fetched.append(url)
        answer = self.pages.get(url, 404)
        if isinstance(answer, str) and etag and etag == self.etag_of(url):
            return Fetched(FetchOutcome.NOT_MODIFIED, url)
        if isinstance(answer, Redirect):
            url, answer = answer.to, self.pages.get(answer.to, 404)
        if isinstance(answer, str):
            content = ExtractedContent(url=url, title=self.title, full_text=answer)
            return Fetched(FetchOutcome.OK, url, content, etag=self.etag_of(url) if self.etags else None)
        outcome = FetchOutcome.GONE if answer in (404, 410) else FetchOutcome.FAILED
        return Fetched(outcome, url, reason=f"HTTP {answer}")

    def etag_of(self, url: str) -> str:
        """A strong validator of what the page says now, as a site that sends them would give."""
        return f'"{hash((url, str(self.pages.get(url)), self.title))}"'

    def publish(self, url: str, text: str) -> None:
        """A linked page with this text."""
        self.pages[url] = text
        if url not in self.linked:
            self.linked.append(url)


class FakeRobots:
    def __init__(self, site: FakeSite) -> None:
        self.site = site

    async def fetch_and_parse(self, base_url: str) -> RobotsTxt:
        return RobotsTxt()

    def is_allowed(self, url: str, robots: RobotsTxt) -> bool:
        return url not in self.site.disallowed


class FakeDiscovery:
    """Finds what the site links to, up to `max_pages`."""

    site: FakeSite

    def __init__(self, config, renderer=None) -> None:
        self.max_pages = config.max_pages

    async def discover_from_url(self, start_url: str) -> AsyncIterator[DiscoveredUrl]:
        for url in self.site.linked[: self.max_pages]:
            yield DiscoveredUrl(url=url, source="crawl")

    discover_from_sitemap = discover_from_url


@dataclass(frozen=True)
class PageRun:
    """One page through the worker: the run's context, and what came of the page."""

    ctx: CrawlContext
    read: PageRead | None
    error: Exception | None = None


class CountingEmbeddings:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def embed_texts_async(self, texts: list[str], **_: object) -> list[EmbeddingResult]:
        self.texts += texts
        return [EmbeddingResult(embedding=[float(len(text))], input_text_token_count=1) for text in texts]


class FakeIndex:
    """Pinecone's contract: `upsert` raises when it fails, `delete_by_ids` returns what it couldn't delete."""

    def __init__(self) -> None:
        self.vectors: dict[str, list[float]] = {}
        self.failing_upserts = 0
        self.failing_deletes = 0

    def upsert(self, vectors: list, kb_id: str) -> int:
        if self.failing_upserts:
            self.failing_upserts -= 1
            raise VectorStoreError("Pinecone is down")
        self.vectors.update({vector.id: vector.values for vector in vectors})
        return len(vectors)

    def list_ids(self, kb_id: str):
        return iter(list(self.vectors))

    def delete_by_ids(self, ids: list[str], kb_id: str) -> list[str]:
        if self.failing_deletes:
            self.failing_deletes -= 1
            return list(ids)
        for chunk_id in ids:
            self.vectors.pop(chunk_id, None)
        return []


def a_crawl(monkeypatch, source: str = SITE, *, max_pages: int = 100) -> SimpleNamespace:
    kb = KnowledgeBaseRepository().save(KnowledgeBase(name="Site", **kb_fields(TEST_USER_EMAIL)))
    config = CrawlConfig(source_type=CrawlSourceType.URL, source_url=source, max_pages=max_pages, rate_limit_ms=0)
    site, embeddings, index = FakeSite(), CountingEmbeddings(), FakeIndex()
    worker = CrawlerWorker()
    worker.extractor, worker.robots = site, FakeRobots(site)  # type: ignore[assignment]
    worker._embeddings, worker._pinecone = embeddings, index
    FakeDiscovery.site = site
    monkeypatch.setattr("src.crawler.worker.UrlDiscovery", FakeDiscovery)

    async def read(url: str, *, by: str = source) -> PageRun:
        """One page through the worker, as a run of a crawl of `by` would read it, whatever the outcome."""
        job = CrawlJob(kb_id=kb.kb_id, created_by=user_id_for(TEST_USER_EMAIL), config=config.model_copy(update={"source_url": by}))
        ctx = CrawlContext(job=job, kb=kb, account_id=kb.account_id)
        ctx.pages = worker._index(ctx).load()
        try:
            return PageRun(ctx, await worker._process_single_url(ctx, url))
        except Exception as error:
            return PageRun(ctx, None, error)

    async def crawl(max_pages: int = max_pages) -> CrawlJob:
        """A whole crawl job, as the dashboard or a schedule starts one."""
        job = create_crawl_job(kb.kb_id, config.model_copy(update={"max_pages": max_pages}), user_id_for(TEST_USER_EMAIL))
        await worker.run(job.job_id, kb.kb_id, kb.account_id)
        finished = CrawlJobRepository().find_by_id(job.job_id, kb.kb_id)
        assert finished is not None
        return finished

    def chunks(url: str | None = None) -> list:
        stored = ContentChunkRepository().find_all_by_kb(kb.kb_id)
        return [chunk for chunk in stored if url is None or chunk.source_url == url]

    def pages() -> dict[str, KnowledgePage]:
        return {page.url: page for page in KnowledgePageRepository().list_by_kb(kb.kb_id)}

    return SimpleNamespace(
        kb=kb, worker=worker, site=site, embeddings=embeddings, index=index,
        read=read, crawl=crawl, chunks=chunks, pages=pages,
    )
