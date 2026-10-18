"""Uploading a file again is the same page read again: only what changed is embedded, what it lost is deleted."""

from types import SimpleNamespace

import pytest

from src.knowledge.models import UPLOAD_SOURCE, KnowledgeBase
from src.knowledge.repository import ContentChunkRepository, KnowledgeBaseRepository, KnowledgePageRepository
from src.knowledge.service import KnowledgeBaseService
from tests.crawler.fakes import CountingEmbeddings, FakeIndex, paragraphs
from tests.mock_data import TEST_USER_EMAIL, kb_fields


@pytest.fixture
def upload(dynamodb_table, monkeypatch):
    kb = KnowledgeBaseRepository().save(KnowledgeBase(name="Handbook", **kb_fields(TEST_USER_EMAIL)))
    embeddings, index = CountingEmbeddings(), FakeIndex()
    monkeypatch.setattr("src.vectorstore.get_embeddings_service", lambda: embeddings)
    monkeypatch.setattr("src.vectorstore.get_pinecone_client", lambda validate=True: index)

    async def send(text: str, filename: str = "handbook.md"):
        return await KnowledgeBaseService().ingest_text_content(kb, filename, text)

    return SimpleNamespace(kb=kb, index=index, send=send)


async def test_the_same_file_uploaded_again_embeds_nothing(upload):
    first = await upload.send(paragraphs(5))

    again = await upload.send(paragraphs(5))

    assert first.vector_count > 0 and again.vector_count == 0
    assert (again.total_pages, again.total_chunks) == (1, first.chunk_count), "one page, not two"


async def test_a_shorter_file_loses_the_chunks_it_no_longer_has(upload):
    await upload.send(paragraphs(10))

    shorter = await upload.send(paragraphs(1))

    stored = ContentChunkRepository().find_all_by_kb(upload.kb.kb_id)
    assert len(stored) == shorter.chunk_count == shorter.total_chunks
    assert {chunk.chunk_id for chunk in stored} == set(upload.index.vectors)


async def test_an_upload_is_a_page_the_uploads_own(upload):
    await upload.send(paragraphs(2))

    [page] = KnowledgePageRepository().list_by_kb(upload.kb.kb_id)

    assert page.source == UPLOAD_SOURCE and page.url == f"file://{upload.kb.kb_id}/handbook.md"
