"""Only the site saying a page is gone deletes it; a write that fails is never recorded as done."""

import pytest

from src.crawler.worker import PageNotRead, PageRead
from tests.crawler.fakes import SITE, Redirect, a_crawl, paragraphs

URL = f"{SITE}/pricing"


@pytest.fixture
async def crawl(dynamodb_table, monkeypatch):
    crawl = a_crawl(monkeypatch)
    crawl.site.pages[URL] = paragraphs(4)
    await crawl.read(URL)
    assert crawl.chunks(URL) and crawl.index.vectors
    return crawl


@pytest.mark.parametrize("status", [404, 410])
async def test_a_page_the_site_says_is_gone_leaves_the_knowledge_base(crawl, status):
    crawl.site.pages[URL] = status

    run = await crawl.read(URL)

    assert run.read is PageRead.REMOVED
    assert crawl.chunks(URL) == [] and crawl.index.vectors == {}


@pytest.mark.parametrize("status", [500, 503, 429, 403])
async def test_a_page_that_cant_be_read_this_time_keeps_what_it_had(crawl, status):
    kept = crawl.chunks(URL)
    crawl.site.pages[URL] = status

    run = await crawl.read(URL)

    assert isinstance(run.error, PageNotRead)
    assert crawl.chunks(URL) == kept and len(crawl.index.vectors) == len(kept)


async def test_a_page_that_moved_within_the_site_is_kept_at_its_new_address(crawl):
    moved = f"{SITE}/plans"
    crawl.site.pages[moved] = paragraphs(4)
    crawl.site.pages[URL] = Redirect(moved)

    run = await crawl.read(URL)

    assert run.read is PageRead.INDEXED
    assert crawl.chunks(URL) == []
    assert crawl.chunks(moved) and set(crawl.index.vectors) == {chunk.chunk_id for chunk in crawl.chunks(moved)}


async def test_a_failed_vector_write_leaves_the_page_to_be_written_again(crawl):
    crawl.site.pages[URL] = paragraphs(4, edit=1)
    crawl.index.failing_upserts = 1

    failed = await crawl.read(URL)

    assert failed.error is not None
    assert not any("EDITED" in chunk.content for chunk in crawl.chunks(URL)), "the old text stays beside its old vector"

    await crawl.read(URL)

    edited = [chunk for chunk in crawl.chunks(URL) if "EDITED" in chunk.content]
    assert edited, "the next read wrote the edit"
    assert all(crawl.index.vectors[chunk.chunk_id] == [float(len(chunk.content))] for chunk in edited), "with its vector"


async def test_a_failed_vector_delete_still_takes_the_page_out_of_search(crawl):
    crawl.site.pages[URL] = 404
    crawl.index.failing_deletes = 1

    await crawl.read(URL)

    assert crawl.chunks(URL) == [], "search returns a vector's text only while its chunk exists"
    assert crawl.index.vectors, "the vectors are left behind, unused"


async def test_a_broken_link_to_a_page_the_knowledge_base_never_had_is_a_failed_read(crawl):
    run = await crawl.read(f"{SITE}/never-existed")

    assert isinstance(run.error, PageNotRead) and str(run.error) == "HTTP 404"
    assert f"{SITE}/never-existed" not in crawl.pages()


async def test_a_page_reached_by_several_links_is_counted_once_in_the_job(crawl):
    other = f"{SITE}/pricing?ref=nav"
    crawl.site.pages[other] = Redirect(URL)
    crawl.site.linked.append(other)

    job = await crawl.crawl()

    assert job.progress.total_chunks == len(crawl.chunks()), "read twice, held once"


async def test_a_removed_pages_vectors_that_couldnt_be_deleted_are_deleted_when_it_is_read_again(crawl):
    crawl.site.pages[URL] = 404
    crawl.index.failing_deletes = 1
    await crawl.read(URL)
    assert crawl.pages()[URL].orphan_vector_ids and crawl.index.vectors

    await crawl.read(URL)

    assert crawl.pages()[URL].orphan_vector_ids == [] and crawl.index.vectors == {}
