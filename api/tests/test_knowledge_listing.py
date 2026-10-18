"""A knowledge base with hundreds of pages and many crawls is listed a page at a time."""

from datetime import datetime, timedelta, timezone

import pytest

from src.knowledge.models import (
    FAILING_RUNS_TO_FLAG,
    CrawlConfig,
    CrawlJob,
    KnowledgeBase,
    KnowledgePage,
    KnowledgePageState,
)
from src.knowledge.repository import CrawlJobRepository, KnowledgeBaseRepository, KnowledgePageRepository
from tests.mock_data import TEST_USER_EMAIL, kb_fields

SITE = "https://example.com"


@pytest.fixture
def kb(dynamodb_table):
    return KnowledgeBaseRepository().save(KnowledgeBase(name="Docs", **kb_fields(TEST_USER_EMAIL)))


def page(kb, path: str, state=KnowledgePageState.LIVE, **fields) -> KnowledgePage:
    chunk_ids = [f"{path}-1"] if state in (KnowledgePageState.LIVE, KnowledgePageState.FAILING) else []
    return KnowledgePageRepository().save(
        KnowledgePage(kb_id=kb.kb_id, url=f"{SITE}/{path}", source=SITE, state=state, chunk_ids=chunk_ids, **fields)
    )


def walk(repository, kb, limit, **filters) -> list[list[str]]:
    """Every page of the list, in order, following the cursor."""
    seen, cursor = [], None
    while True:
        pages, cursor = repository.list_page(kb.kb_id, limit=limit, cursor=cursor, **filters)
        seen.append([p.url.removeprefix(f"{SITE}/") for p in pages])
        if cursor is None:
            return seen


def test_pages_are_listed_a_page_at_a_time_without_skipping_or_repeating_one(kb):
    for number in range(7):
        page(kb, f"p{number}")

    walked = walk(KnowledgePageRepository(), kb, limit=3)

    assert [len(chunk) for chunk in walked] == [3, 3, 1]
    assert [url for chunk in walked for url in chunk] == [f"p{number}" for number in range(7)]


def test_a_list_that_fits_in_one_page_has_no_cursor(kb):
    page(kb, "only")

    pages, cursor = KnowledgePageRepository().list_page(kb.kb_id, limit=5)

    assert len(pages) == 1 and cursor is None


def test_pages_that_need_a_look_come_first_then_the_states_in_turn(kb):
    page(kb, "a-gone", KnowledgePageState.GONE)
    page(kb, "b-dup", KnowledgePageState.DUPLICATE)
    page(kb, "c-live")
    page(kb, "d-failing", KnowledgePageState.FAILING, consecutive_failures=1)
    page(kb, "e-flagged", KnowledgePageState.FAILING, consecutive_failures=FAILING_RUNS_TO_FLAG)

    [everything] = walk(KnowledgePageRepository(), kb, limit=10)

    assert everything == ["e-flagged", "d-failing", "c-live", "b-dup", "a-gone"]


def test_the_list_can_be_narrowed_to_a_state(kb):
    for number in range(4):
        page(kb, f"live{number}")
    page(kb, "gone", KnowledgePageState.GONE)

    walked = walk(KnowledgePageRepository(), kb, limit=3, state=KnowledgePageState.LIVE)

    assert [url for chunk in walked for url in chunk] == [f"live{number}" for number in range(4)]


def test_the_list_can_be_searched_by_address_or_title(kb):
    page(kb, "pricing")
    page(kb, "docs/setup", title="Getting started")
    page(kb, "about")

    by_address = walk(KnowledgePageRepository(), kb, limit=10, search="PRIC")
    by_title = walk(KnowledgePageRepository(), kb, limit=10, search="started")

    assert by_address == [["pricing"]] and by_title == [["docs/setup"]]


def test_pages_are_counted_by_state(kb):
    for number in range(3):
        page(kb, f"live{number}")
    page(kb, "dup", KnowledgePageState.DUPLICATE)
    page(kb, "gone", KnowledgePageState.GONE)

    counts = KnowledgePageRepository().count_by_state(kb.kb_id)

    assert counts == {
        KnowledgePageState.LIVE: 3, KnowledgePageState.FAILING: 0,
        KnowledgePageState.GONE: 1, KnowledgePageState.DUPLICATE: 1,
    }


def test_the_page_routes_return_a_page_and_the_counts(kb, test_client, auth_headers):
    for number in range(5):
        page(kb, f"p{number}")
    url = f"/knowledge-bases/{kb.kb_id}/pages"

    first = test_client.get(url, params={"limit": 2}, headers=auth_headers).json()
    second = test_client.get(url, params={"limit": 2, "cursor": first["next_cursor"]}, headers=auth_headers).json()
    counts = test_client.get(f"{url}/counts", headers=auth_headers).json()

    assert [len(first["items"]), first["has_more"], len(second["items"])] == [2, True, 2]
    assert counts == {"live": 5, "failing": 0, "gone": 0, "duplicate": 0}


def test_a_cursor_that_isnt_ours_is_a_bad_request(kb, test_client, auth_headers):
    response = test_client.get(f"/knowledge-bases/{kb.kb_id}/pages", params={"cursor": "nonsense"}, headers=auth_headers)

    assert response.status_code == 400


def a_job(kb, minutes_ago: int) -> CrawlJob:
    created = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    return CrawlJobRepository().save(CrawlJob(kb_id=kb.kb_id, config=CrawlConfig(source_url=SITE), created_by=kb.owner_id, created_at=created))


def test_crawl_jobs_are_listed_newest_first_a_page_at_a_time(kb, test_client, auth_headers):
    jobs = [a_job(kb, minutes_ago=ago) for ago in (50, 10, 40, 20, 30, 60, 5)]
    newest_first = [job.job_id for job in sorted(jobs, key=lambda job: job.created_at, reverse=True)]
    url = f"/knowledge-bases/{kb.kb_id}/crawl-jobs"

    first = test_client.get(url, headers=auth_headers).json()
    second = test_client.get(url, params={"cursor": first["next_cursor"]}, headers=auth_headers).json()

    assert [job["job_id"] for job in first["items"]] == newest_first[:5], "five by default"
    assert first["has_more"] is True
    assert [job["job_id"] for job in second["items"]] == newest_first[5:]
    assert second["next_cursor"] is None and second["has_more"] is False


def test_a_page_is_shown_with_its_chunks_in_page_order_and_the_pages_that_say_the_same(kb, test_client, auth_headers):
    from src.knowledge.models import ContentChunk
    from src.knowledge.repository import ContentChunkRepository

    chunks = [
        ContentChunk(chunk_id=f"c{n}", kb_id=kb.kb_id, source_url=f"{SITE}/pricing", chunk_index=n,
                     content=f"Plan {n} costs {n} pounds.", level=1, section_heading=f"Plan {n}")
        for n in (3, 1, 2)
    ]
    ContentChunkRepository().batch_save(chunks)
    KnowledgePageRepository().save(KnowledgePage(
        kb_id=kb.kb_id, url=f"{SITE}/pricing", source=SITE, title="Pricing", chunk_ids=["c3", "c1", "c2"]))
    page(kb, "pricing?ref=nav", KnowledgePageState.DUPLICATE, duplicate_of=f"{SITE}/pricing")

    response = test_client.get(f"/knowledge-bases/{kb.kb_id}/pages/detail", params={"url": f"{SITE}/pricing"}, headers=auth_headers)

    body = response.json()
    assert response.status_code == 200, response.text
    assert [chunk["chunk_id"] for chunk in body["chunks"]] == ["c3", "c1", "c2"], "the order the page says them"
    assert body["chunks"][0]["section_heading"] == "Plan 3" and body["chunks"][0]["word_count"] == 5
    assert body["duplicates"] == [f"{SITE}/pricing?ref=nav"] and body["chunk_count"] == 3


def test_a_page_the_knowledge_base_doesnt_have_is_not_found(kb, test_client, auth_headers):
    response = test_client.get(f"/knowledge-bases/{kb.kb_id}/pages/detail", params={"url": f"{SITE}/nope"}, headers=auth_headers)

    assert response.status_code == 404
