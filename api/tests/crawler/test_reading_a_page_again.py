"""Reading a page again embeds only what changed on it, and clears what it no longer has."""

from types import SimpleNamespace

import pytest

from src.knowledge.models import CrawlConfig, CrawlJob, CrawlSourceType, KnowledgeBase  # first: the knowledge package loads the crawler
from src.crawler.chunking import get_chunking_strategy
from src.crawler.extractor import ExtractedContent
from src.crawler.page_chunks import prepare_page
from src.crawler.worker import CrawlContext, CrawlerWorker
from src.knowledge.repository import ContentChunkRepository, KnowledgeBaseRepository
from src.vectorstore.embeddings import EmbeddingResult
from tests.mock_data import TEST_USER_EMAIL, kb_fields

URL = "https://example.com/pricing"


class CountingEmbeddings:
    def __init__(self) -> None:
        self.texts: list[str] = []

    async def embed_texts_async(self, texts: list[str], **_: object) -> list[EmbeddingResult]:
        self.texts += texts
        return [EmbeddingResult(embedding=[float(len(text))], input_text_token_count=1) for text in texts]


class FakeIndex:
    def __init__(self) -> None:
        self.vectors: dict[str, list[float]] = {}

    def upsert(self, vectors: list, kb_id: str) -> int:
        self.vectors.update({vector.id: vector.values for vector in vectors})
        return len(vectors)

    def delete_by_ids(self, ids: list[str], kb_id: str) -> bool:
        for chunk_id in ids:
            self.vectors.pop(chunk_id, None)
        return True


class FakeExtractor:
    def __init__(self, text: str) -> None:
        self.text = text

    async def fetch_and_extract(self, url: str) -> ExtractedContent:
        return ExtractedContent(url=url, title="Pricing", full_text=self.text)


def paragraphs(count: int, *, edit: int | None = None) -> str:
    return "\n\n".join(
        f"Paragraph {n}: " + ("EDITED " if n == edit else "") + "plans, seats and billing explained at length. " * 12
        for n in range(count)
    )


@pytest.fixture
def crawl(dynamodb_table):
    kb = KnowledgeBaseRepository().save(KnowledgeBase(name="Site", **kb_fields(TEST_USER_EMAIL)))
    job = CrawlJob(
        kb_id=kb.kb_id, created_by=TEST_USER_EMAIL, config=CrawlConfig(source_type=CrawlSourceType.URL, source_url=URL)
    )
    worker = CrawlerWorker()
    worker._embeddings, worker._pinecone = CountingEmbeddings(), FakeIndex()

    async def read(text: str) -> CrawlContext:
        """One crawl run over the page, as its own run (a new context)."""
        ctx = CrawlContext(job=job, kb=kb, account_id=kb.account_id)
        worker.extractor = FakeExtractor(text)
        await worker._process_single_url(ctx, URL)
        return ctx

    return SimpleNamespace(kb=kb, worker=worker, read=read, embeddings=worker._embeddings, index=worker._pinecone)


async def test_the_same_page_read_again_embeds_nothing(crawl):
    await crawl.read(paragraphs(6))
    first_run = len(crawl.embeddings.texts)
    assert first_run > 0

    again = await crawl.read(paragraphs(6))

    assert len(crawl.embeddings.texts) == first_run, "no chunk went through the model again"
    assert again.total_chunks == first_run and again.total_embeddings == 0
    assert len(crawl.index.vectors) == len(ContentChunkRepository().find_all_by_kb(crawl.kb.kb_id)) == first_run


async def test_an_edit_embeds_only_the_chunks_it_touches(crawl):
    await crawl.read(paragraphs(6))
    first_run = len(crawl.embeddings.texts)

    await crawl.read(paragraphs(6, edit=3))

    embedded_again = crawl.embeddings.texts[first_run:]
    assert 0 < len(embedded_again) < first_run
    assert all("EDITED" in text or "Paragraph 3" in text for text in embedded_again), "only chunks holding the edit"
    stored = ContentChunkRepository().find_all_by_kb(crawl.kb.kb_id)
    assert any("EDITED" in chunk.content for chunk in stored)
    assert len(stored) == first_run, "the edit replaced chunks, it didn't add copies"


async def test_a_shorter_page_loses_the_chunks_it_no_longer_has(crawl):
    await crawl.read(paragraphs(8))
    before = ContentChunkRepository().find_all_by_kb(crawl.kb.kb_id)

    await crawl.read(paragraphs(2))

    after = ContentChunkRepository().find_all_by_kb(crawl.kb.kb_id)
    assert 0 < len(after) < len(before)
    assert {chunk.chunk_id for chunk in after} == set(crawl.index.vectors), "the index kept nothing the page lost"


def test_the_first_read_of_a_page_changes_every_chunk():
    chunks = get_chunking_strategy("hierarchical").chunk(content=paragraphs(3), source_url=URL, page_title="Pricing", sections=None)

    page = prepare_page("kb-1", URL, "Pricing", chunks, stored={})

    assert page.changed == page.chunks and page.stale == [] and page.reused == 0
    assert {chunk.parent_chunk_id for chunk in page.chunks} - {None} <= {chunk.chunk_id for chunk in page.chunks}
