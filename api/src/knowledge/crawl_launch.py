"""Starting a saved crawl job on whichever backend this deployment runs crawls on.

Shared by the knowledge-base routes and by blueprints, so both start crawls the same way.
"""

import asyncio
import json
import logging
from typing import Any, Optional

from fastapi import BackgroundTasks, HTTPException

from src.config import settings

log = logging.getLogger(__name__)


#: Crawls started outside a request (from a chat turn), held so they aren't garbage-collected mid-run.
_running_crawls: set[asyncio.Task[None]] = set()


def launch_crawl(
    job_id: str,
    kb_id: str,
    user_email: str,
    background_tasks: Optional[BackgroundTasks] = None,
    crawler: Optional[Any] = None,
) -> None:
    """Lambda when ASYNC_JOB_BACKEND=lambda. Otherwise in this process: after the response when called from a
    request, or as a task on the running event loop when called from a chat turn's tool call."""
    if settings.async_job_backend == "lambda":
        invoke_crawl_async(job_id, kb_id, user_email)
        log.info(f"Invoked async Lambda for crawl job {job_id}")
        return

    if crawler is None:
        from src.crawler.worker import get_crawler_worker

        crawler = get_crawler_worker()
    if background_tasks is not None:
        background_tasks.add_task(run_crawl_in_background, job_id, kb_id, user_email, crawler)
    else:
        task = asyncio.get_running_loop().create_task(run_crawl_in_background(job_id, kb_id, user_email, crawler))
        _running_crawls.add(task)
        task.add_done_callback(_running_crawls.discard)
    log.info(f"Queued background crawl for job {job_id}")


def invoke_crawl_async(job_id: str, kb_id: str, user_email: str):
    """Invoke the crawl job asynchronously via the configured Lambda worker."""
    import boto3

    function_name = settings.async_job_lambda_name
    if not function_name:
        raise HTTPException(
            status_code=503,
            detail="ASYNC_JOB_LAMBDA_NAME is required when ASYNC_JOB_BACKEND=lambda",
        )
    lambda_client = boto3.client("lambda", region_name=settings.aws_region)

    payload = json.dumps({
        "crawl_job": {
            "job_id": job_id,
            "kb_id": kb_id,
            "user_email": user_email,
        }
    })

    try:
        response = lambda_client.invoke(
            FunctionName=function_name,
            InvocationType="Event",  # Async invocation
            Payload=payload,
        )
        log.info(f"Invoked Lambda async for crawl job {job_id}, status: {response['StatusCode']}")
        return response
    except Exception as e:
        log.error(f"Failed to invoke Lambda async for crawl job {job_id}: {e}")
        raise


async def run_crawl_in_background(
    job_id: str,
    kb_id: str,
    user_email: str,
    crawler,  # CrawlerWorker - type annotation omitted to avoid circular import
):
    """Background task to run the crawler in this process (local and Railway)."""
    from src.knowledge.models import CrawlJobStatus

    try:
        # The worker checkpoints every 5 minutes for Lambda's time limit. Nothing re-invokes a process,
        # so resume each checkpoint here until the job completes, fails or is cancelled.
        while True:
            job = await crawler.run(
                job_id=job_id,
                kb_id=kb_id,
                user_email=user_email,
                timeout_ms=300000,  # 5 minutes
            )
            if job.status != CrawlJobStatus.IN_PROGRESS or job.checkpoint is None:
                break
            log.info(f"Resuming crawl job {job_id} in process from index {job.checkpoint.current_url_index}")
    except Exception as e:
        log.error(f"Background crawl failed for job {job_id}: {e}")
