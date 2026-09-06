from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

import pytest

from src.config import settings
from src.knowledge.models import (
    CrawlConfig,
    CrawlJob,
    CrawlJobStatus,
    CrawlProgress,
    CrawlSourceType,
)
from src.knowledge.repository import CrawlJobRepository
from src.knowledge.run_state import CrawlJobStateService, CrawlJobStoppedError
from src.crawler.worker import CrawlerWorker
from tests.mock_data import TEST_USER_EMAIL


def _crawl_job(
    *,
    status: CrawlJobStatus = CrawlJobStatus.IN_PROGRESS,
    started_at: datetime | None = None,
    heartbeat_at: datetime | None = None,
) -> CrawlJob:
    job = CrawlJob(
        kb_id="kb-1",
        status=status,
        config=CrawlConfig(
            source_type=CrawlSourceType.URL,
            source_url="https://example.com",
        ),
        created_by=TEST_USER_EMAIL,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        last_heartbeat_at=heartbeat_at,
    )
    job.timing.started_at = started_at
    return job


def test_heartbeat_persists_liveness_and_progress(dynamodb_table):
    repository = CrawlJobRepository()
    job = _crawl_job()
    job.progress = CrawlProgress(discovered_urls=12, processed_urls=4)
    repository.save(job)
    heartbeat_at = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)

    CrawlJobStateService(repository).heartbeat(job, at=heartbeat_at)

    saved = repository.find_by_id(job.job_id, job.kb_id)
    assert saved is not None
    assert saved.last_heartbeat_at == heartbeat_at
    assert saved.updated_at == heartbeat_at
    assert saved.progress.discovered_urls == 12
    assert saved.progress.processed_urls == 4


def test_heartbeat_stops_worker_after_cancellation(dynamodb_table):
    repository = CrawlJobRepository()
    job = _crawl_job()
    repository.save(job)
    repository.cancel_if_active(job.job_id, job.kb_id)

    with pytest.raises(CrawlJobStoppedError, match="no longer in progress"):
        CrawlJobStateService(repository).heartbeat(job)


def test_worker_save_does_not_overwrite_cancellation(dynamodb_table):
    repository = CrawlJobRepository()
    job = _crawl_job()
    repository.save(job)
    repository.cancel_if_active(job.job_id, job.kb_id)
    job.status = CrawlJobStatus.COMPLETED

    assert repository.save_if_in_progress(job) is False
    saved = repository.find_by_id(job.job_id, job.kb_id)
    assert saved is not None
    assert saved.status == CrawlJobStatus.CANCELLED


def test_stale_reaper_fails_only_expired_in_progress_jobs(dynamodb_table, monkeypatch):
    repository = CrawlJobRepository()
    now = datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc)
    stale = _crawl_job(heartbeat_at=now - timedelta(minutes=16))
    fresh = _crawl_job(heartbeat_at=now - timedelta(minutes=14))
    pending = _crawl_job(
        status=CrawlJobStatus.PENDING,
        started_at=now - timedelta(hours=1),
    )
    for job in (stale, fresh, pending):
        repository.save(job)
    monkeypatch.setattr(settings, "crawl_job_stale_timeout_seconds", 15 * 60)

    failed_count = CrawlJobStateService(repository).fail_stale_jobs(now=now)

    assert failed_count == 1
    saved_stale = repository.find_by_id(stale.job_id, stale.kb_id)
    saved_fresh = repository.find_by_id(fresh.job_id, fresh.kb_id)
    saved_pending = repository.find_by_id(pending.job_id, pending.kb_id)
    assert saved_stale is not None
    assert saved_stale.status == CrawlJobStatus.FAILED
    assert saved_stale.timing.completed_at == now
    assert saved_stale.error_message is not None
    assert saved_fresh is not None
    assert saved_fresh.status == CrawlJobStatus.IN_PROGRESS
    assert saved_pending is not None
    assert saved_pending.status == CrawlJobStatus.PENDING


def test_stale_reaper_handles_legacy_job_without_heartbeat(dynamodb_table, monkeypatch):
    repository = CrawlJobRepository()
    now = datetime(2026, 1, 1, 12, 30, tzinfo=timezone.utc)
    legacy = _crawl_job(started_at=now - timedelta(minutes=16))
    repository.save(legacy)
    monkeypatch.setattr(settings, "crawl_job_stale_timeout_seconds", 15 * 60)

    failed_count = CrawlJobStateService(repository).fail_stale_jobs(now=now)

    assert failed_count == 1
    saved = repository.find_by_id(legacy.job_id, legacy.kb_id)
    assert saved is not None
    assert saved.status == CrawlJobStatus.FAILED


def test_stale_transition_loses_race_to_new_heartbeat(dynamodb_table):
    repository = CrawlJobRepository()
    observed = datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc)
    job = _crawl_job(heartbeat_at=observed)
    repository.save(job)
    stale_snapshot = repository.find_by_id(job.job_id, job.kb_id)
    assert stale_snapshot is not None

    repository.update_heartbeat(
        job.job_id,
        job.kb_id,
        observed + timedelta(minutes=1),
        job.progress.model_dump(),
    )

    was_failed = repository.mark_failed_if_heartbeat_unchanged(
        stale_snapshot,
        failed_at=observed + timedelta(minutes=16),
        error_message="stale",
    )
    assert was_failed is False


@pytest.mark.asyncio
async def test_url_discovery_offers_heartbeat_on_each_url(monkeypatch):
    discovered_urls = ["https://example.com", "https://example.com/about"]

    class FakeDiscovery:
        def __init__(self, _config):
            pass

        async def discover_from_url(self, _source_url):
            from src.crawler.discovery import DiscoveredUrl

            for url in discovered_urls:
                yield DiscoveredUrl(url=url, source="crawl")

    job = _crawl_job()
    context = Mock()
    context.job = job
    context.kb.kb_id = job.kb_id
    context.discovered_urls = []
    context.emit_event = Mock()
    context.heartbeat = Mock()
    context.step_repo.save = Mock()
    monkeypatch.setattr("src.crawler.worker.UrlDiscovery", FakeDiscovery)

    await CrawlerWorker()._discover_urls(context)

    assert context.discovered_urls == discovered_urls
    assert context.heartbeat.call_count == len(discovered_urls)


def test_page_progress_forces_heartbeat():
    context = Mock()

    CrawlerWorker()._update_progress(context)

    context.heartbeat.assert_called_once_with(force=True)
