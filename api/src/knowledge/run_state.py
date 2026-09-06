"""Crawl-job heartbeat and stale-run lifecycle management."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from src.config import settings
from src.knowledge.models import CrawlJob
from src.knowledge.repository import CrawlJobRepository


class CrawlJobStoppedError(RuntimeError):
    """Raised when a worker discovers that its job is no longer active."""


class CrawlJobStateService:
    """Own crawl-job liveness checks and stale-run transitions."""

    def __init__(self, repository: CrawlJobRepository | None = None):
        self.repository = repository or CrawlJobRepository()

    def heartbeat(self, job: CrawlJob, *, at: datetime | None = None) -> None:
        heartbeat_at = at or _utcnow()
        was_updated = self.repository.update_heartbeat(
            job.job_id,
            job.kb_id,
            heartbeat_at,
            job.progress.model_dump(),
        )
        if not was_updated:
            raise CrawlJobStoppedError(
                f"Crawl job {job.job_id} is no longer in progress"
            )
        job.last_heartbeat_at = heartbeat_at
        job.updated_at = heartbeat_at

    def fail_stale_jobs(self, *, now: datetime | None = None) -> int:
        checked_at = now or _utcnow()
        cutoff = checked_at - timedelta(seconds=settings.crawl_job_stale_timeout_seconds)
        failed_count = 0

        for job in self.repository.find_in_progress():
            if self._liveness_reference(job) >= cutoff:
                continue
            if self.repository.mark_failed_if_heartbeat_unchanged(
                job,
                failed_at=checked_at,
                error_message=(
                    "Crawl job heartbeat expired. The worker may have been interrupted; "
                    "please retry the crawl."
                ),
            ):
                failed_count += 1

        return failed_count

    @staticmethod
    def _liveness_reference(job: CrawlJob) -> datetime:
        reference = job.last_heartbeat_at or job.timing.started_at or job.created_at
        if reference.tzinfo is None:
            return reference.replace(tzinfo=timezone.utc)
        return reference.astimezone(timezone.utc)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)
