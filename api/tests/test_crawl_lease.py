"""A knowledge base runs one crawl at a time: the job holding its crawl lease."""

from datetime import datetime, timedelta, timezone

import pytest

from src.config import settings
from src.knowledge.crawl_launch import CrawlAlreadyRunning, create_crawl_job
from src.knowledge.models import CrawlConfig, CrawlJob, CrawlJobStatus, CrawlSourceType, KnowledgeBase
from src.knowledge.repository import CrawlJobRepository, CrawlLeaseRepository, KnowledgeBaseRepository
from src.knowledge.run_state import CrawlJobStateService, CrawlJobStoppedError
from src.crawler.worker import CrawlerWorker
from tests.mock_data import TEST_USER_EMAIL, kb_fields, user_id_for

CONFIG = CrawlConfig(source_type=CrawlSourceType.URL, source_url="https://docs.acme.example")
OWNER_ID = user_id_for(TEST_USER_EMAIL)


@pytest.fixture
def kb(dynamodb_table) -> KnowledgeBase:
    return KnowledgeBaseRepository().save(KnowledgeBase(name="Docs", **kb_fields(TEST_USER_EMAIL)))


def test_a_second_crawl_is_refused_while_the_first_holds_the_knowledge_base(kb):
    first = create_crawl_job(kb.kb_id, CONFIG, OWNER_ID)

    with pytest.raises(CrawlAlreadyRunning) as refused:
        create_crawl_job(kb.kb_id, CONFIG, OWNER_ID)

    assert refused.value.job_id == first.job_id
    assert [job.job_id for job in CrawlJobRepository().find_all_by_kb(kb.kb_id)] == [first.job_id]


def test_a_crawl_that_ended_lets_the_next_one_start(kb):
    first = create_crawl_job(kb.kb_id, CONFIG, OWNER_ID)

    CrawlJobStateService().release(first)

    assert create_crawl_job(kb.kb_id, CONFIG, OWNER_ID).job_id != first.job_id


def test_a_lease_whose_worker_died_lapses_after_the_stale_timeout(kb):
    stale = CrawlJob(kb_id=kb.kb_id, config=CONFIG, created_by=OWNER_ID)
    long_ago = datetime.now(timezone.utc) - timedelta(seconds=settings.crawl_job_stale_timeout_seconds + 60)
    assert CrawlJobStateService().hold(stale, at=long_ago)

    assert create_crawl_job(kb.kb_id, CONFIG, OWNER_ID)


def test_releasing_never_frees_a_lease_another_job_holds(kb):
    holder = create_crawl_job(kb.kb_id, CONFIG, OWNER_ID)
    other = CrawlJob(kb_id=kb.kb_id, config=CONFIG, created_by=OWNER_ID)

    CrawlJobStateService().release(other)

    lease = CrawlLeaseRepository().find(kb.kb_id)
    assert lease is not None and lease.job_id == holder.job_id


def test_a_worker_that_lost_the_lease_stops_at_its_next_heartbeat(kb):
    running = CrawlJob(kb_id=kb.kb_id, config=CONFIG, created_by=OWNER_ID, status=CrawlJobStatus.IN_PROGRESS)
    CrawlJobRepository().save(running)
    long_ago = datetime.now(timezone.utc) - timedelta(seconds=settings.crawl_job_stale_timeout_seconds + 60)
    assert CrawlJobStateService().hold(running, at=long_ago)
    create_crawl_job(kb.kb_id, CONFIG, OWNER_ID)  # took the lapsed lease

    with pytest.raises(CrawlJobStoppedError, match="Another crawl"):
        CrawlJobStateService().heartbeat(running)


async def test_the_worker_does_not_start_a_job_another_crawl_holds_the_knowledge_base_for(kb):
    create_crawl_job(kb.kb_id, CONFIG, OWNER_ID)
    waiting = CrawlJobRepository().save(CrawlJob(kb_id=kb.kb_id, config=CONFIG, created_by=OWNER_ID))

    job = await CrawlerWorker().run(waiting.job_id, kb.kb_id, kb.account_id)

    assert job.status == CrawlJobStatus.PENDING, "it wasn't touched"


def test_the_newest_job_is_found_however_many_there_are(kb):
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    jobs = [
        CrawlJobRepository().save(CrawlJob(kb_id=kb.kb_id, config=CONFIG, created_by=OWNER_ID, created_at=start + timedelta(days=day)))
        for day in range(60)
    ]

    [newest] = CrawlJobRepository().find_all_by_kb(kb.kb_id, limit=1)

    assert newest.job_id == jobs[-1].job_id


def test_the_route_answers_409_while_a_crawl_runs(test_client, auth_headers, kb):
    create_crawl_job(kb.kb_id, CONFIG, OWNER_ID)

    response = test_client.post(
        f"/knowledge-bases/{kb.kb_id}/crawl-jobs?auto_start=false",
        json={"source_url": "https://docs.acme.example", "source_type": "url"},
        headers=auth_headers,
    )

    assert response.status_code == 409, response.text
