"""Deleting a knowledge base deletes its vectors too, or deletes nothing and says to try again."""

from types import SimpleNamespace

import pytest

from src.knowledge.models import ContentChunk, KnowledgeBase, KnowledgeBaseStatus
from src.knowledge.router import get_kb_service
from src.knowledge.repository import ContentChunkRepository, KnowledgeBaseRepository
from src.knowledge.service import KnowledgeBaseService
from tests.crawler.fakes import FakeIndex
from tests.mock_data import TEST_USER_EMAIL, kb_fields


class FakeNamespaces(FakeIndex):
    """A Pinecone client that can delete a namespace, or fail to, as the real one's `delete_namespace` does."""

    def __init__(self) -> None:
        super().__init__()
        self._index: object | None = object()
        self.deletable = True

    def delete_namespace(self, kb_id: str) -> bool:
        if self.deletable:
            self.vectors.clear()
        return self.deletable


@pytest.fixture
def knowledge_base(dynamodb_table):
    kb = KnowledgeBaseRepository().save(KnowledgeBase(name="Docs", **kb_fields(TEST_USER_EMAIL)))
    ContentChunkRepository().batch_save([
        ContentChunk(chunk_id="c1", kb_id=kb.kb_id, source_url="https://example.com", chunk_index=0, content="Seats cost ten pounds.")
    ])
    index = FakeNamespaces()
    index.vectors = {"c1": [1.0]}
    service = KnowledgeBaseService()
    service._pinecone = index
    return SimpleNamespace(kb=kb, index=index, service=service)


def stored(kb: KnowledgeBase) -> KnowledgeBase | None:
    return KnowledgeBaseRepository().find_in_account(kb.account_id, kb.kb_id)


def test_deleting_removes_the_vectors_and_the_chunks(knowledge_base):
    result = knowledge_base.service.soft_delete(knowledge_base.kb)

    assert result.success and result.vectors_deleted
    assert knowledge_base.index.vectors == {}
    assert not ContentChunkRepository().has_any(knowledge_base.kb.kb_id)
    assert stored(knowledge_base.kb).status == KnowledgeBaseStatus.DELETED


def test_when_the_vectors_cant_be_deleted_nothing_is_and_it_can_be_tried_again(knowledge_base):
    knowledge_base.index.deletable = False

    failed = knowledge_base.service.soft_delete(knowledge_base.kb)

    assert not failed.success and failed.retryable
    assert ContentChunkRepository().has_any(knowledge_base.kb.kb_id), "the chunks still record that vectors exist"
    assert stored(knowledge_base.kb).status == KnowledgeBaseStatus.ACTIVE

    knowledge_base.index.deletable = True
    assert knowledge_base.service.soft_delete(knowledge_base.kb).success
    assert knowledge_base.index.vectors == {}


def test_without_pinecone_a_knowledge_base_with_content_isnt_deleted(knowledge_base):
    knowledge_base.index._index = None

    result = knowledge_base.service.soft_delete(knowledge_base.kb)

    assert not result.success and result.retryable
    assert ContentChunkRepository().has_any(knowledge_base.kb.kb_id)


def test_without_pinecone_an_empty_knowledge_base_is_deleted(knowledge_base):
    ContentChunkRepository().delete_all_by_kb(knowledge_base.kb.kb_id)
    knowledge_base.index._index = None

    assert knowledge_base.service.soft_delete(knowledge_base.kb).success


def test_the_route_says_503_when_the_vectors_cant_be_deleted(knowledge_base, test_client, auth_headers):
    knowledge_base.index.deletable = False
    test_client.app.dependency_overrides[get_kb_service] = lambda: knowledge_base.service

    try:
        response = test_client.delete(f"/knowledge-bases/{knowledge_base.kb.kb_id}", headers=auth_headers)
    finally:
        test_client.app.dependency_overrides.pop(get_kb_service)

    assert response.status_code == 503, response.text
    assert stored(knowledge_base.kb).status == KnowledgeBaseStatus.ACTIVE


def test_a_namespace_that_never_existed_counts_as_deleted(monkeypatch):
    from pinecone.exceptions import NotFoundException

    from src.vectorstore.pinecone_client import PineconeClient

    class Index:
        def delete(self, **_):
            raise NotFoundException(status=404, reason="Namespace not found")

    client = PineconeClient.__new__(PineconeClient)
    client._index = Index()

    assert client.delete_namespace("kb-1") is True


class IndexThatErrorsAfterDeleting:
    """A server whose reply the SDK can't parse: the delete happens, then the call raises."""

    def __init__(self, stored: set[str], applies: bool = True):
        self.stored, self.applies = stored, applies

    def delete(self, ids, namespace):
        if self.applies:
            self.stored -= set(ids)
        raise TypeError("'str' object has no attribute '_response_info'")

    def fetch(self, ids, namespace):
        return SimpleNamespace(vectors={vector_id: {} for vector_id in ids if vector_id in self.stored})


def a_client(index):
    from src.vectorstore.pinecone_client import PineconeClient

    client = PineconeClient.__new__(PineconeClient)
    client._index = index
    return client


def test_a_delete_that_raised_after_applying_isnt_reported_as_failed():
    client = a_client(IndexThatErrorsAfterDeleting({"a", "b", "c"}))

    assert client.delete_by_ids(["a", "b"], "kb-1") == []


def test_a_delete_that_raised_and_didnt_apply_is_reported_as_failed():
    client = a_client(IndexThatErrorsAfterDeleting({"a", "b", "c"}, applies=False))

    assert client.delete_by_ids(["a", "b"], "kb-1") == ["a", "b"]
