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
import hashlib
import json
import logging
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional, AsyncIterator, Callable
from urllib.parse import urlparse

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
    ContentChunk,
    CrawlProgress,
    CrawlCheckpoint,
    PageMetadata,
    PageTiming,
    CrawlSourceType,
)
from src.knowledge.repository import (
    KnowledgeBaseRepository,
    CrawlJobRepository,
    CrawlStepRepository,
    CrawledPageRepository,
    ContentChunkRepository,
)
from src.crawler.discovery import UrlDiscovery, DiscoveryConfig, DiscoveredUrl
from src.crawler.extractor import ContentExtractor, ExtractedContent
from src.crawler.chunking import get_chunking_strategy, ContentChunkData
from src.crawler.events import (
    CrawlEvent,
    job_started_event,
    job_progress_event,
    job_checkpoint_event,
    job_completed_event,
    job_failed_event,
    url_discovered_event,
    url_skipped_event,
    page_fetch_start_event,
    page_fetch_complete_event,
    page_parse_complete_event,
    page_chunk_complete_event,
    page_embed_complete_event,
    page_ingest_complete_event,
    page_error_event,
)

log = logging.getLogger(__name__)

# Lambda timeout buffer (save checkpoint 30s before timeout)
LAMBDA_TIMEOUT_BUFFER_MS = 30000
DEFAULT_LAMBDA_TIMEOUT_MS = 300000  # 5 minutes


def generate_chunk_id(kb_id: str, source_url: str, chunk_index: int, level: int) -> str:
    """
    Generate a deterministic chunk ID based on content identifiers.

    This enables deduplication: re-crawling the same page produces the same
    chunk IDs, so Pinecone upsert overwrites instead of creating duplicates.

    Args:
        kb_id: Knowledge base ID
        source_url: Source URL of the page
        chunk_index: Index of the chunk within the page
        level: Hierarchical level (0=document, 1=section, 2=paragraph)

    Returns:
        Deterministic chunk ID (MD5 hash truncated to UUID-like format)
    """
    # Create a unique string from the identifiers
    identifier = f"{kb_id}:{source_url}:{chunk_index}:{level}"
    # Generate MD5 hash and format as UUID-like string
    hash_bytes = hashlib.md5(identifier.encode()).hexdigest()
    # Format: 8-4-4-4-12 to match UUID format
    return f"{hash_bytes[:8]}-{hash_bytes[8:12]}-{hash_bytes[12:16]}-{hash_bytes[16:20]}-{hash_bytes[20:32]}"


@dataclass
class CrawlContext:
    """Context for a crawl job execution."""
    job: CrawlJob
    kb: KnowledgeBase
    user_email: str

    # Repositories
    job_repo: CrawlJobRepository = field(default_factory=CrawlJobRepository)
    step_repo: CrawlStepRepository = field(default_factory=CrawlStepRepository)
    page_repo: CrawledPageRepository = field(default_factory=CrawledPageRepository)
    chunk_repo: ContentChunkRepository = field(default_factory=ContentChunkRepository)
    kb_repo: KnowledgeBaseRepository = field(default_factory=KnowledgeBaseRepository)

    # Runtime state
    start_time_ms: int = 0
    timeout_ms: int = DEFAULT_LAMBDA_TIMEOUT_MS
    discovered_urls: list[str] = field(default_factory=list)
    current_url_index: int = 0

    # Progress counters
    processed_count: int = 0
    successful_count: int = 0
    failed_count: int = 0
    total_chunks: int = 0
    total_embeddings: int = 0

    # Event callback (for SSE streaming)
    event_callback: Optional[Callable[[CrawlEvent], None]] = None

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
            total_chunks=self.total_chunks,
            total_embeddings=self.total_embeddings,
        )


class CrawlerWorker:
    """
    Main crawler worker that orchestrates the crawl pipeline.

    Usage:
        worker = CrawlerWorker()
        await worker.run(job_id, kb_id, user_email)

    Or with event streaming:
        async for event in worker.run_with_events(job_id, kb_id, user_email):
            yield event.to_sse()
    """

    def __init__(self):
        self.extractor = ContentExtractor()
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
        user_email: str,
        timeout_ms: int = DEFAULT_LAMBDA_TIMEOUT_MS,
    ) -> CrawlJob:
        """
        Run a crawl job to completion (or checkpoint).

        Args:
            job_id: The crawl job ID
            kb_id: The knowledge base ID
            user_email: The user who owns the KB
            timeout_ms: Lambda timeout in milliseconds

        Returns:
            Updated CrawlJob
        """
        events = []

        def collect_event(event: CrawlEvent):
            events.append(event)

        return await self._execute(job_id, kb_id, user_email, timeout_ms, collect_event)

    async def run_with_events(
        self,
        job_id: str,
        kb_id: str,
        user_email: str,
        timeout_ms: int = DEFAULT_LAMBDA_TIMEOUT_MS,
    ) -> AsyncIterator[CrawlEvent]:
        """
        Run a crawl job and yield events for SSE streaming.

        Args:
            job_id: The crawl job ID
            kb_id: The knowledge base ID
            user_email: The user who owns the KB
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
                await self._execute(job_id, kb_id, user_email, timeout_ms, queue_event)
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
        user_email: str,
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

        kb = kb_repo.find_by_id(kb_id, user_email)
        if not kb:
            raise ValueError(f"Knowledge base {kb_id} not found")

        # Create context
        ctx = CrawlContext(
            job=job,
            kb=kb,
            user_email=user_email,
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
                ctx.total_chunks = job.progress.total_chunks
                ctx.total_embeddings = job.progress.total_embeddings
            log.info(f"Resuming from checkpoint at index {ctx.current_url_index}, previously processed {ctx.processed_count} URLs")

        try:
            job.status = CrawlJobStatus.IN_PROGRESS
            if not job.timing.started_at:
                job.timing.started_at = datetime.now(timezone.utc)
            job_repo.save(job)

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

            if not ctx.discovered_urls:
                await self._discover_urls(ctx)

            await self._process_urls(ctx)

            if ctx.current_url_index >= len(ctx.discovered_urls):
                await self._complete_job(ctx)
            else:
                await self._checkpoint_job(ctx)

            return ctx.job

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

        discovery = UrlDiscovery(discovery_config)

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

            if len(ctx.discovered_urls) >= config.max_pages:
                break

        log.info(f"Discovered {len(ctx.discovered_urls)} URLs")

    async def _process_urls(self, ctx: CrawlContext) -> None:
        """Process discovered URLs."""
        config = ctx.job.config
        rate_limit_s = config.rate_limit_ms / 1000.0

        while ctx.current_url_index < len(ctx.discovered_urls):
            # Check for checkpoint
            if ctx.should_checkpoint():
                log.info("Approaching timeout, saving checkpoint")
                break

            url = ctx.discovered_urls[ctx.current_url_index]

            try:
                await self._process_single_url(ctx, url)
                ctx.successful_count += 1
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

    async def _process_single_url(self, ctx: CrawlContext, url: str) -> None:
        """Process a single URL through the full pipeline."""
        job_id = ctx.job.job_id
        kb_id = ctx.kb.kb_id
        timing = PageTiming()

        ctx.emit_event(page_fetch_start_event(job_id, kb_id, url))
        self._log_step(ctx, CrawlStepType.PAGE_FETCH_START, url=url)

        fetch_start = time.time()
        try:
            extracted = await self.extractor.fetch_and_extract(url)
        except Exception as e:
            self._log_step(ctx, CrawlStepType.PAGE_FETCH_ERROR, url=url, details={"error": str(e)})
            raise
        timing.fetch_duration_ms = int((time.time() - fetch_start) * 1000)

        ctx.emit_event(page_fetch_complete_event(
            job_id, kb_id, url,
            status_code=200,
            content_length=extracted.content_length,
            duration_ms=timing.fetch_duration_ms,
        ))
        self._log_step(ctx, CrawlStepType.PAGE_FETCH_COMPLETE, url=url,
                       duration_ms=timing.fetch_duration_ms)

        # Step 2: Parse content
        parse_start = time.time()
        timing.parse_duration_ms = int((time.time() - parse_start) * 1000)

        ctx.emit_event(page_parse_complete_event(
            job_id, kb_id, url,
            title=extracted.title,
            word_count=extracted.word_count,
            duration_ms=timing.parse_duration_ms,
        ))
        self._log_step(ctx, CrawlStepType.PAGE_PARSE_COMPLETE, url=url,
                       duration_ms=timing.parse_duration_ms,
                       details={"title": extracted.title, "word_count": extracted.word_count})

        # Step 3: Chunk content
        chunk_start = time.time()
        chunking_strategy = get_chunking_strategy(ctx.job.config.chunking_strategy.value)
        chunk_data_list = chunking_strategy.chunk(
            content=extracted.full_text,
            source_url=url,
            page_title=extracted.title,
            sections=extracted.sections,
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
            log.warning(f"No chunks generated for {url}")
            return

        # Step 4: Generate embeddings
        embed_start = time.time()
        texts = [c.content for c in chunk_data_list]
        embedding_results = await self.embeddings.embed_texts_async(texts)
        timing.embed_duration_ms = int((time.time() - embed_start) * 1000)

        ctx.emit_event(page_embed_complete_event(
            job_id, kb_id, url,
            embedding_count=len(embedding_results),
            duration_ms=timing.embed_duration_ms,
        ))
        self._log_step(ctx, CrawlStepType.PAGE_EMBED_COMPLETE, url=url,
                       duration_ms=timing.embed_duration_ms,
                       details={"embedding_count": len(embedding_results)})

        # Step 5: Store in Pinecone and DynamoDB
        ingest_start = time.time()
        await self._store_chunks(ctx, chunk_data_list, embedding_results, url, extracted.title)
        timing.ingest_duration_ms = int((time.time() - ingest_start) * 1000)

        ctx.emit_event(page_ingest_complete_event(
            job_id, kb_id, url,
            vector_count=len(chunk_data_list),
            duration_ms=timing.ingest_duration_ms,
        ))
        self._log_step(ctx, CrawlStepType.PAGE_INGEST_COMPLETE, url=url,
                       duration_ms=timing.ingest_duration_ms,
                       details={"vector_count": len(chunk_data_list)})

        # Calculate total timing
        timing.total_duration_ms = (
            (timing.fetch_duration_ms or 0) +
            (timing.parse_duration_ms or 0) +
            (timing.chunk_duration_ms or 0) +
            (timing.embed_duration_ms or 0) +
            (timing.ingest_duration_ms or 0)
        )

        # Save crawled page record
        page = CrawledPage(
            job_id=job_id,
            created_by=ctx.user_email,
            url=url,
            status=CrawledPageStatus.SUCCESS,
            page_metadata=PageMetadata(
                title=extracted.title,
                description=extracted.description,
                content_length=extracted.content_length,
                word_count=extracted.word_count,
            ),
            chunk_count=len(chunk_data_list),
            timing=timing,
        )
        ctx.page_repo.save(page)

        # Update counters
        ctx.total_chunks += len(chunk_data_list)
        ctx.total_embeddings += len(embedding_results)

    async def _store_chunks(
        self,
        ctx: CrawlContext,
        chunk_data_list: list[ContentChunkData],
        embedding_results: list,
        url: str,
        title: str,
    ) -> None:
        """Store chunks in DynamoDB and vectors in Pinecone."""
        from src.vectorstore.pinecone_client import VectorRecord, VectorMetadata

        # Build mapping from old random UUID to chunk info for parent_chunk_id resolution
        # This allows us to generate deterministic parent_chunk_ids
        old_id_to_info: dict[str, tuple[int, int]] = {}  # old_uuid -> (chunk_index, level)
        for chunk_data in chunk_data_list:
            old_id_to_info[chunk_data.chunk_id] = (chunk_data.chunk_index, chunk_data.level)

        # Create ContentChunk entities and VectorRecords
        chunks = []
        vectors = []

        for chunk_data, emb_result in zip(chunk_data_list, embedding_results):
            # Generate deterministic chunk ID for deduplication
            # Same kb_id + url + chunk_index + level = same ID
            # This allows Pinecone upsert to overwrite instead of duplicate
            chunk_id = generate_chunk_id(
                kb_id=ctx.kb.kb_id,
                source_url=url,
                chunk_index=chunk_data.chunk_index,
                level=chunk_data.level,
            )

            # Generate deterministic parent_chunk_id if parent exists
            parent_chunk_id = None
            if chunk_data.parent_chunk_id and chunk_data.parent_chunk_id in old_id_to_info:
                parent_index, parent_level = old_id_to_info[chunk_data.parent_chunk_id]
                parent_chunk_id = generate_chunk_id(
                    kb_id=ctx.kb.kb_id,
                    source_url=url,
                    chunk_index=parent_index,
                    level=parent_level,
                )

            # Create DynamoDB chunk
            chunk = ContentChunk(
                chunk_id=chunk_id,
                kb_id=ctx.kb.kb_id,
                source_url=url,
                page_title=title,
                chunk_index=chunk_data.chunk_index,
                content=chunk_data.content,
                word_count=chunk_data.word_count,
                parent_chunk_id=parent_chunk_id,
                level=chunk_data.level,
            )
            chunks.append(chunk)

            # Create Pinecone vector
            vector = VectorRecord(
                id=chunk_id,
                values=emb_result.embedding,
                metadata=VectorMetadata(
                    kb_id=ctx.kb.kb_id,
                    chunk_id=chunk_id,
                    source_url=url,
                    page_title=title or "",
                    chunk_index=chunk_data.chunk_index,
                    level=chunk_data.level,
                    word_count=chunk_data.word_count,
                ),
            )
            vectors.append(vector)

        # Batch save to DynamoDB
        ctx.chunk_repo.batch_save(chunks)

        # Upsert to Pinecone
        self.pinecone.upsert(vectors, ctx.kb.kb_id)

    def _update_progress(self, ctx: CrawlContext) -> None:
        """Update job progress in database."""
        progress = ctx.get_progress()
        ctx.job_repo.update_progress(
            ctx.job.job_id,
            ctx.kb.kb_id,
            progress.model_dump(),
        )

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

        job.progress = ctx.get_progress()
        job.checkpoint = None  # Clear checkpoint

        ctx.job_repo.save(job)

        # Update KB stats
        ctx.kb_repo.update_stats(
            ctx.kb.kb_id,
            ctx.user_email,
            total_pages=ctx.successful_count,
            total_chunks=ctx.total_chunks,
            total_vectors=ctx.total_embeddings,
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

        ctx.job_repo.save(job)

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
        self._invoke_continuation(job.job_id, ctx.kb.kb_id, ctx.user_email)

    def _invoke_continuation(self, job_id: str, kb_id: str, user_email: str) -> None:
        """Invoke Lambda asynchronously to continue crawl from checkpoint."""
        function_name = os.environ.get("AWS_LAMBDA_FUNCTION_NAME")
        if not function_name:
            log.warning("Not running in Lambda, skipping self-invocation")
            return

        payload = {
            "crawl_job": {
                "job_id": job_id,
                "kb_id": kb_id,
                "user_email": user_email,
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

        ctx.job_repo.save(job)

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
