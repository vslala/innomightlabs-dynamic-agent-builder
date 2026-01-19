"""
Crawl event types and models for SSE streaming.

These events are emitted during the crawl process to provide
real-time progress updates to the frontend.
"""

from pydantic import BaseModel, Field
from datetime import datetime, timezone
from typing import Any, Optional
from enum import Enum


class CrawlEventType(str, Enum):
    """Types of events emitted during crawling."""

    # Job lifecycle
    JOB_STARTED = "JOB_STARTED"
    JOB_PROGRESS = "JOB_PROGRESS"
    JOB_CHECKPOINT = "JOB_CHECKPOINT"
    JOB_COMPLETED = "JOB_COMPLETED"
    JOB_FAILED = "JOB_FAILED"

    # URL discovery
    URL_DISCOVERED = "URL_DISCOVERED"
    URL_SKIPPED = "URL_SKIPPED"

    # Page processing
    PAGE_FETCH_START = "PAGE_FETCH_START"
    PAGE_FETCH_COMPLETE = "PAGE_FETCH_COMPLETE"
    PAGE_PARSE_COMPLETE = "PAGE_PARSE_COMPLETE"
    PAGE_CHUNK_COMPLETE = "PAGE_CHUNK_COMPLETE"
    PAGE_EMBED_COMPLETE = "PAGE_EMBED_COMPLETE"
    PAGE_INGEST_COMPLETE = "PAGE_INGEST_COMPLETE"
    PAGE_ERROR = "PAGE_ERROR"


class CrawlEvent(BaseModel):
    """A crawl event for SSE streaming."""

    event_type: CrawlEventType
    job_id: str
    kb_id: str
    timestamp: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    data: dict[str, Any] = Field(default_factory=dict)

    def to_sse(self) -> str:
        """Format as Server-Sent Event."""
        import json

        event_data = {
            "event_type": self.event_type.value,
            "job_id": self.job_id,
            "kb_id": self.kb_id,
            "timestamp": self.timestamp.isoformat(),
            "data": self.data,
        }
        return f"event: {self.event_type.value}\ndata: {json.dumps(event_data)}\n\n"


# =============================================================================
# Event Factory Functions
# =============================================================================


def job_started_event(job_id: str, kb_id: str, source_url: str, max_pages: int) -> CrawlEvent:
    """Create a job started event."""
    return CrawlEvent(
        event_type=CrawlEventType.JOB_STARTED,
        job_id=job_id,
        kb_id=kb_id,
        data={
            "source_url": source_url,
            "max_pages": max_pages,
            "message": "Crawl job started",
        },
    )


def job_progress_event(
    job_id: str,
    kb_id: str,
    discovered: int,
    processed: int,
    successful: int,
    failed: int,
    chunks: int,
) -> CrawlEvent:
    """Create a job progress event."""
    return CrawlEvent(
        event_type=CrawlEventType.JOB_PROGRESS,
        job_id=job_id,
        kb_id=kb_id,
        data={
            "discovered_urls": discovered,
            "processed_urls": processed,
            "successful_urls": successful,
            "failed_urls": failed,
            "total_chunks": chunks,
        },
    )


def job_checkpoint_event(job_id: str, kb_id: str, current_index: int, pending_count: int) -> CrawlEvent:
    """Create a checkpoint event (Lambda continuation)."""
    return CrawlEvent(
        event_type=CrawlEventType.JOB_CHECKPOINT,
        job_id=job_id,
        kb_id=kb_id,
        data={
            "current_url_index": current_index,
            "pending_urls_count": pending_count,
            "message": "Saving checkpoint for Lambda continuation",
        },
    )


def job_completed_event(
    job_id: str,
    kb_id: str,
    total_pages: int,
    total_chunks: int,
    duration_ms: int,
) -> CrawlEvent:
    """Create a job completed event."""
    return CrawlEvent(
        event_type=CrawlEventType.JOB_COMPLETED,
        job_id=job_id,
        kb_id=kb_id,
        data={
            "total_pages": total_pages,
            "total_chunks": total_chunks,
            "duration_ms": duration_ms,
            "message": "Crawl job completed successfully",
        },
    )


def job_failed_event(job_id: str, kb_id: str, error: str) -> CrawlEvent:
    """Create a job failed event."""
    return CrawlEvent(
        event_type=CrawlEventType.JOB_FAILED,
        job_id=job_id,
        kb_id=kb_id,
        data={
            "error": error,
            "message": "Crawl job failed",
        },
    )


def url_discovered_event(job_id: str, kb_id: str, url: str, total_discovered: int) -> CrawlEvent:
    """Create a URL discovered event."""
    return CrawlEvent(
        event_type=CrawlEventType.URL_DISCOVERED,
        job_id=job_id,
        kb_id=kb_id,
        data={
            "url": url,
            "total_discovered": total_discovered,
        },
    )


def url_skipped_event(job_id: str, kb_id: str, url: str, reason: str) -> CrawlEvent:
    """Create a URL skipped event."""
    return CrawlEvent(
        event_type=CrawlEventType.URL_SKIPPED,
        job_id=job_id,
        kb_id=kb_id,
        data={
            "url": url,
            "reason": reason,
        },
    )


def page_fetch_start_event(job_id: str, kb_id: str, url: str) -> CrawlEvent:
    """Create a page fetch start event."""
    return CrawlEvent(
        event_type=CrawlEventType.PAGE_FETCH_START,
        job_id=job_id,
        kb_id=kb_id,
        data={
            "url": url,
            "message": "Fetching page",
        },
    )


def page_fetch_complete_event(
    job_id: str, kb_id: str, url: str, status_code: int, content_length: int, duration_ms: int
) -> CrawlEvent:
    """Create a page fetch complete event."""
    return CrawlEvent(
        event_type=CrawlEventType.PAGE_FETCH_COMPLETE,
        job_id=job_id,
        kb_id=kb_id,
        data={
            "url": url,
            "status_code": status_code,
            "content_length": content_length,
            "duration_ms": duration_ms,
        },
    )


def page_parse_complete_event(
    job_id: str, kb_id: str, url: str, title: str, word_count: int, duration_ms: int
) -> CrawlEvent:
    """Create a page parse complete event."""
    return CrawlEvent(
        event_type=CrawlEventType.PAGE_PARSE_COMPLETE,
        job_id=job_id,
        kb_id=kb_id,
        data={
            "url": url,
            "title": title,
            "word_count": word_count,
            "duration_ms": duration_ms,
        },
    )


def page_chunk_complete_event(
    job_id: str, kb_id: str, url: str, chunk_count: int, duration_ms: int
) -> CrawlEvent:
    """Create a page chunk complete event."""
    return CrawlEvent(
        event_type=CrawlEventType.PAGE_CHUNK_COMPLETE,
        job_id=job_id,
        kb_id=kb_id,
        data={
            "url": url,
            "chunk_count": chunk_count,
            "duration_ms": duration_ms,
        },
    )


def page_embed_complete_event(
    job_id: str, kb_id: str, url: str, embedding_count: int, duration_ms: int
) -> CrawlEvent:
    """Create a page embed complete event."""
    return CrawlEvent(
        event_type=CrawlEventType.PAGE_EMBED_COMPLETE,
        job_id=job_id,
        kb_id=kb_id,
        data={
            "url": url,
            "embedding_count": embedding_count,
            "duration_ms": duration_ms,
        },
    )


def page_ingest_complete_event(
    job_id: str, kb_id: str, url: str, vector_count: int, duration_ms: int
) -> CrawlEvent:
    """Create a page ingest complete event."""
    return CrawlEvent(
        event_type=CrawlEventType.PAGE_INGEST_COMPLETE,
        job_id=job_id,
        kb_id=kb_id,
        data={
            "url": url,
            "vector_count": vector_count,
            "duration_ms": duration_ms,
        },
    )


def page_error_event(job_id: str, kb_id: str, url: str, error: str, step: Optional[str] = None) -> CrawlEvent:
    """Create a page error event."""
    return CrawlEvent(
        event_type=CrawlEventType.PAGE_ERROR,
        job_id=job_id,
        kb_id=kb_id,
        data={
            "url": url,
            "error": error,
            "step": step,
        },
    )
