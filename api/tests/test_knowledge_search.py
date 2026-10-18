"""Search answers with what the knowledge base says now: each passage once, nothing without text."""

from types import SimpleNamespace

import pytest

from src.knowledge.models import ContentChunk
from src.knowledge.repository import ContentChunkRepository
from src.vectorstore.pinecone_client import QueryResponse, QueryResult, VectorMetadata
from src.vectorstore.search import SemanticSearch

KB = "kb-1"


class Index:
    """A Pinecone that returns the vectors it was given, best first, as the real one does."""

    def __init__(self, hits: list[tuple[str, float]]) -> None:
        self.hits = hits
        self.asked_for: int | None = None

    def _results(self, kb_id: str = KB) -> list[QueryResult]:
        return [QueryResult(id=i, score=s, metadata=VectorMetadata(kb_id=kb_id, chunk_id=i, source_url="")) for i, s in self.hits]

    def query(self, vector, kb_id, top_k=5, filter=None, include_metadata=True):
        self.asked_for = top_k
        return QueryResponse(results=self._results(kb_id)[:top_k])

    def query_multiple_kbs(self, vector, kb_ids, top_k=5):
        self.asked_for = top_k
        return self._results()[:top_k]


class Embeddings:
    async def embed_text_async(self, text, normalize=True):
        return SimpleNamespace(embedding=[1.0])


def stored(chunk_id: str, text: str, url: str = "https://example.com/contact", heading: str = "") -> None:
    ContentChunkRepository().save(
        ContentChunk(chunk_id=chunk_id, kb_id=KB, source_url=url, chunk_index=0, content=text, section_heading=heading)
    )


def search(hits: list[tuple[str, float]]) -> tuple[SemanticSearch, Index]:
    index = Index(hits)
    return SemanticSearch(embeddings=Embeddings(), pinecone=index, chunk_repo=ContentChunkRepository()), index


@pytest.fixture(autouse=True)
def table(dynamodb_table):
    return dynamodb_table


async def test_the_same_passage_under_several_chunks_is_one_result():
    for chunk_id in ("a", "b", "c"):
        stored(chunk_id, "Tell us what you are trying to achieve.\n\nWe reply within two days.")
    stored("d", "Registered name: Innomight Labs Ltd")
    service, _ = search([("a", 0.9), ("b", 0.9), ("c", 0.9), ("d", 0.7)])

    results = await service.search_multiple_kbs("contact", [KB], top_k=2)

    assert [r.chunk_id for r in results] == ["a", "d"], "the next best passage takes the place of the copies"


async def test_text_that_differs_only_in_whitespace_is_the_same_passage():
    stored("a", "Seats cost ten pounds.\n\nBilled monthly.")
    stored("b", "Seats cost ten pounds. Billed monthly.")
    service, _ = search([("a", 0.9), ("b", 0.89)])

    assert [r.chunk_id for r in (await service.search_multiple_kbs("price", [KB], top_k=3))] == ["a"]


async def test_a_vector_with_no_chunk_is_not_a_result():
    stored("b", "Seats cost ten pounds.")
    service, _ = search([("orphan", 0.95), ("b", 0.8)])

    results = await service.search_multiple_kbs("price", [KB], top_k=3)

    assert [r.chunk_id for r in results] == ["b"]
    assert not any("not available" in r.content for r in results)


async def test_a_single_knowledge_base_search_answers_the_same_way():
    stored("a", "Seats cost ten pounds.")
    stored("b", "Seats cost ten pounds.")
    service, _ = search([("orphan", 0.95), ("a", 0.9), ("b", 0.9)])

    response = await service.search("price", KB, top_k=3)

    assert [r.chunk_id for r in response.results] == ["a"]


async def test_results_below_the_minimum_score_are_left_out():
    stored("a", "Seats cost ten pounds.")
    stored("b", "Refunds take five days.")
    service, _ = search([("a", 0.9), ("b", 0.2)])

    assert [r.chunk_id for r in await service.search_multiple_kbs("price", [KB], top_k=3, min_score=0.3)] == ["a"]


async def test_more_than_top_k_is_asked_for_so_copies_leave_room_for_others():
    stored("a", "Seats cost ten pounds.")
    service, index = search([("a", 0.9)])

    await service.search_multiple_kbs("price", [KB], top_k=3)

    assert index.asked_for == 3 * 3


async def test_a_result_carries_the_heading_of_its_section():
    stored("a", "Section: Pricing\n\nSeats cost ten pounds.", heading="Pricing")
    service, _ = search([("a", 0.9)])

    [result] = await service.search_multiple_kbs("price", [KB], top_k=3)

    assert result.section_heading == "Pricing"
