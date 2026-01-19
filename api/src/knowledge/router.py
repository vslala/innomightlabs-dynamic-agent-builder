"""
Knowledge Base API router.

Endpoints:
    Knowledge Base CRUD:
        POST   /knowledge-bases                    Create knowledge base
        GET    /knowledge-bases                    List user's knowledge bases
        GET    /knowledge-bases/{kb_id}            Get knowledge base details
        PATCH  /knowledge-bases/{kb_id}            Update knowledge base
        DELETE /knowledge-bases/{kb_id}            Delete knowledge base (soft delete)

    Crawl Jobs:
        GET    /knowledge-bases/{kb_id}/crawl-config-schema   Get form schema for crawl config
        POST   /knowledge-bases/{kb_id}/crawl-jobs            Start new crawl job (auto_start=true by default)
        GET    /knowledge-bases/{kb_id}/crawl-jobs            List crawl jobs
        GET    /knowledge-bases/{kb_id}/crawl-jobs/{job_id}   Get job details
        POST   /knowledge-bases/{kb_id}/crawl-jobs/{job_id}/run        Manually run pending job
        POST   /knowledge-bases/{kb_id}/crawl-jobs/{job_id}/run-stream Run and stream events (SSE)
        GET    /knowledge-bases/{kb_id}/crawl-jobs/{job_id}/stream     Poll for updates (SSE)
        DELETE /knowledge-bases/{kb_id}/crawl-jobs/{job_id}            Cancel crawl job
        GET    /knowledge-bases/{kb_id}/crawl-jobs/{job_id}/steps      Get audit log
        GET    /knowledge-bases/{kb_id}/crawl-jobs/{job_id}/pages      Get crawled pages

    Search:
        POST   /knowledge-bases/{kb_id}/search     Search knowledge base content
        POST   /agents/{agent_id}/knowledge-search Search across agent's linked KBs

    Agent Knowledge Base Links:
        POST   /agents/{agent_id}/knowledge-bases             Link knowledge base to agent
        GET    /agents/{agent_id}/knowledge-bases             List linked knowledge bases
        DELETE /agents/{agent_id}/knowledge-bases/{kb_id}     Unlink knowledge base
"""

from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query, BackgroundTasks
from fastapi.responses import StreamingResponse
from fastapi.security import HTTPBearer
from typing import Annotated, Optional
import logging
import asyncio
import json

import src.form_models as form_models
from src.knowledge.models import (
    KnowledgeBase,
    KnowledgeBaseResponse,
    CreateKnowledgeBaseRequest,
    UpdateKnowledgeBaseRequest,
    CrawlJob,
    CrawlJobResponse,
    CrawlJobStatus,
    CrawlConfig,
    StartCrawlJobRequest,
    CrawlStepResponse,
    CrawledPageResponse,
)
from src.knowledge.repository import (
    KnowledgeBaseRepository,
    CrawlJobRepository,
    CrawlStepRepository,
    CrawledPageRepository,
    AgentKnowledgeBaseRepository,
)
from src.knowledge.schemas import get_crawl_config_form, get_create_knowledge_base_form

log = logging.getLogger(__name__)

# Security scheme for Swagger UI
security = HTTPBearer()

router = APIRouter(
    prefix="/knowledge-bases",
    tags=["knowledge-bases"],
    dependencies=[Depends(security)],
)

# SSE router without HTTPBearer (EventSource doesn't support custom headers)
# Auth is handled via query param token in the middleware
sse_router = APIRouter(
    prefix="/knowledge-bases",
    tags=["knowledge-bases"],
)

# Agent knowledge base linking router (separate prefix)
agent_kb_router = APIRouter(
    prefix="/agents",
    tags=["agent-knowledge-bases"],
    dependencies=[Depends(security)],
)


# =============================================================================
# Dependencies
# =============================================================================


def get_kb_repository() -> KnowledgeBaseRepository:
    return KnowledgeBaseRepository()


def get_crawl_job_repository() -> CrawlJobRepository:
    return CrawlJobRepository()


def get_crawl_step_repository() -> CrawlStepRepository:
    return CrawlStepRepository()


def get_crawled_page_repository() -> CrawledPageRepository:
    return CrawledPageRepository()


def get_agent_kb_repository() -> AgentKnowledgeBaseRepository:
    return AgentKnowledgeBaseRepository()


def get_crawler():
    """Lazy import crawler worker to avoid circular import."""
    from src.crawler import get_crawler_worker
    return get_crawler_worker()


# =============================================================================
# Knowledge Base CRUD
# =============================================================================


@router.get("/create-schema", response_model=form_models.Form, response_model_exclude_none=True)
async def get_create_kb_schema() -> form_models.Form:
    """Get the form schema for creating a knowledge base."""
    return get_create_knowledge_base_form()


@router.post(
    "",
    response_model=KnowledgeBaseResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_knowledge_base(
    request: Request,
    create_request: CreateKnowledgeBaseRequest,
    repo: Annotated[KnowledgeBaseRepository, Depends(get_kb_repository)],
) -> KnowledgeBaseResponse:
    """Create a new knowledge base."""
    user_email: str = request.state.user_email

    kb = KnowledgeBase(
        name=create_request.name,
        description=create_request.description,
        created_by=user_email,
    )

    saved_kb = repo.save(kb)
    log.info(f"Created knowledge base '{saved_kb.name}' (id={saved_kb.kb_id}) for user {user_email}")

    return saved_kb.to_response()


@router.get("", response_model=list[KnowledgeBaseResponse])
async def list_knowledge_bases(
    request: Request,
    repo: Annotated[KnowledgeBaseRepository, Depends(get_kb_repository)],
) -> list[KnowledgeBaseResponse]:
    """List all knowledge bases for the authenticated user."""
    user_email: str = request.state.user_email
    kbs = repo.find_all_by_user(user_email)
    return [kb.to_response() for kb in kbs]


@router.get("/{kb_id}", response_model=KnowledgeBaseResponse)
async def get_knowledge_base(
    request: Request,
    kb_id: str,
    repo: Annotated[KnowledgeBaseRepository, Depends(get_kb_repository)],
) -> KnowledgeBaseResponse:
    """Get a knowledge base by ID."""
    user_email: str = request.state.user_email
    kb = repo.find_by_id(kb_id, user_email)

    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    return kb.to_response()


@router.patch("/{kb_id}", response_model=KnowledgeBaseResponse)
async def update_knowledge_base(
    request: Request,
    kb_id: str,
    update_request: UpdateKnowledgeBaseRequest,
    repo: Annotated[KnowledgeBaseRepository, Depends(get_kb_repository)],
) -> KnowledgeBaseResponse:
    """Update a knowledge base."""
    user_email: str = request.state.user_email
    kb = repo.find_by_id(kb_id, user_email)

    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    if update_request.name is not None:
        kb.name = update_request.name
    if update_request.description is not None:
        kb.description = update_request.description

    saved_kb = repo.save(kb)
    log.info(f"Updated knowledge base '{saved_kb.name}' (id={saved_kb.kb_id})")

    return saved_kb.to_response()


@router.delete("/{kb_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_knowledge_base(
    request: Request,
    kb_id: str,
    repo: Annotated[KnowledgeBaseRepository, Depends(get_kb_repository)],
) -> None:
    """Soft delete a knowledge base."""
    user_email: str = request.state.user_email
    repo.soft_delete(kb_id, user_email)
    log.info(f"Soft deleted knowledge base {kb_id} for user {user_email}")


# =============================================================================
# Crawl Jobs
# =============================================================================


@router.get(
    "/{kb_id}/crawl-config-schema",
    response_model=form_models.Form,
    response_model_exclude_none=True,
)
async def get_crawl_config_schema(kb_id: str) -> form_models.Form:
    """Get the form schema for configuring a crawl job."""
    return get_crawl_config_form(kb_id)


async def _run_crawl_in_background(
    job_id: str,
    kb_id: str,
    user_email: str,
    crawler,  # CrawlerWorker - type annotation omitted to avoid circular import
):
    """Background task to run the crawler."""
    try:
        # Run with a 5 minute timeout for development
        # In Lambda, this would be adjusted based on remaining execution time
        await crawler.run(
            job_id=job_id,
            kb_id=kb_id,
            user_email=user_email,
            timeout_ms=300000,  # 5 minutes
        )
    except Exception as e:
        log.error(f"Background crawl failed for job {job_id}: {e}")


@router.post(
    "/{kb_id}/crawl-jobs",
    response_model=CrawlJobResponse,
    status_code=status.HTTP_201_CREATED,
)
async def start_crawl_job(
    request: Request,
    kb_id: str,
    crawl_request: StartCrawlJobRequest,
    background_tasks: BackgroundTasks,
    kb_repo: Annotated[KnowledgeBaseRepository, Depends(get_kb_repository)],
    job_repo: Annotated[CrawlJobRepository, Depends(get_crawl_job_repository)],
    crawler = Depends(get_crawler),
    auto_start: bool = Query(default=True, description="Automatically start crawling"),
) -> CrawlJobResponse:
    """
    Start a new crawl job for the knowledge base.

    Set auto_start=false to create the job without starting the crawler.
    The job can then be started manually via POST /{kb_id}/crawl-jobs/{job_id}/run
    """
    user_email: str = request.state.user_email

    # Verify KB exists and belongs to user
    kb = kb_repo.find_by_id(kb_id, user_email)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Check if Pinecone is configured (required for crawling)
    from src.config import settings
    if auto_start and not settings.is_pinecone_configured():
        raise HTTPException(
            status_code=503,
            detail="Vector store is not configured. Set PINECONE_API_KEY, PINECONE_HOST, and PINECONE_INDEX to enable crawling."
        )

    # Create crawl config
    config = CrawlConfig(
        source_type=crawl_request.source_type,
        source_url=crawl_request.source_url,
        max_pages=crawl_request.max_pages,
        max_depth=crawl_request.max_depth,
        rate_limit_ms=crawl_request.rate_limit_ms,
        chunking_strategy=crawl_request.chunking_strategy,
    )

    # Create crawl job
    job = CrawlJob(
        kb_id=kb_id,
        config=config,
        created_by=user_email,
    )

    saved_job = job_repo.save(job)
    log.info(f"Created crawl job {saved_job.job_id} for KB {kb_id}")

    # Start crawling in background if auto_start is enabled
    if auto_start:
        background_tasks.add_task(
            _run_crawl_in_background,
            saved_job.job_id,
            kb_id,
            user_email,
            crawler,
        )
        log.info(f"Queued background crawl for job {saved_job.job_id}")

    return saved_job.to_response()


@router.get("/{kb_id}/crawl-jobs", response_model=list[CrawlJobResponse])
async def list_crawl_jobs(
    request: Request,
    kb_id: str,
    kb_repo: Annotated[KnowledgeBaseRepository, Depends(get_kb_repository)],
    job_repo: Annotated[CrawlJobRepository, Depends(get_crawl_job_repository)],
    limit: int = Query(default=5, ge=1, le=50),
) -> list[CrawlJobResponse]:
    """List crawl jobs for a knowledge base (most recent first)."""
    user_email: str = request.state.user_email

    # Verify KB exists and belongs to user
    kb = kb_repo.find_by_id(kb_id, user_email)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    jobs = job_repo.find_all_by_kb(kb_id, limit=limit)
    return [job.to_response() for job in jobs]


@router.get("/{kb_id}/crawl-jobs/{job_id}", response_model=CrawlJobResponse)
async def get_crawl_job(
    request: Request,
    kb_id: str,
    job_id: str,
    kb_repo: Annotated[KnowledgeBaseRepository, Depends(get_kb_repository)],
    job_repo: Annotated[CrawlJobRepository, Depends(get_crawl_job_repository)],
) -> CrawlJobResponse:
    """Get a crawl job by ID."""
    user_email: str = request.state.user_email

    # Verify KB exists and belongs to user
    kb = kb_repo.find_by_id(kb_id, user_email)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    job = job_repo.find_by_id(job_id, kb_id)
    if not job:
        raise HTTPException(status_code=404, detail="Crawl job not found")

    return job.to_response()


@router.post("/{kb_id}/crawl-jobs/{job_id}/run", response_model=CrawlJobResponse)
async def run_crawl_job(
    request: Request,
    kb_id: str,
    job_id: str,
    background_tasks: BackgroundTasks,
    kb_repo: Annotated[KnowledgeBaseRepository, Depends(get_kb_repository)],
    job_repo: Annotated[CrawlJobRepository, Depends(get_crawl_job_repository)],
    crawler = Depends(get_crawler),
) -> CrawlJobResponse:
    """
    Manually run a pending crawl job.

    Use this endpoint to start a job that was created with auto_start=false,
    or to retry a failed job.
    """
    user_email: str = request.state.user_email

    # Verify KB exists and belongs to user
    kb = kb_repo.find_by_id(kb_id, user_email)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    job = job_repo.find_by_id(job_id, kb_id)
    if not job:
        raise HTTPException(status_code=404, detail="Crawl job not found")

    # Check if job can be started
    if job.status == CrawlJobStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=409,
            detail="Crawl job is already in progress"
        )

    if job.status == CrawlJobStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail="Crawl job has already completed. Create a new job to re-crawl."
        )

    if job.status == CrawlJobStatus.CANCELLED:
        raise HTTPException(
            status_code=409,
            detail="Crawl job was cancelled. Create a new job to re-crawl."
        )

    # Check if Pinecone is configured
    from src.config import settings
    if not settings.is_pinecone_configured():
        raise HTTPException(
            status_code=503,
            detail="Vector store is not configured. Set PINECONE_API_KEY, PINECONE_HOST, and PINECONE_INDEX to enable crawling."
        )

    # Start crawling in background
    background_tasks.add_task(
        _run_crawl_in_background,
        job_id,
        kb_id,
        user_email,
        crawler,
    )
    log.info(f"Queued background crawl for job {job_id} (manual trigger)")

    return job.to_response()


@sse_router.get("/{kb_id}/crawl-jobs/{job_id}/stream")
async def stream_crawl_job(
    request: Request,
    kb_id: str,
    job_id: str,
    kb_repo: Annotated[KnowledgeBaseRepository, Depends(get_kb_repository)],
    job_repo: Annotated[CrawlJobRepository, Depends(get_crawl_job_repository)],
    step_repo: Annotated[CrawlStepRepository, Depends(get_crawl_step_repository)],
    cursor: Optional[str] = Query(default=None, description="Cursor for resuming from last seen step"),
):
    """
    SSE stream for real-time crawl job updates.

    Polls CrawlStep table for granular events (fetching pages, parsing, chunking, etc.)
    Supports reconnection via cursor parameter.

    Auth is handled via query param token since EventSource doesn't support headers.
    """
    user_email: str = request.state.user_email

    kb = kb_repo.find_by_id(kb_id, user_email)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    job = job_repo.find_by_id(job_id, kb_id)
    if not job:
        raise HTTPException(status_code=404, detail="Crawl job not found")

    async def event_stream():
        current_cursor = cursor
        last_status = None
        last_progress = None

        yield f"event: connected\ndata: {{\"event_type\": \"connected\", \"job_id\": \"{job_id}\", \"kb_id\": \"{kb_id}\", \"timestamp\": \"{datetime.now(timezone.utc).isoformat()}\"}}\n\n"

        while True:
            if await request.is_disconnected():
                break

            steps, new_cursor = step_repo.find_steps_after_cursor(
                job_id, cursor_sk=current_cursor, limit=50
            )

            for step in steps:
                details = step.details
                if details:
                    details = {k: (int(v) if hasattr(v, '__int__') and not isinstance(v, bool) else v) for k, v in details.items()}
                event_data = {
                    "event_type": step.step_type.value,
                    "step_id": step.step_id,
                    "job_id": job_id,
                    "kb_id": kb_id,
                    "url": step.url,
                    "details": details,
                    "duration_ms": int(step.duration_ms) if step.duration_ms else None,
                    "timestamp": step.timestamp.isoformat(),
                }
                yield f"event: {step.step_type.value}\ndata: {json.dumps(event_data)}\n\n"

            if new_cursor:
                current_cursor = new_cursor

            current_job = job_repo.find_by_id(job_id, kb_id)
            if not current_job:
                break

            current_status = current_job.status.value
            current_progress = current_job.progress.model_dump()

            if current_status != last_status or current_progress != last_progress:
                progress_event = {
                    "event_type": "JOB_PROGRESS",
                    "job_id": job_id,
                    "kb_id": kb_id,
                    "status": current_status,
                    "progress": current_progress,
                }
                yield f"event: JOB_PROGRESS\ndata: {json.dumps(progress_event)}\n\n"
                last_status = current_status
                last_progress = current_progress

            if current_job.status in [
                CrawlJobStatus.COMPLETED,
                CrawlJobStatus.FAILED,
                CrawlJobStatus.CANCELLED,
            ]:
                final_event = {
                    "event_type": f"JOB_{current_status.upper()}",
                    "job_id": job_id,
                    "kb_id": kb_id,
                    "status": current_status,
                    "progress": current_progress,
                    "error_message": current_job.error_message,
                    "cursor": current_cursor,
                }
                yield f"event: JOB_{current_status.upper()}\ndata: {json.dumps(final_event)}\n\n"
                break

            await asyncio.sleep(0.5)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@sse_router.post("/{kb_id}/crawl-jobs/{job_id}/run-stream")
async def run_and_stream_crawl_job(
    request: Request,
    kb_id: str,
    job_id: str,
    kb_repo: Annotated[KnowledgeBaseRepository, Depends(get_kb_repository)],
    job_repo: Annotated[CrawlJobRepository, Depends(get_crawl_job_repository)],
    crawler = Depends(get_crawler),
):
    """
    Run crawl job synchronously while streaming SSE events.

    This endpoint runs the crawler in the request context and streams events
    directly to the client. Useful for development and testing.

    NOTE: This endpoint has a long timeout due to the nature of web crawling.
    For production use with Lambda, prefer the background approach:
    1. POST to start the job (auto_start=true)
    2. GET /stream to poll for updates

    Auth is handled via query param token since EventSource doesn't support headers.
    """
    user_email: str = request.state.user_email

    # Verify KB exists and belongs to user
    kb = kb_repo.find_by_id(kb_id, user_email)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    job = job_repo.find_by_id(job_id, kb_id)
    if not job:
        raise HTTPException(status_code=404, detail="Crawl job not found")

    # Check if job can be started
    if job.status == CrawlJobStatus.IN_PROGRESS:
        raise HTTPException(
            status_code=409,
            detail="Crawl job is already in progress"
        )

    if job.status == CrawlJobStatus.COMPLETED:
        raise HTTPException(
            status_code=409,
            detail="Crawl job has already completed. Create a new job to re-crawl."
        )

    # Check if Pinecone is configured
    from src.config import settings
    if not settings.is_pinecone_configured():
        raise HTTPException(
            status_code=503,
            detail="Vector store is not configured. Set PINECONE_API_KEY, PINECONE_HOST, and PINECONE_INDEX to enable crawling."
        )

    async def event_stream():
        """Run crawler and stream events."""
        try:
            async for event in crawler.run_with_events(
                job_id=job_id,
                kb_id=kb_id,
                user_email=user_email,
                timeout_ms=300000,  # 5 minutes
            ):
                # Check if client disconnected
                if await request.is_disconnected():
                    log.info(f"Client disconnected during crawl job {job_id}")
                    break

                event_data = event.model_dump(mode="json")
                yield f"event: {event.event_type.value}\ndata: {json.dumps(event_data)}\n\n"

        except Exception as e:
            log.error(f"Error streaming crawl events for job {job_id}: {e}")
            error_event = {
                "event_type": "JOB_FAILED",
                "job_id": job_id,
                "kb_id": kb_id,
                "error": str(e),
            }
            yield f"event: JOB_FAILED\ndata: {json.dumps(error_event)}\n\n"

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
        },
    )


@router.delete(
    "/{kb_id}/crawl-jobs/{job_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def cancel_crawl_job(
    request: Request,
    kb_id: str,
    job_id: str,
    kb_repo: Annotated[KnowledgeBaseRepository, Depends(get_kb_repository)],
    job_repo: Annotated[CrawlJobRepository, Depends(get_crawl_job_repository)],
) -> None:
    """Cancel a crawl job."""
    user_email: str = request.state.user_email

    # Verify KB exists and belongs to user
    kb = kb_repo.find_by_id(kb_id, user_email)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    job = job_repo.find_by_id(job_id, kb_id)
    if not job:
        raise HTTPException(status_code=404, detail="Crawl job not found")

    # Only cancel if job is in progress or pending
    if job.status in [CrawlJobStatus.PENDING, CrawlJobStatus.IN_PROGRESS]:
        job_repo.update_status(job_id, kb_id, CrawlJobStatus.CANCELLED.value)
        log.info(f"Cancelled crawl job {job_id}")


@router.get("/{kb_id}/crawl-jobs/{job_id}/steps", response_model=list[CrawlStepResponse])
async def list_crawl_steps(
    request: Request,
    kb_id: str,
    job_id: str,
    kb_repo: Annotated[KnowledgeBaseRepository, Depends(get_kb_repository)],
    job_repo: Annotated[CrawlJobRepository, Depends(get_crawl_job_repository)],
    step_repo: Annotated[CrawlStepRepository, Depends(get_crawl_step_repository)],
    limit: int = Query(default=100, ge=1, le=500),
) -> list[CrawlStepResponse]:
    """List audit log steps for a crawl job."""
    user_email: str = request.state.user_email

    # Verify KB exists and belongs to user
    kb = kb_repo.find_by_id(kb_id, user_email)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    job = job_repo.find_by_id(job_id, kb_id)
    if not job:
        raise HTTPException(status_code=404, detail="Crawl job not found")

    steps, _ = step_repo.find_all_by_job(job_id, limit=limit)
    return [step.to_response() for step in steps]


@router.get("/{kb_id}/crawl-jobs/{job_id}/pages", response_model=list[CrawledPageResponse])
async def list_crawled_pages(
    request: Request,
    kb_id: str,
    job_id: str,
    kb_repo: Annotated[KnowledgeBaseRepository, Depends(get_kb_repository)],
    job_repo: Annotated[CrawlJobRepository, Depends(get_crawl_job_repository)],
    page_repo: Annotated[CrawledPageRepository, Depends(get_crawled_page_repository)],
    limit: int = Query(default=100, ge=1, le=500),
) -> list[CrawledPageResponse]:
    """List crawled pages for a crawl job with analytics."""
    user_email: str = request.state.user_email

    # Verify KB exists and belongs to user
    kb = kb_repo.find_by_id(kb_id, user_email)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    job = job_repo.find_by_id(job_id, kb_id)
    if not job:
        raise HTTPException(status_code=404, detail="Crawl job not found")

    pages, _ = page_repo.find_all_by_job(job_id, limit=limit)
    return [page.to_response() for page in pages]


# =============================================================================
# Search
# =============================================================================


@router.post("/{kb_id}/search")
async def search_knowledge_base(
    request: Request,
    kb_id: str,
    query: str = Query(..., description="Search query"),
    top_k: int = Query(default=5, ge=1, le=20),
    kb_repo: Annotated[KnowledgeBaseRepository, Depends(get_kb_repository)] = None,
) -> dict:
    """
    Search a knowledge base for relevant content.

    Performs semantic search using vector embeddings.
    Requires PINECONE_API_KEY, PINECONE_HOST, and PINECONE_INDEX to be configured.
    """
    from src.config import settings
    from src.knowledge.models import SearchResponse as KBSearchResponse, SearchResult as KBSearchResult

    user_email: str = request.state.user_email

    # Check if Pinecone is configured
    if not settings.is_pinecone_configured():
        raise HTTPException(
            status_code=503,
            detail="Vector search is not configured. Set PINECONE_API_KEY, PINECONE_HOST, and PINECONE_INDEX."
        )

    # Verify KB exists and belongs to user
    kb = kb_repo.find_by_id(kb_id, user_email)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Perform search
    from src.vectorstore import get_search_service
    search_service = get_search_service()
    response = await search_service.search(query, kb_id, top_k=top_k)

    # Convert to response format
    results = [
        KBSearchResult(
            chunk_id=r.chunk_id,
            content=r.content,
            source_url=r.source_url,
            page_title=r.page_title,
            score=r.score,
        )
        for r in response.results
    ]

    return KBSearchResponse(results=results, query=query).model_dump()


@agent_kb_router.post("/{agent_id}/knowledge-search")
async def search_agent_knowledge_bases(
    request: Request,
    agent_id: str,
    query: str = Query(..., description="Search query"),
    top_k: int = Query(default=5, ge=1, le=20),
    kb_repo: Annotated[KnowledgeBaseRepository, Depends(get_kb_repository)] = None,
    agent_kb_repo: Annotated[AgentKnowledgeBaseRepository, Depends(get_agent_kb_repository)] = None,
) -> dict:
    """
    Search across all knowledge bases linked to an agent.

    Performs semantic search and returns results from all linked KBs.
    Requires PINECONE_API_KEY, PINECONE_HOST, and PINECONE_INDEX to be configured.
    """
    from src.config import settings

    user_email: str = request.state.user_email

    # Check if Pinecone is configured
    if not settings.is_pinecone_configured():
        raise HTTPException(
            status_code=503,
            detail="Vector search is not configured. Set PINECONE_API_KEY, PINECONE_HOST, and PINECONE_INDEX."
        )

    # Get linked KB IDs
    links = agent_kb_repo.find_kbs_for_agent(agent_id)
    if not links:
        return {"results": [], "query": query}

    # Get KB IDs that the user has access to
    kb_ids = []
    for link in links:
        kb = kb_repo.find_by_id(link.kb_id, user_email)
        if kb:
            kb_ids.append(link.kb_id)

    if not kb_ids:
        return {"results": [], "query": query}

    # Perform search across all KBs
    from src.vectorstore import get_search_service
    search_service = get_search_service()
    results = await search_service.search_multiple_kbs(query, kb_ids, top_k=top_k)

    # Convert to response format
    response_results = [
        {
            "chunk_id": r.chunk_id,
            "content": r.content,
            "source_url": r.source_url,
            "page_title": r.page_title,
            "score": r.score,
        }
        for r in results
    ]

    return {"results": response_results, "query": query}


# =============================================================================
# Agent Knowledge Base Links
# =============================================================================


@agent_kb_router.post(
    "/{agent_id}/knowledge-bases",
    status_code=status.HTTP_201_CREATED,
)
async def link_knowledge_base(
    request: Request,
    agent_id: str,
    kb_id: str = Query(..., description="Knowledge base ID to link"),
    kb_repo: Annotated[KnowledgeBaseRepository, Depends(get_kb_repository)] = None,
    agent_kb_repo: Annotated[AgentKnowledgeBaseRepository, Depends(get_agent_kb_repository)] = None,
) -> dict:
    """Link a knowledge base to an agent."""
    user_email: str = request.state.user_email

    # Verify KB exists and belongs to user
    kb = kb_repo.find_by_id(kb_id, user_email)
    if not kb:
        raise HTTPException(status_code=404, detail="Knowledge base not found")

    # Check if already linked
    if agent_kb_repo.exists(agent_id, kb_id):
        return {"message": "Knowledge base already linked", "kb_id": kb_id, "agent_id": agent_id}

    # Create link
    link = agent_kb_repo.link(agent_id, kb_id, user_email)
    log.info(f"Linked KB {kb_id} to agent {agent_id}")

    return {
        "message": "Knowledge base linked successfully",
        "kb_id": kb_id,
        "agent_id": agent_id,
        "linked_at": link.linked_at.isoformat(),
    }


@agent_kb_router.get("/{agent_id}/knowledge-bases", response_model=list[KnowledgeBaseResponse])
async def list_agent_knowledge_bases(
    request: Request,
    agent_id: str,
    kb_repo: Annotated[KnowledgeBaseRepository, Depends(get_kb_repository)],
    agent_kb_repo: Annotated[AgentKnowledgeBaseRepository, Depends(get_agent_kb_repository)],
) -> list[KnowledgeBaseResponse]:
    """List all knowledge bases linked to an agent."""
    user_email: str = request.state.user_email

    # Get linked KB IDs
    links = agent_kb_repo.find_kbs_for_agent(agent_id)

    # Fetch full KB details
    kbs = []
    for link in links:
        kb = kb_repo.find_by_id(link.kb_id, user_email)
        if kb:
            kbs.append(kb.to_response())

    return kbs


@agent_kb_router.delete(
    "/{agent_id}/knowledge-bases/{kb_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def unlink_knowledge_base(
    request: Request,
    agent_id: str,
    kb_id: str,
    agent_kb_repo: Annotated[AgentKnowledgeBaseRepository, Depends(get_agent_kb_repository)],
) -> None:
    """Unlink a knowledge base from an agent."""
    agent_kb_repo.unlink(agent_id, kb_id)
    log.info(f"Unlinked KB {kb_id} from agent {agent_id}")
