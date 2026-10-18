"""A page that says what it said last time costs a 304 or a hash, never chunking or embedding, unless it's unsettled."""

import pytest

from src.crawler.worker import PageRead
from src.knowledge.models import KnowledgePageState
from src.knowledge.repository import ContentChunkRepository
from tests.crawler.fakes import SITE, a_crawl, paragraphs

URL = f"{SITE}/pricing"


@pytest.fixture
async def crawl(dynamodb_table, monkeypatch):
    crawl = a_crawl(monkeypatch)
    crawl.site.pages[URL] = paragraphs(4)
    await crawl.read(URL)
    return crawl


async def test_a_site_that_sends_etags_answers_304_for_an_unchanged_page(crawl):
    crawl.site.etags = True
    await crawl.read(URL)  # the first read that gets an ETag
    embedded = len(crawl.embeddings.texts)

    run = await crawl.read(URL)

    assert run.read is PageRead.UNCHANGED and len(crawl.embeddings.texts) == embedded
    assert crawl.pages()[URL].last_seen_job == run.ctx.job.job_id, "it was seen this run"


async def test_a_site_without_etags_is_skipped_on_the_same_text(crawl):
    embedded = len(crawl.embeddings.texts)

    run = await crawl.read(URL)

    assert run.read is PageRead.UNCHANGED and len(crawl.embeddings.texts) == embedded


async def test_a_changed_page_is_read_in_full_despite_its_old_etag(crawl):
    crawl.site.etags = True
    await crawl.read(URL)
    crawl.site.pages[URL] = paragraphs(4, edit=2)

    run = await crawl.read(URL)

    assert run.read is PageRead.INDEXED
    assert any("EDITED" in chunk.content for chunk in crawl.chunks(URL))


async def test_a_page_whose_write_stopped_halfway_is_never_skipped(crawl, monkeypatch):
    crawl.site.etags = True
    crawl.site.pages[URL] = paragraphs(4, edit=1)

    def crash(self, chunks):
        raise RuntimeError("the worker died")

    real_save = ContentChunkRepository.batch_save
    monkeypatch.setattr(ContentChunkRepository, "batch_save", crash)
    await crawl.read(URL)
    monkeypatch.setattr(ContentChunkRepository, "batch_save", real_save)
    assert crawl.pages()[URL].pending_ids and not crawl.pages()[URL].settled

    run = await crawl.read(URL)

    assert run.read is PageRead.INDEXED, "its ETag may be from the write that didn't finish"
    assert crawl.pages()[URL].settled
    assert any("EDITED" in chunk.content for chunk in crawl.chunks(URL))


async def test_a_page_that_couldnt_be_read_is_read_in_full_next_time(crawl):
    crawl.site.pages[URL] = 503
    await crawl.read(URL)
    assert crawl.pages()[URL].state == KnowledgePageState.FAILING
    crawl.site.pages[URL] = paragraphs(4)

    run = await crawl.read(URL)

    assert run.read is PageRead.INDEXED and crawl.pages()[URL].state == KnowledgePageState.LIVE
