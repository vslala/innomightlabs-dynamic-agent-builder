"""Reading a page again embeds only what changed on it, and clears what it no longer has."""

import pytest

from src.crawler.chunking import ContentChunkData, get_chunking_strategy
from src.crawler.page_chunks import prepare_page
from src.crawler.worker import PageRead
from tests.crawler.fakes import SITE, a_crawl, paragraphs

URL = f"{SITE}/pricing"


@pytest.fixture
def crawl(dynamodb_table, monkeypatch):
    return a_crawl(monkeypatch)


async def test_the_same_page_read_again_embeds_nothing(crawl):
    crawl.site.pages[URL] = paragraphs(6)
    await crawl.read(URL)
    first_run = len(crawl.embeddings.texts)
    assert first_run > 0

    again = await crawl.read(URL)

    assert again.read is PageRead.UNCHANGED
    assert len(crawl.embeddings.texts) == first_run, "no chunk went through the model again"
    assert again.ctx.total_chunks == first_run and again.ctx.total_embeddings == 0
    assert len(crawl.index.vectors) == len(crawl.chunks()) == first_run


async def test_an_edit_embeds_only_the_chunks_it_touches(crawl):
    crawl.site.pages[URL] = paragraphs(6)
    await crawl.read(URL)
    first_run = len(crawl.embeddings.texts)

    crawl.site.pages[URL] = paragraphs(6, edit=3)
    await crawl.read(URL)

    embedded_again = crawl.embeddings.texts[first_run:]
    assert 0 < len(embedded_again) < first_run
    assert all("EDITED" in text or "Paragraph 3" in text for text in embedded_again), "only chunks holding the edit"
    stored = crawl.chunks()
    assert any("EDITED" in chunk.content for chunk in stored)
    assert len(stored) == first_run, "the edit replaced chunks, it didn't add copies"


async def test_a_shorter_page_loses_the_chunks_it_no_longer_has(crawl):
    crawl.site.pages[URL] = paragraphs(8)
    await crawl.read(URL)
    before = crawl.chunks()

    crawl.site.pages[URL] = paragraphs(2)
    await crawl.read(URL)

    after = crawl.chunks()
    assert 0 < len(after) < len(before)
    assert {chunk.chunk_id for chunk in after} == set(crawl.index.vectors), "the index kept nothing the page lost"


async def test_a_paragraph_inserted_at_the_top_re_embeds_only_the_chunks_holding_it(crawl):
    crawl.site.pages[URL] = paragraphs(8)
    await crawl.read(URL)
    first_run = len(crawl.embeddings.texts)

    crawl.site.pages[URL] = "Announcement: prices change in March, and every plan gets more seats.\n\n" + paragraphs(8)
    await crawl.read(URL)

    embedded_again = crawl.embeddings.texts[first_run:]
    assert embedded_again and all("Announcement" in text for text in embedded_again), "nothing after it moved ids"
    assert {chunk.chunk_id for chunk in crawl.chunks()} == set(crawl.index.vectors)


async def test_a_retitled_page_is_indexed_again_under_its_new_title(crawl):
    crawl.site.pages[URL] = paragraphs(3)
    await crawl.read(URL)
    first_run = len(crawl.embeddings.texts)

    crawl.worker.extractor.title = "Plans and pricing"
    await crawl.read(URL)

    assert len(crawl.embeddings.texts) == 2 * first_run
    assert {chunk.page_title for chunk in crawl.chunks()} == {"Plans and pricing"}


def test_the_first_read_of_a_page_makes_every_chunk_new():
    chunks = get_chunking_strategy("hierarchical").chunk(content=paragraphs(3), source_url=URL, page_title="Pricing", sections=None)

    page = prepare_page("kb-1", URL, "Pricing", chunks, committed=set())

    assert page.new == page.chunks and page.unchanged == 0
    assert {chunk.parent_chunk_id for chunk in page.chunks} - {None} <= {chunk.chunk_id for chunk in page.chunks}


def test_identical_chunks_on_one_page_get_their_own_ids():
    repeated = [ContentChunkData(content="Contact us at hello@acme.example", chunk_index=index, level=2) for index in range(2)]

    page = prepare_page("kb-1", URL, "Pricing", repeated, committed=set())

    assert len({chunk.chunk_id for chunk in page.chunks}) == 2


def test_a_chunk_keeps_its_id_wherever_it_moves_on_the_page():
    one = ContentChunkData(content="Seats cost ten pounds.", chunk_index=0, level=2)
    moved = ContentChunkData(content="Seats cost ten pounds.", chunk_index=7, level=2)

    assert (
        prepare_page("kb-1", URL, "Pricing", [one], committed=set()).chunks[0].chunk_id
        == prepare_page("kb-1", URL, "Pricing", [moved], committed=set()).chunks[0].chunk_id
    )
