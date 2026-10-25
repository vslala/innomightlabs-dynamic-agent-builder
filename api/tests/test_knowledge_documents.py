"""Files uploaded to a knowledge base: accepted at once, read and indexed in the background, deleted page-first."""

from types import SimpleNamespace

import pytest

from src.config import settings
from src.documents.models import DocumentStatus
from src.knowledge.models import KnowledgeBase, KnowledgeBaseStatus
from src.knowledge.repository import ContentChunkRepository, KnowledgeBaseRepository, KnowledgePageRepository
from tests.crawler.fakes import CountingEmbeddings, FakeIndex
from tests.documents_support import bucket_keys, create_documents_bucket, pdf_with_text
from tests.mock_data import TEST_USER_EMAIL, TEST_USER_EMAIL_2, kb_fields
from tests.oauth_handoff import owner_headers

PAYSLIP = pdf_with_text("Net pay 5608.87 for June")


@pytest.fixture
def kb(dynamodb_table, monkeypatch):
    knowledge_base = KnowledgeBaseRepository().save(KnowledgeBase(name="Payslips", **kb_fields(TEST_USER_EMAIL)))
    embeddings, index = CountingEmbeddings(), FakeIndex()
    monkeypatch.setattr("src.vectorstore.get_embeddings_service", lambda: embeddings)
    monkeypatch.setattr("src.vectorstore.get_pinecone_client", lambda validate=True: index)
    monkeypatch.setattr(settings, "is_pinecone_configured", lambda: True)
    monkeypatch.setattr(settings, "cli_runner_base_url", "")  # PDFs read from their text layer
    return SimpleNamespace(kb=knowledge_base, index=index, s3=create_documents_bucket())


def upload(test_client, kb, *, filename="payslip.pdf", data=PAYSLIP, headers=None):
    return test_client.post(
        f"/knowledge-bases/{kb.kb.kb_id}/content-upload",
        files={"attachment": (filename, data, "application/pdf")},
        data={"metadata": "June payslip"},
        headers=headers or owner_headers(),
    )


def test_a_pdf_upload_is_accepted_then_read_and_indexed_in_the_background(test_client, kb):
    response = upload(test_client, kb)

    assert response.status_code == 202 and response.json()["status"] == "pending"
    document_id = response.json()["document_id"]
    # TestClient runs the background task before returning
    document = test_client.get(f"/knowledge-bases/{kb.kb.kb_id}/documents/{document_id}", headers=owner_headers()).json()
    assert document["status"] == "ready" and document["parser"] == "pdf_text_layer" and document["page_count"] == 1
    page = KnowledgePageRepository().find(kb.kb.kb_id, "file://" + kb.kb.kb_id + "/payslip.pdf")
    assert page and page.chunk_ids and set(page.chunk_ids) <= set(kb.index.vectors)
    chunks = ContentChunkRepository().find_all_by_kb(kb.kb.kb_id)
    assert any("5608.87" in chunk.content and "June payslip" in chunk.content for chunk in chunks)
    assert KnowledgeBaseRepository().find_in_account(kb.kb.account_id, kb.kb.kb_id).total_chunks == len(page.chunk_ids)


def test_a_file_that_cant_be_read_is_refused(test_client, kb):
    response = upload(test_client, kb, filename="setup.exe", data=b"MZ")

    assert response.status_code == 400 and "can be read" in response.json()["detail"]


def test_a_file_over_the_limit_is_refused(test_client, kb, monkeypatch):
    monkeypatch.setattr(settings, "document_max_bytes", 10)

    assert upload(test_client, kb).status_code == 413


def test_documents_are_listed_newest_first_a_page_at_a_time(test_client, kb):
    for name in ("a.pdf", "b.pdf", "c.pdf"):
        upload(test_client, kb, filename=name, data=pdf_with_text(f"File {name}"))

    first = test_client.get(f"/knowledge-bases/{kb.kb.kb_id}/documents?limit=2", headers=owner_headers()).json()
    rest = test_client.get(
        f"/knowledge-bases/{kb.kb.kb_id}/documents?limit=2&cursor={first['next_cursor']}", headers=owner_headers()
    ).json()

    assert [d["filename"] for d in first["items"] + rest["items"]] == ["c.pdf", "b.pdf", "a.pdf"]
    assert first["has_more"] and not rest["has_more"]


def test_deleting_a_document_takes_its_page_out_then_its_files_then_its_record(test_client, kb):
    document_id = upload(test_client, kb).json()["document_id"]
    page_url = f"file://{kb.kb.kb_id}/payslip.pdf"

    response = test_client.delete(f"/knowledge-bases/{kb.kb.kb_id}/documents/{document_id}", headers=owner_headers())

    assert response.status_code == 204
    assert KnowledgePageRepository().find(kb.kb.kb_id, page_url).chunk_ids == [] and kb.index.vectors == {}
    assert bucket_keys(kb.s3) == set()
    assert test_client.get(f"/knowledge-bases/{kb.kb.kb_id}/documents/{document_id}", headers=owner_headers()).status_code == 404


def test_deleting_the_knowledge_base_deletes_its_documents(test_client, kb, monkeypatch):
    upload(test_client, kb)
    monkeypatch.setattr(FakeIndex, "_index", object(), raising=False)
    monkeypatch.setattr(FakeIndex, "delete_namespace", lambda self, kb_id: True, raising=False)

    assert test_client.delete(f"/knowledge-bases/{kb.kb.kb_id}", headers=owner_headers()).status_code == 204

    assert bucket_keys(kb.s3) == set()
    assert KnowledgeBaseRepository().find_in_account(kb.kb.account_id, kb.kb.kb_id).status == KnowledgeBaseStatus.DELETED


def test_a_failed_document_can_be_read_again(test_client, kb):
    broken = upload(test_client, kb, filename="broken.pdf", data=b"not a pdf").json()
    document_url = f"/knowledge-bases/{kb.kb.kb_id}/documents/{broken['document_id']}"
    assert test_client.get(document_url, headers=owner_headers()).json()["status"] == DocumentStatus.FAILED.value

    retried = test_client.post(f"{document_url}/retry", headers=owner_headers())

    assert retried.status_code == 202 and test_client.get(document_url, headers=owner_headers()).json()["status"] == "failed"


def test_someone_else_cant_see_or_upload_to_the_knowledge_base(test_client, kb):
    stranger = owner_headers(TEST_USER_EMAIL_2)

    assert upload(test_client, kb, headers=stranger).status_code == 404
    assert test_client.get(f"/knowledge-bases/{kb.kb.kb_id}/documents", headers=stranger).status_code == 404
