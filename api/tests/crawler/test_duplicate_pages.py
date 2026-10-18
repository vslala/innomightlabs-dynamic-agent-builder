"""Pages that say the same thing are in the knowledge base once: the best address keeps the chunks."""

import pytest

from src.knowledge.models import CrawlJobStatus, KnowledgePageState
from tests.crawler.fakes import SITE, a_crawl, paragraphs

CONTACT = f"{SITE}/contact"
VARIANTS = [f"{SITE}/contact?topic=product", f"{SITE}/contact?topic=project"]
TEXT = paragraphs(3, topic="contact")


@pytest.fixture
def crawl(dynamodb_table, monkeypatch):
    return a_crawl(monkeypatch)


def live(crawl) -> set[str]:
    return {url for url, page in crawl.pages().items() if page.state == KnowledgePageState.LIVE}


def aliases(crawl) -> dict[str, str]:
    return {url: page.duplicate_of for url, page in crawl.pages().items() if page.state == KnowledgePageState.DUPLICATE}


async def test_pages_with_the_same_text_are_indexed_once(crawl):
    for url in (*VARIANTS, CONTACT):
        crawl.site.publish(url, TEXT)

    job = await crawl.crawl()

    assert live(crawl) == {CONTACT}, "the address with no query string is the one kept"
    assert aliases(crawl) == {url: CONTACT for url in VARIANTS}
    assert {chunk.source_url for chunk in crawl.chunks()} == {CONTACT}
    assert set(crawl.index.vectors) == {chunk.chunk_id for chunk in crawl.chunks()}
    assert job.progress.duplicate_urls == 2 and job.progress.successful_urls == 3


async def test_the_best_address_is_kept_whichever_is_read_first(crawl):
    crawl.site.publish(VARIANTS[0], TEXT)
    await crawl.crawl()
    assert live(crawl) == {VARIANTS[0]}

    crawl.site.publish(CONTACT, TEXT)
    await crawl.crawl()

    assert live(crawl) == {CONTACT} and aliases(crawl) == {VARIANTS[0]: CONTACT}
    assert {chunk.source_url for chunk in crawl.chunks()} == {CONTACT}
    assert set(crawl.index.vectors) == {chunk.chunk_id for chunk in crawl.chunks()}


async def test_a_second_crawl_embeds_nothing_and_keeps_the_same_pages(crawl):
    for url in (CONTACT, *VARIANTS):
        crawl.site.publish(url, TEXT)
    await crawl.crawl()
    embedded, chunks = len(crawl.embeddings.texts), {chunk.chunk_id for chunk in crawl.chunks()}

    again = await crawl.crawl()

    assert len(crawl.embeddings.texts) == embedded and {chunk.chunk_id for chunk in crawl.chunks()} == chunks
    assert live(crawl) == {CONTACT} and len(aliases(crawl)) == 2
    assert again.progress.duplicate_urls == 2 and again.progress.unchanged_urls == 1


async def test_a_page_that_comes_to_say_what_another_says_gives_up_its_chunks(crawl):
    crawl.site.publish(CONTACT, TEXT)
    crawl.site.publish(VARIANTS[0], paragraphs(3, topic="partnership"))
    await crawl.crawl()
    assert live(crawl) == {CONTACT, VARIANTS[0]}

    crawl.site.publish(VARIANTS[0], TEXT)
    await crawl.crawl()

    assert live(crawl) == {CONTACT} and aliases(crawl) == {VARIANTS[0]: CONTACT}
    assert {chunk.source_url for chunk in crawl.chunks()} == {CONTACT}
    assert set(crawl.index.vectors) == {chunk.chunk_id for chunk in crawl.chunks()}


async def test_an_alias_that_changes_is_indexed_on_its_own_again(crawl):
    for url in (CONTACT, VARIANTS[0]):
        crawl.site.publish(url, TEXT)
    await crawl.crawl()

    crawl.site.publish(VARIANTS[0], paragraphs(3, topic="partnership"))
    await crawl.crawl()

    assert live(crawl) == {CONTACT, VARIANTS[0]} and aliases(crawl) == {}
    assert {chunk.source_url for chunk in crawl.chunks()} == {CONTACT, VARIANTS[0]}


async def test_when_the_page_standing_behind_the_others_is_removed_they_take_its_place(crawl):
    for url in (CONTACT, *VARIANTS):
        crawl.site.publish(url, TEXT)
    await crawl.crawl()

    crawl.site.linked.remove(CONTACT)
    crawl.site.pages[CONTACT] = 404
    job = await crawl.crawl()

    assert job.status == CrawlJobStatus.COMPLETED
    assert len(live(crawl)) == 1 and live(crawl) <= set(VARIANTS), "one alias took over in the same crawl"
    assert crawl.pages()[CONTACT].state == KnowledgePageState.GONE
    assert {chunk.source_url for chunk in crawl.chunks()} == live(crawl)
    assert set(crawl.index.vectors) == {chunk.chunk_id for chunk in crawl.chunks()}


async def test_the_root_written_with_a_slash_is_kept_over_the_bare_domain(crawl):
    bare = SITE  # a ledger from before discovery wrote the root as "/"
    crawl.site.publish(bare, TEXT)
    crawl.site.publish(f"{SITE}/", TEXT)

    await crawl.crawl()

    assert live(crawl) == {f"{SITE}/"} and aliases(crawl) == {bare: f"{SITE}/"}
