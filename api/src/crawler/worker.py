"""
Crawler Worker - Main crawl orchestration logic.

This module handles the complete crawl pipeline:
1. URL Discovery (sitemap or crawl-based)
2. Page Fetching & Content Extraction
3. Hierarchical Chunking
4. Embedding Generation (Bedrock Titan)
5. Vector Storage (Pinecone)
6. Progress Tracking & Audit Logging

Supports Lambda continuation via checkpoints for long-running crawls.
"""

import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import AsyncIterator, Callable, NoReturn, Optional

import boto3

from src.config import settings
from src.knowledge.models import (
    KnowledgeBase,
    CrawlJob,
    CrawlJobStatus,
    CrawlStep,
    CrawlStepType,
    CrawledPage,
    CrawledPageStatus,
    CrawlProgress,
    CrawlCheckpoint,
    PageMetadata,
    PageTiming,
    CrawlSourceType,
    KnowledgePage,
    KnowledgePageState,
)
from src.knowledge.repository import (
    KnowledgeBaseRepository,
    CrawlJobRepository,
    CrawlStepRepository,
    CrawledPageRepository,
    ContentChunkRepository,
    KnowledgePageRepository,
)
from src.knowledge.run_state import CrawlJobStateService, CrawlJobStoppedError
from src.crawler.discovery import UrlDiscovery, DiscoveryConfig
from src.crawler.extractor import ContentExtractor, ExtractedContent, Fetched, FetchOutcome
from src.crawler.renderer import configured_page_renderer
from src.crawler.chunking import get_chunking_strategy
from src.crawler.page_chunks import READER_VERSION, text_hash
from src.crawler.page_index import PageIndex, address_rank, held
from src.crawler.robots import RobotsParser, RobotsTxt
from src.crawler.events import (
    CrawlEvent,
    job_started_event,
    job_progress_event,
    job_checkpoint_event,
    job_completed_event,
    job_failed_event,
    url_discovered_event,
    page_fetch_start_event,
    page_fetch_complete_event,
    page_parse_complete_event,
    page_chunk_complete_event,
    page_ingest_complete_event,
    page_error_event,
)

log = logging.getLogger(__name__)


class PageNotRead(Exception):
    """The page couldn't be read this time; what the knowledge base had of it is kept."""


class PageRead(str, Enum):
    """What reading a page did to the knowledge base. A read that failed raises `PageNotRead` instead."""

    INDEXED = "indexed"
    #: It said what it said last time (a 304, or the same text): nothing was chunked or embedded.
    UNCHANGED = "unchanged"
    #: The site said it's gone, and it was taken out.
    REMOVED = "removed"
    #: It says what another page says, so it was kept out of the index.
    DUPLICATE = "duplicate"


# Lambda timeout buffer (save checkpoint 30s before timeout)
LAMBDA_TIMEOUT_BUFFER_MS = 30000
DEFAULT_LAMBDA_TIMEOUT_MS = 300000  # 5 minutes


@dataclass
class CrawlContext:
    """Context for a crawl job execution."""
    job: CrawlJob
    kb: KnowledgeBase
    account_id: str

    # Repositories
    job_repo: CrawlJobRepository = field(default_factory=CrawlJobRepository)
    step_repo: CrawlStepRepository = field(default_factory=CrawlStepRepository)
    page_repo: CrawledPageRepository = field(default_factory=CrawledPageRepository)
    chunk_repo: ContentChunkRepository = field(default_factory=ContentChunkRepository)
    kb_repo: KnowledgeBaseRepository = field(default_factory=KnowledgeBaseRepository)
    state_service: CrawlJobStateService = field(default_factory=CrawlJobStateService)

    # Runtime state
    start_time_ms: int = 0
    timeout_ms: int = DEFAULT_LAMBDA_TIMEOUT_MS
    discovered_urls: list[str] = field(default_factory=list)
    current_url_index: int = 0

    # Progress counters
    processed_count: int = 0
    successful_count: int = 0
    failed_count: int = 0
    removed_count: int = 0
    unchanged_count: int = 0
    duplicate_count: int = 0
    total_chunks: int = 0
    total_embeddings: int = 0
    last_heartbeat_monotonic: float = 0.0

    # Event callback (for SSE streaming)
    event_callback: Optional[Callable[[CrawlEvent], None]] = None

    knowledge_pages: KnowledgePageRepository = field(default_factory=KnowledgePageRepository)
    #: The knowledge base's pages by URL, read once per run (`PageIndex.load`) and kept current as pages are written.
    pages: dict[str, KnowledgePage] = field(default_factory=dict)
    #: The site's robots.txt, read the first time a page is checked against it.
    robots: Optional[RobotsTxt] = None

    def page(self, url: str) -> KnowledgePage:
        """The page as the knowledge base has it, or a new one this crawl owns."""
        return self.pages.get(url) or KnowledgePage(kb_id=self.kb.kb_id, url=url, source=self.job.config.source_url)

    def keep(self, page: KnowledgePage) -> None:
        self.pages[page.url] = page

    def emit_event(self, event: CrawlEvent) -> None:
        """Emit an event if callback is registered."""
        if self.event_callback:
            try:
                self.event_callback(event)
            except Exception as e:
                log.warning(f"Failed to emit event: {e}")

    def should_checkpoint(self) -> bool:
        """Check if we should save a checkpoint (approaching timeout)."""
        elapsed_ms = int((time.time() * 1000) - self.start_time_ms)
        remaining_ms = self.timeout_ms - elapsed_ms
        return remaining_ms < LAMBDA_TIMEOUT_BUFFER_MS

    def get_progress(self) -> CrawlProgress:
        """Get current progress."""
        return CrawlProgress(
            discovered_urls=len(self.discovered_urls),
            processed_urls=self.processed_count,
            successful_urls=self.successful_count,
            failed_urls=self.failed_count,
            removed_urls=self.removed_count,
            unchanged_urls=self.unchanged_count,
            duplicate_urls=self.duplicate_count,
            total_chunks=self.total_chunks,
            total_embeddings=self.total_embeddings,
        )

    def heartbeat(self, *, force: bool = False) -> None:
        """Persist liveness and progress.

        Unforced calls (e.g. the discovery loop, or the top of each processing
        iteration) are throttled to `crawl_job_heartbeat_interval_seconds` so a
        fast crawl doesn't write on every single URL. `force=True` bypasses the
        throttle entirely and always writes - used at job start and after each
        page finishes processing, where callers want progress to be durable and
        current immediately rather than rate-limited.
        """
        now = time.monotonic()
        heartbeat_interval = settings.crawl_job_heartbeat_interval_seconds
        if not force and now - self.last_heartbeat_monotonic < heartbeat_interval:
            return

        self.job.progress = self.get_progress()
        self.state_service.heartbeat(self.job)
        self.last_heartbeat_monotonic = now


class CrawlerWorker:
    """
    Main crawler worker that orchestrates the crawl pipeline.

    Usage:
        worker = CrawlerWorker()
        await worker.run(job_id, kb_id, account_id)

    Or with event streaming:
        async for event in worker.run_with_events(job_id, kb_id, account_id):
            yield event.to_sse()
    """

    def __init__(self) -> None:
        # One browser for both ways the crawler reads a page: its text, and the links on it.
        self.renderer = configured_page_renderer()
        self.extractor = ContentExtractor(renderer=self.renderer)
        self.robots = RobotsParser()
        self._embeddings = None
        self._pinecone = None

    @property
    def embeddings(self):
        """Lazy-load embeddings service."""
        if self._embeddings is None:
            from src.vectorstore import get_embeddings_service
            self._embeddings = get_embeddings_service()
        return self._embeddings

    @property
    def pinecone(self):
        """Lazy-load Pinecone client."""
        if self._pinecone is None:
            from src.vectorstore import get_pinecone_client
            self._pinecone = get_pinecone_client(validate=True)
        return self._pinecone

    async def run(
        self,
        job_id: str,
        kb_id: str,
        account_id: str,
        timeout_ms: int = DEFAULT_LAMBDA_TIMEOUT_MS,
    ) -> CrawlJob:
        """
        Run a crawl job to completion (or checkpoint).

        Args:
            job_id: The crawl job ID
            kb_id: The knowledge base ID
            account_id: The account the KB is in
            timeout_ms: Lambda timeout in milliseconds

        Returns:
            Updated CrawlJob
        """
        events = []

        def collect_event(event: CrawlEvent):
            events.append(event)

        return await self._execute(job_id, kb_id, account_id, timeout_ms, collect_event)

    async def run_with_events(
        self,
        job_id: str,
        kb_id: str,
        account_id: str,
        timeout_ms: int = DEFAULT_LAMBDA_TIMEOUT_MS,
    ) -> AsyncIterator[CrawlEvent]:
        """
        Run a crawl job and yield events for SSE streaming.

        Args:
            job_id: The crawl job ID
            kb_id: The knowledge base ID
            account_id: The account the KB is in
            timeout_ms: Lambda timeout in milliseconds

        Yields:
            CrawlEvent objects for real-time progress updates
        """
        event_queue: asyncio.Queue[CrawlEvent] = asyncio.Queue()
        job_done = asyncio.Event()

        def queue_event(event: CrawlEvent):
            event_queue.put_nowait(event)

        async def run_job():
            try:
                await self._execute(job_id, kb_id, account_id, timeout_ms, queue_event)
            finally:
                job_done.set()

        # Start job in background
        job_task = asyncio.create_task(run_job())

        # Yield events as they arrive
        while not job_done.is_set() or not event_queue.empty():
            try:
                event = await asyncio.wait_for(event_queue.get(), timeout=0.5)
                yield event
            except asyncio.TimeoutError:
                continue

        # Ensure job task is complete
        await job_task

    async def _execute(
        self,
        job_id: str,
        kb_id: str,
        account_id: str,
        timeout_ms: int,
        event_callback: Callable[[CrawlEvent], None],
    ) -> CrawlJob:
        """Execute the crawl job."""
        # Load job and KB
        job_repo = CrawlJobRepository()
        kb_repo = KnowledgeBaseRepository()

        job = job_repo.find_by_id(job_id, kb_id)
        if not job:
            raise ValueError(f"Crawl job {job_id} not found")

        is_continuation = job.status == CrawlJobStatus.IN_PROGRESS and job.checkpoint is not None
        if job.status not in {CrawlJobStatus.PENDING, CrawlJobStatus.FAILED} and not is_continuation:
            log.info("Did not start crawl job %s because its status is %s", job_id, job.status.value)
            return job

        kb = kb_repo.find_in_account(account_id, kb_id)
        if not kb:
            raise ValueError(f"Knowledge base {kb_id} not found")

        # Create context
        ctx = CrawlContext(
            job=job,
            kb=kb,
            account_id=account_id,
            start_time_ms=int(time.time() * 1000),
            timeout_ms=timeout_ms,
            event_callback=event_callback,
        )

        if job.checkpoint:
            ctx.discovered_urls = job.checkpoint.pending_urls
            ctx.current_url_index = job.checkpoint.current_url_index
            # Restore progress counters from previous run
            if job.progress:
                ctx.processed_count = job.progress.processed_urls
                ctx.successful_count = job.progress.successful_urls
                ctx.failed_count = job.progress.failed_urls
                ctx.removed_count = job.progress.removed_urls
                ctx.unchanged_count = job.progress.unchanged_urls
                ctx.duplicate_count = job.progress.duplicate_urls
                ctx.total_chunks = job.progress.total_chunks
                ctx.total_embeddings = job.progress.total_embeddings
            log.info(f"Resuming from checkpoint at index {ctx.current_url_index}, previously processed {ctx.processed_count} URLs")

        if not ctx.state_service.hold(job):
            log.info("Did not start crawl job %s because another crawl of the knowledge base holds it", job_id)
            return job

        try:
            expected_status = job.status.value
            job.status = CrawlJobStatus.IN_PROGRESS
            job.error_message = None
            if not job.timing.started_at:
                job.timing.started_at = datetime.now(timezone.utc)
            if not job_repo.save_if_status(job, expected_status=expected_status):
                latest_job = job_repo.find_by_id(job_id, kb_id)
                if latest_job is not None:
                    log.info("Did not start crawl job %s because its status changed", job_id)
                    return latest_job
                raise ValueError(f"Crawl job {job_id} disappeared before execution")

            ctx.emit_event(job_started_event(
                job_id=job_id,
                kb_id=kb_id,
                source_url=job.config.source_url,
                max_pages=job.config.max_pages,
            ))

            self._log_step(ctx, CrawlStepType.JOB_STARTED, details={
                "source_url": job.config.source_url,
                "source_type": job.config.source_type.value,
                "max_pages": job.config.max_pages,
            })
            ctx.heartbeat(force=True)

            ctx.pages = self._index(ctx).load()
            if not ctx.discovered_urls:
                await self._discover_urls(ctx)

            await self._process_urls(ctx)

            if ctx.current_url_index >= len(ctx.discovered_urls):
                await self._complete_job(ctx)
            else:
                await self._checkpoint_job(ctx)

            return ctx.job

        except CrawlJobStoppedError:
            latest_job = job_repo.find_by_id(job_id, kb_id)
            if latest_job is not None:
                log.info("Stopped crawl job %s because it is no longer active", job_id)
                return latest_job
            raise
        except Exception as e:
            log.error(f"Crawl job {job_id} failed: {e}", exc_info=True)
            await self._fail_job(ctx, str(e))
            raise

    async def _discover_urls(self, ctx: CrawlContext) -> None:
        """Discover URLs to crawl."""
        config = ctx.job.config

        discovery_config = DiscoveryConfig(
            max_pages=config.max_pages,
            max_depth=config.max_depth,
            respect_robots_txt=config.respect_robots_txt,
            rate_limit_ms=config.rate_limit_ms,
            same_domain_only=True,
        )

        discovery = UrlDiscovery(discovery_config, self.renderer)

        if config.source_type == CrawlSourceType.SITEMAP:
            url_iter = discovery.discover_from_sitemap(config.source_url)
        else:
            url_iter = discovery.discover_from_url(config.source_url)

        async for discovered in url_iter:
            ctx.discovered_urls.append(discovered.url)

            ctx.emit_event(url_discovered_event(
                job_id=ctx.job.job_id,
                kb_id=ctx.kb.kb_id,
                url=discovered.url,
                total_discovered=len(ctx.discovered_urls),
            ))

            # Log discovery
            self._log_step(ctx, CrawlStepType.URL_DISCOVERED, url=discovered.url)
            ctx.heartbeat()

            if len(ctx.discovered_urls) >= config.max_pages:
                break

        log.info(f"Discovered {len(ctx.discovered_urls)} URLs")
        ctx.discovered_urls += self._pages_to_verify(ctx)

    def _pages_to_verify(self, ctx: CrawlContext) -> list[str]:
        """This crawl's pages that discovery didn't find, to read like any other: one gone from the site says so with a
        404, one that's merely unlinked or past `max_pages` is read and kept. Least recently read first, at most
        `max_pages` of them a run; the rest wait for the next."""
        found = set(ctx.discovered_urls)
        unseen = [
            page for page in ctx.pages.values()
            if page.source == ctx.job.config.source_url and page.url not in found
            # A gone page is read again only to delete the vectors it couldn't
            and (page.state != KnowledgePageState.GONE or page.orphan_vector_ids)
        ]
        unseen.sort(key=lambda page: page.last_read_at or datetime.min.replace(tzinfo=timezone.utc))
        return [page.url for page in unseen[: ctx.job.config.max_pages]]

    async def _process_urls(self, ctx: CrawlContext) -> None:
        """Process discovered URLs."""
        config = ctx.job.config
        rate_limit_s = config.rate_limit_ms / 1000.0

        while ctx.current_url_index < len(ctx.discovered_urls):
            ctx.heartbeat()

            # Check for checkpoint
            if ctx.should_checkpoint():
                log.info("Approaching timeout, saving checkpoint")
                break

            url = ctx.discovered_urls[ctx.current_url_index]

            try:
                read = await self._process_single_url(ctx, url)
                if read is PageRead.REMOVED:
                    ctx.removed_count += 1
                else:
                    ctx.successful_count += 1
                    if read is PageRead.UNCHANGED:
                        ctx.unchanged_count += 1
                    if read is PageRead.DUPLICATE:
                        ctx.duplicate_count += 1
            except Exception as e:
                log.error(f"Failed to process {url}: {e}")
                ctx.failed_count += 1

                ctx.emit_event(page_error_event(
                    job_id=ctx.job.job_id,
                    kb_id=ctx.kb.kb_id,
                    url=url,
                    error=str(e),
                ))

            ctx.processed_count += 1
            ctx.current_url_index += 1

            # Update progress
            self._update_progress(ctx)

            # Emit progress event
            progress = ctx.get_progress()
            ctx.emit_event(job_progress_event(
                job_id=ctx.job.job_id,
                kb_id=ctx.kb.kb_id,
                discovered=progress.discovered_urls,
                processed=progress.processed_urls,
                successful=progress.successful_urls,
                failed=progress.failed_urls,
                chunks=progress.total_chunks,
            ))

            # Rate limiting
            if ctx.current_url_index < len(ctx.discovered_urls):
                await asyncio.sleep(rate_limit_s)

    async def _process_single_url(self, ctx: CrawlContext, url: str) -> PageRead:
        """Read one page: index what it says now, skip it if it says the same, or remove it if the site says it's gone.

        A page that can't be read this time (a timeout, a 5xx, no text) raises `PageNotRead` and keeps what the
        knowledge base had of it: only the site saying the page is gone deletes anything.
        """
        timing = PageTiming()
        if not await self._allowed(ctx, url):
            return self._gone(ctx, url, "robots.txt disallows it", timing)
        page = ctx.page(url)
        fetched = await self._fetch_page(ctx, url, timing, page)
        if fetched.outcome is FetchOutcome.NOT_MODIFIED:
            return self._unchanged(ctx, page, fetched, timing)
        if fetched.outcome is FetchOutcome.GONE:
            return self._gone(ctx, url, fetched.reason, timing)
        if fetched.outcome is FetchOutcome.FAILED or fetched.content is None:
            self._failed(ctx, url, fetched.reason, timing)
        if fetched.url != url:
            # It moved within the site: what it says is kept under its new address
            self._take_out(ctx, url, f"moved to {fetched.url}")

        content = fetched.content
        read = ctx.page(fetched.url)
        said = text_hash(content.title, content.full_text, ctx.job.config.chunking_strategy.value)
        if read.settled and read.text_hash == said:
            return self._unchanged(ctx, read, fetched, timing)
        twin = self._twin(ctx, read.url, said)
        if twin is not None and address_rank(twin.url) <= address_rank(read.url):
            return self._duplicate(ctx, read, twin, said, timing)
        read = read.model_copy(update={
            "text_hash": said, "etag": fetched.etag, "last_modified": fetched.last_modified,
            "description": content.description, "reader_version": READER_VERSION,
        })
        await self._index_page(ctx, read, content, timing)
        if twin is not None:
            # This is the better address for what both say: the other one now stands behind it
            better, index = ctx.pages[read.url], self._index(ctx)
            ctx.keep(index.alias(twin, of=better, text_hash=said, job_id=ctx.job.job_id))
            for other in [page for page in ctx.pages.values() if page.state == KnowledgePageState.DUPLICATE and page.duplicate_of == twin.url]:
                ctx.keep(index.repoint(other, to=better))
        return PageRead.INDEXED

    @staticmethod
    def _twin(ctx: CrawlContext, url: str, said: str) -> Optional[KnowledgePage]:
        """Another page of the knowledge base that's in the index and says exactly what this one says."""
        return next((page for page in ctx.pages.values() if page.url != url and page.settled and page.text_hash == said), None)

    def _duplicate(self, ctx: CrawlContext, page: KnowledgePage, twin: KnowledgePage, said: str, timing: PageTiming) -> PageRead:
        ctx.keep(self._index(ctx).alias(page, of=twin, text_hash=said, job_id=ctx.job.job_id))
        self._record(ctx, page.url, CrawledPageStatus.DUPLICATE, timing, error=f"says what {twin.url} says")
        self._log_step(ctx, CrawlStepType.PAGE_DUPLICATE, url=page.url, details={"duplicate_of": twin.url})
        return PageRead.DUPLICATE

    async def _allowed(self, ctx: CrawlContext, url: str) -> bool:
        if not ctx.job.config.respect_robots_txt:
            return True
        if ctx.robots is None:
            ctx.robots = await self.robots.fetch_and_parse(ctx.job.config.source_url)
        return self.robots.is_allowed(url, ctx.robots)

    def _index(self, ctx: CrawlContext) -> PageIndex:
        return PageIndex(
            ctx.kb.kb_id, vectors=self.pinecone, embeddings=self.embeddings,
            chunks=ctx.chunk_repo, pages=ctx.knowledge_pages,
        )

    def _gone(self, ctx: CrawlContext, url: str, reason: str, timing: PageTiming) -> PageRead:
        """The site says the page is gone: take it out. One the knowledge base never had is a broken link, a failed read."""
        if not self._take_out(ctx, url, reason):
            self._record(ctx, url, CrawledPageStatus.FAILED, timing, error=reason)
            raise PageNotRead(reason)
        self._record(ctx, url, CrawledPageStatus.GONE, timing, error=reason)
        return PageRead.REMOVED

    def _take_out(self, ctx: CrawlContext, url: str, reason: str) -> bool:
        """Remove the page if the knowledge base has anything of it; whether it did."""
        page = ctx.pages.get(url)
        # A removal that stopped halfway left the page pending, or vectors it couldn't delete: it's finished here
        if page is None or (page.state == KnowledgePageState.GONE and not page.pending_ids and not page.orphan_vector_ids):
            return False
        removed = len(page.chunk_ids)
        ctx.keep(self._index(ctx).remove(page, reason=reason, job_id=ctx.job.job_id))
        self._log_step(ctx, CrawlStepType.PAGE_REMOVED, url=url, details={"reason": reason, "removed_count": removed})
        # Pages that stood behind this one may be the only copy of its text left: read them again this run
        queued = set(ctx.discovered_urls[ctx.current_url_index + 1:])
        ctx.discovered_urls += [
            other.url for other in ctx.pages.values()
            if other.state == KnowledgePageState.DUPLICATE and other.duplicate_of == url and other.url not in queued
        ]
        return True

    def _unchanged(self, ctx: CrawlContext, page: KnowledgePage, fetched: Fetched, timing: PageTiming) -> PageRead:
        ctx.keep(self._index(ctx).seen(
            page, job_id=ctx.job.job_id,
            etag=fetched.etag or page.etag, last_modified=fetched.last_modified or page.last_modified,
        ))
        self._record(ctx, page.url, CrawledPageStatus.UNCHANGED, timing, chunk_count=len(page.chunk_ids))
        ctx.total_chunks += len(page.chunk_ids)  # covered by this run, though none was embedded
        return PageRead.UNCHANGED

    def _failed(self, ctx: CrawlContext, url: str, reason: str, timing: PageTiming) -> NoReturn:
        ctx.keep(self._index(ctx).failed(ctx.page(url), reason=reason, job_id=ctx.job.job_id))
        self._record(ctx, url, CrawledPageStatus.FAILED, timing, error=reason)
        raise PageNotRead(reason)

    def _record(
        self,
        ctx: CrawlContext,
        url: str,
        status: CrawledPageStatus,
        timing: PageTiming,
        *,
        content: Optional[ExtractedContent] = None,
        chunk_count: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """What this run did to the page, for the run's page list."""
        timing.total_duration_ms = sum(
            duration or 0 for duration in (timing.fetch_duration_ms, timing.chunk_duration_ms, timing.ingest_duration_ms)
        )
        ctx.page_repo.save(CrawledPage(
            job_id=ctx.job.job_id,
            created_by=ctx.kb.owner_id,
            url=url,
            status=status,
            page_metadata=PageMetadata(
                title=content.title,
                description=content.description,
                content_length=content.content_length,
                word_count=content.word_count,
            ) if content else PageMetadata(),
            chunk_count=chunk_count,
            timing=timing,
            error=error,
        ))

    async def _fetch_page(self, ctx: CrawlContext, url: str, timing: PageTiming, page: KnowledgePage) -> Fetched:
        """Fetch the page, sending back the validators of its last read when it's settled, so it may answer 304."""
        job_id, kb_id = ctx.job.job_id, ctx.kb.kb_id
        ctx.emit_event(page_fetch_start_event(job_id, kb_id, url))
        self._log_step(ctx, CrawlStepType.PAGE_FETCH_START, url=url)

        fetch_start = time.time()
        current = page.settled and page.reader_version == READER_VERSION
        etag, last_modified = (page.etag, page.last_modified) if current else (None, None)
        fetched = await self.extractor.fetch(url, etag=etag, last_modified=last_modified)
        timing.fetch_duration_ms = int((time.time() - fetch_start) * 1000)
        if fetched.outcome is FetchOutcome.NOT_MODIFIED:
            return fetched
        if fetched.outcome is not FetchOutcome.OK or fetched.content is None:
            self._log_step(ctx, CrawlStepType.PAGE_FETCH_ERROR, url=url,
                           details={"outcome": fetched.outcome.value, "error": fetched.reason})
            return fetched

        content = fetched.content
        ctx.emit_event(page_fetch_complete_event(
            job_id, kb_id, url,
            status_code=200,
            content_length=content.content_length,
            duration_ms=timing.fetch_duration_ms,
        ))
        self._log_step(ctx, CrawlStepType.PAGE_FETCH_COMPLETE, url=url, duration_ms=timing.fetch_duration_ms)
        ctx.emit_event(page_parse_complete_event(
            job_id, kb_id, url,
            title=content.title,
            word_count=content.word_count,
            duration_ms=0,  # extraction is part of the fetch
        ))
        self._log_step(ctx, CrawlStepType.PAGE_PARSE_COMPLETE, url=url,
                       details={"title": content.title, "word_count": content.word_count})
        return fetched

    async def _index_page(self, ctx: CrawlContext, page: KnowledgePage, content: ExtractedContent, timing: PageTiming) -> None:
        """Chunk the page and write it into the knowledge base (`PageIndex.write`)."""
        job_id, kb_id, url = ctx.job.job_id, ctx.kb.kb_id, page.url

        chunk_start = time.time()
        chunk_data_list = get_chunking_strategy(ctx.job.config.chunking_strategy.value).chunk(
            content=content.full_text,
            source_url=url,
            page_title=content.title,
            sections=content.sections,
        )
        timing.chunk_duration_ms = int((time.time() - chunk_start) * 1000)
        ctx.emit_event(page_chunk_complete_event(
            job_id, kb_id, url,
            chunk_count=len(chunk_data_list),
            duration_ms=timing.chunk_duration_ms,
        ))
        self._log_step(ctx, CrawlStepType.PAGE_CHUNK_COMPLETE, url=url,
                       duration_ms=timing.chunk_duration_ms,
                       details={"chunk_count": len(chunk_data_list)})
        if not chunk_data_list:
            # A page with text but nothing to chunk is a bad read, not an empty page: keep what it had
            self._failed(ctx, url, "the page gave no chunks", timing)

        ingest_start = time.time()
        written = await self._index(ctx).write(page, content.title, chunk_data_list, job_id=job_id)
        ctx.keep(written.page)
        timing.ingest_duration_ms = int((time.time() - ingest_start) * 1000)
        ctx.emit_event(page_ingest_complete_event(
            job_id, kb_id, url,
            vector_count=written.embedded,
            duration_ms=timing.ingest_duration_ms,
        ))
        self._log_step(ctx, CrawlStepType.PAGE_INGEST_COMPLETE, url=url,
                       duration_ms=timing.ingest_duration_ms,
                       details={
                           "embedding_count": written.embedded,
                           "unchanged_count": written.chunks - written.embedded,
                           "removed_count": written.removed,
                       })

        self._record(ctx, url, CrawledPageStatus.SUCCESS, timing, content=content, chunk_count=written.chunks)
        ctx.total_chunks += written.chunks
        ctx.total_embeddings += written.embedded

    def _update_progress(self, ctx: CrawlContext) -> None:
        """Update job progress in database."""
        ctx.heartbeat(force=True)

    def _log_step(
        self,
        ctx: CrawlContext,
        step_type: CrawlStepType,
        url: Optional[str] = None,
        duration_ms: Optional[int] = None,
        details: Optional[dict] = None,
    ) -> None:
        """Log a crawl step to the audit log."""
        step = CrawlStep(
            job_id=ctx.job.job_id,
            step_type=step_type,
            url=url,
            duration_ms=duration_ms,
            details=details,
        )
        ctx.step_repo.save(step)

    async def _complete_job(self, ctx: CrawlContext) -> None:
        """Mark job as completed."""
        job = ctx.job
        job.status = CrawlJobStatus.COMPLETED
        job.timing.completed_at = datetime.now(timezone.utc)

        if job.timing.started_at:
            duration = job.timing.completed_at - job.timing.started_at
            job.timing.total_duration_ms = int(duration.total_seconds() * 1000)

            if ctx.processed_count > 0:
                job.timing.avg_page_duration_ms = job.timing.total_duration_ms / ctx.processed_count

        # Duplicates as the knowledge base ends the crawl with them: a page read early may have become one later
        ctx.duplicate_count = sum(1 for page in ctx.pages.values() if page.state == KnowledgePageState.DUPLICATE)
        # Chunks of the pages this run read, each once: a page reached by several links or a redirect is read several times
        ctx.total_chunks = sum(
            len(page.chunk_ids) for page in ctx.pages.values()
            if page.state == KnowledgePageState.LIVE and page.last_seen_job == job.job_id
        )
        job.progress = ctx.get_progress()
        job.checkpoint = None  # Clear checkpoint

        if not ctx.job_repo.save_if_in_progress(job):
            raise CrawlJobStoppedError(f"Crawl job {job.job_id} is no longer active")
        ctx.state_service.release(job)

        # The knowledge base as it is now, not what this run read
        total_pages, total_chunks = held(ctx.pages.values())
        ctx.kb_repo.update_stats(
            ctx.account_id, ctx.kb.kb_id, total_pages=total_pages, total_chunks=total_chunks, total_vectors=total_chunks
        )

        # Log completion
        self._log_step(ctx, CrawlStepType.JOB_COMPLETED, details={
            "total_pages": ctx.successful_count,
            "total_chunks": ctx.total_chunks,
            "duration_ms": job.timing.total_duration_ms,
        })

        # Emit completion event
        ctx.emit_event(job_completed_event(
            job_id=job.job_id,
            kb_id=ctx.kb.kb_id,
            total_pages=ctx.successful_count,
            total_chunks=ctx.total_chunks,
            duration_ms=job.timing.total_duration_ms or 0,
        ))

        log.info(f"Crawl job {job.job_id} completed: {ctx.successful_count} pages, {ctx.total_chunks} chunks")

    async def _checkpoint_job(self, ctx: CrawlContext) -> None:
        """Save checkpoint for Lambda continuation."""
        job = ctx.job
        job.checkpoint = CrawlCheckpoint(
            current_url_index=ctx.current_url_index,
            pending_urls=ctx.discovered_urls,
        )
        job.progress = ctx.get_progress()

        if not ctx.job_repo.save_if_in_progress(job):
            raise CrawlJobStoppedError(f"Crawl job {job.job_id} is no longer active")

        # Log checkpoint
        self._log_step(ctx, CrawlStepType.JOB_CHECKPOINT, details={
            "current_url_index": ctx.current_url_index,
            "pending_count": len(ctx.discovered_urls) - ctx.current_url_index,
        })

        # Emit checkpoint event
        ctx.emit_event(job_checkpoint_event(
            job_id=job.job_id,
            kb_id=ctx.kb.kb_id,
            current_index=ctx.current_url_index,
            pending_count=len(ctx.discovered_urls) - ctx.current_url_index,
        ))

        log.info(f"Crawl job {job.job_id} checkpointed at index {ctx.current_url_index}")

        # Self-invoke Lambda to continue processing
        self._invoke_continuation(job.job_id, ctx.kb.kb_id, ctx.account_id)

    def _invoke_continuation(self, job_id: str, kb_id: str, account_id: str) -> None:
        """Invoke Lambda asynchronously to continue crawl from checkpoint."""
        running_in_lambda = bool(os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))
        if not running_in_lambda and settings.async_job_backend != "lambda":
            return  # In-process crawls are resumed by run_crawl_in_background.
        function_name = settings.async_job_lambda_name or os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
        if not function_name:
            log.warning("No async Lambda function configured, skipping crawl continuation invocation")
            return

        payload = {
            "crawl_job": {
                "job_id": job_id,
                "kb_id": kb_id,
                "account_id": account_id,
            }
        }

        try:
            client = boto3.client("lambda", region_name=settings.aws_region)
            response = client.invoke(
                FunctionName=function_name,
                InvocationType="Event",  # Async invocation
                Payload=json.dumps(payload).encode("utf-8"),
            )
            log.info(f"Self-invoked Lambda for continuation, status: {response['StatusCode']}")
        except Exception as e:
            log.error(f"Failed to self-invoke Lambda: {e}")
            # Don't raise - the checkpoint is saved, manual retry is possible

    async def _fail_job(self, ctx: CrawlContext, error: str) -> None:
        """Mark job as failed."""
        job = ctx.job
        job.status = CrawlJobStatus.FAILED
        job.error_message = error
        job.progress = ctx.get_progress()
        # Snapshot whatever progress was made this run so a retry resumes from
        # here instead of the last periodic checkpoint (or from scratch).
        job.checkpoint = CrawlCheckpoint(
            current_url_index=ctx.current_url_index,
            pending_urls=ctx.discovered_urls,
        )

        if not ctx.job_repo.save_if_in_progress(job):
            log.info("Did not overwrite terminal state for crawl job %s", job.job_id)
            return
        ctx.state_service.release(job)

        # Log failure
        self._log_step(ctx, CrawlStepType.JOB_FAILED, details={"error": error})

        # Emit failure event
        ctx.emit_event(job_failed_event(
            job_id=job.job_id,
            kb_id=ctx.kb.kb_id,
            error=error,
        ))

        log.error(f"Crawl job {job.job_id} failed: {error}")


# Singleton worker instance
_worker: Optional[CrawlerWorker] = None


def get_crawler_worker() -> CrawlerWorker:
    """Get or create the crawler worker singleton."""
    global _worker
    if _worker is None:
        _worker = CrawlerWorker()
    return _worker
