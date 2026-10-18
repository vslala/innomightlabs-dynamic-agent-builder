"""A crawl keeps the knowledge base matching the site: pages the site removed leave, nothing live is lost.

These run whole crawls (`crawl.crawl()`), discovery to completion, against a fake site.
"""

import pytest

from src.knowledge.models import (
    FAILING_RUNS_TO_FLAG,
    UPLOAD_SOURCE,
    ContentChunk,
    CrawlJobStatus,
    KnowledgePage,
    KnowledgePageState,
)
from src.knowledge.repository import (
    ContentChunkRepository,
    KnowledgeBaseRepository,
    KnowledgePageRepository,
    PageWrittenElsewhere,
)
from tests.crawler.fakes import SITE, a_crawl, paragraphs

PRICING, FAQ, TEAM = f"{SITE}/pricing", f"{SITE}/faq", f"{SITE}/team"


@pytest.fixture
async def crawl(dynamodb_table, monkeypatch):
    """A site of three pages, crawled once."""
    crawl = a_crawl(monkeypatch)
    for url in (PRICING, FAQ, TEAM):
        crawl.site.publish(url, paragraphs(3, topic=url.rsplit("/", 1)[-1]))
    job = await crawl.crawl()
    assert job.status == CrawlJobStatus.COMPLETED
    assert {url for url, page in crawl.pages().items() if page.chunk_ids} == {PRICING, FAQ, TEAM}
    return crawl


def searchable(crawl) -> set[str]:
    """The pages search can return text from: those with chunks in DynamoDB."""
    return {chunk.source_url for chunk in crawl.chunks()}


async def test_a_page_the_site_took_down_leaves_on_the_next_crawl(crawl):
    crawl.site.linked.remove(TEAM)
    crawl.site.pages[TEAM] = 404

    job = await crawl.crawl()

    assert searchable(crawl) == {PRICING, FAQ}
    assert crawl.pages()[TEAM].state == KnowledgePageState.GONE and crawl.pages()[TEAM].reason == "HTTP 404"
    assert job.progress.removed_urls == 1
    assert set(crawl.index.vectors) == {chunk.chunk_id for chunk in crawl.chunks()}, "its vectors went too"


async def test_a_page_no_longer_linked_but_still_there_is_kept(crawl):
    crawl.site.linked.remove(TEAM)

    await crawl.crawl()

    assert searchable(crawl) == {PRICING, FAQ, TEAM}
    assert TEAM in crawl.site.fetched[-1:], "it was read to check, not assumed gone"


async def test_pages_past_the_crawls_page_limit_are_kept(crawl):
    await crawl.crawl(max_pages=1)

    assert searchable(crawl) == {PRICING, FAQ, TEAM}


async def test_a_crawl_that_finds_nothing_removes_nothing(crawl):
    crawl.site.linked.clear()  # a sitemap that failed to load

    job = await crawl.crawl()

    assert job.status == CrawlJobStatus.COMPLETED
    assert searchable(crawl) == {PRICING, FAQ, TEAM}


async def test_a_page_robots_txt_now_disallows_is_removed(crawl):
    crawl.site.disallowed.add(FAQ)

    await crawl.crawl()

    assert searchable(crawl) == {PRICING, TEAM}
    assert crawl.pages()[FAQ].reason == "robots.txt disallows it"


async def test_a_page_failing_for_runs_on_end_keeps_its_chunks_and_is_flagged(crawl):
    crawl.site.pages[FAQ] = 503

    for _ in range(FAILING_RUNS_TO_FLAG):
        await crawl.crawl()

    faq = crawl.pages()[FAQ]
    assert faq.state == KnowledgePageState.FAILING and faq.needs_attention
    assert FAQ in searchable(crawl), "an outage doesn't empty the agent"


async def test_a_crawl_never_touches_another_sources_pages(crawl):
    blog = "https://example.com/blog/launch"
    crawl.site.pages[blog] = paragraphs(2, topic="launch")
    await crawl.read(blog, by="https://example.com/blog")
    crawl.site.pages[blog] = 404
    fetched_before = len(crawl.site.fetched)

    await crawl.crawl()

    assert blog in searchable(crawl) and blog not in crawl.site.fetched[fetched_before:]


async def test_uploaded_files_are_never_verified_by_a_crawl(crawl):
    upload = f"file://{crawl.kb.kb_id}/handbook.md"
    KnowledgePageRepository().save(KnowledgePage(kb_id=crawl.kb.kb_id, url=upload, source=UPLOAD_SOURCE, chunk_ids=["c1"]))

    await crawl.crawl()

    assert crawl.pages()[upload].state == KnowledgePageState.LIVE and upload not in crawl.site.fetched


async def test_the_knowledge_base_counts_what_it_holds_not_what_the_run_read(crawl):
    crawl.site.linked.remove(TEAM)
    crawl.site.pages[TEAM] = 404

    await crawl.crawl()

    kb = KnowledgeBaseRepository().find_in_account(crawl.kb.account_id, crawl.kb.kb_id)
    assert (kb.total_pages, kb.total_chunks) == (2, len(crawl.chunks()))


async def test_a_vector_delete_that_failed_is_retried_on_the_pages_next_write(crawl):
    crawl.site.pages[FAQ] = paragraphs(10, topic="faq")
    await crawl.read(FAQ)
    crawl.site.pages[FAQ] = paragraphs(1, topic="faq")
    crawl.index.failing_deletes = 1
    await crawl.read(FAQ)
    orphans = crawl.pages()[FAQ].orphan_vector_ids
    assert orphans and set(orphans) <= set(crawl.index.vectors)

    crawl.site.pages[FAQ] = paragraphs(1, topic="faq", edit=0)
    await crawl.read(FAQ)

    assert crawl.pages()[FAQ].orphan_vector_ids == []
    assert not set(orphans) & set(crawl.index.vectors)


async def test_a_write_that_stopped_halfway_is_finished_by_the_next_read(crawl, monkeypatch):
    crawl.site.pages[PRICING] = paragraphs(5, topic="pricing")
    real_save = ContentChunkRepository.batch_save

    def crash(self, chunks):
        raise RuntimeError("the worker died")

    monkeypatch.setattr(ContentChunkRepository, "batch_save", crash)
    stopped = await crawl.read(PRICING)
    assert stopped.error is not None and crawl.pages()[PRICING].pending_ids, "what it was writing is on the page"
    monkeypatch.setattr(ContentChunkRepository, "batch_save", real_save)

    await crawl.read(PRICING)

    page = crawl.pages()[PRICING]
    assert page.pending_ids == [] and len(page.chunk_ids) == len(crawl.chunks(PRICING))
    assert {chunk.chunk_id for chunk in crawl.chunks()} == set(crawl.index.vectors), "no vector without its chunk"


def dies_right_after_deleting(monkeypatch) -> None:
    """The next chunk delete happens, then the worker dies before it records anything else."""
    real_delete = ContentChunkRepository.delete_by_ids

    def delete_then_die(self, kb_id, chunk_ids):
        real_delete(self, kb_id, chunk_ids)
        monkeypatch.setattr(ContentChunkRepository, "delete_by_ids", real_delete)
        raise RuntimeError("the worker died")

    monkeypatch.setattr(ContentChunkRepository, "delete_by_ids", delete_then_die)


def consistent(crawl, url: str) -> bool:
    page = crawl.pages()[url]
    return (
        page.pending_ids == []
        and set(page.chunk_ids) == {chunk.chunk_id for chunk in crawl.chunks(url)}
        and {chunk.chunk_id for chunk in crawl.chunks()} == set(crawl.index.vectors)
    )


async def test_a_write_that_died_after_deleting_loses_nothing_when_the_page_changes_back(crawl, monkeypatch):
    before = paragraphs(10, topic="faq")
    crawl.site.pages[FAQ] = before
    await crawl.read(FAQ)
    had = len(crawl.chunks(FAQ))
    crawl.site.pages[FAQ] = paragraphs(1, topic="faq")
    dies_right_after_deleting(monkeypatch)
    assert (await crawl.read(FAQ)).error is not None
    assert len(crawl.chunks(FAQ)) < had, "it died after deleting what the shorter page lost"

    crawl.site.pages[FAQ] = before
    await crawl.read(FAQ)

    assert len(crawl.chunks(FAQ)) == had, "the chunks it deleted were written back"
    assert consistent(crawl, FAQ)


async def test_a_removal_that_died_after_deleting_is_written_back_if_the_page_returns(crawl, monkeypatch):
    text = crawl.site.pages[TEAM]
    crawl.site.pages[TEAM] = 404
    dies_right_after_deleting(monkeypatch)
    assert (await crawl.read(TEAM)).error is not None
    assert TEAM not in searchable(crawl)

    crawl.site.pages[TEAM] = text
    await crawl.read(TEAM)

    assert TEAM in searchable(crawl) and consistent(crawl, TEAM)


async def test_a_removal_that_died_after_deleting_is_finished_when_the_page_is_still_gone(crawl, monkeypatch):
    crawl.site.pages[TEAM] = 404
    dies_right_after_deleting(monkeypatch)
    await crawl.read(TEAM)

    await crawl.read(TEAM)

    page = crawl.pages()[TEAM]
    assert page.state == KnowledgePageState.GONE and page.pending_ids == []
    assert {chunk.chunk_id for chunk in crawl.chunks()} == set(crawl.index.vectors), "its vectors went too"


async def test_chunks_from_before_pages_were_kept_are_adopted_and_cleaned_like_any_page(dynamodb_table, monkeypatch):
    crawl = a_crawl(monkeypatch)
    old_page, upload = f"{SITE}/old-offer", f"file://{crawl.kb.kb_id}/notes.md"
    ContentChunkRepository().batch_save([
        ContentChunk(chunk_id=f"legacy-{n}", kb_id=crawl.kb.kb_id, source_url=url,
                     chunk_index=0, content=f"What {url} said.")
        for n, url in enumerate((old_page, upload))
    ])
    crawl.site.publish(PRICING, paragraphs(2))

    await crawl.crawl()

    assert searchable(crawl) == {PRICING, upload}, "the offer is gone from the site; the upload isn't the crawl's"
    assert crawl.pages()[upload].source == UPLOAD_SOURCE


def test_a_page_saved_by_another_writer_since_it_was_read_is_not_overwritten(dynamodb_table):
    repository = KnowledgePageRepository()
    read = repository.save(KnowledgePage(kb_id="kb-1", url=PRICING, source=SITE))
    repository.save(read.model_copy(update={"title": "Theirs"}))

    with pytest.raises(PageWrittenElsewhere):
        repository.save(read.model_copy(update={"title": "Mine"}))
    assert repository.list_by_kb("kb-1")[0].title == "Theirs"


async def test_the_page_list_puts_pages_that_need_a_look_first(crawl, test_client, auth_headers):
    crawl.site.pages[FAQ] = 503
    crawl.site.linked.remove(TEAM)
    crawl.site.pages[TEAM] = 404
    for _ in range(FAILING_RUNS_TO_FLAG):
        await crawl.crawl()

    response = test_client.get(f"/knowledge-bases/{crawl.kb.kb_id}/pages", headers=auth_headers)

    assert response.status_code == 200, response.text
    assert [(page["url"], page["state"], page["needs_attention"]) for page in response.json()] == [
        (FAQ, "failing", True), (PRICING, "live", False), (TEAM, "gone", False),
    ]
