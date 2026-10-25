"""Documents sent with a message: attached as references, shown to the agent, swept when never sent."""

import time
from datetime import datetime, timedelta, timezone

import pytest

from src.config import settings
from src.conversations import documents as conversation_documents
from src.conversations.documents import ConversationDocuments, document_tag, sweep_unsent
from src.conversations.models import Conversation
from src.documents.models import Document, DocumentOwner, DocumentStatus, OwnerKind
from src.documents.repository import DocumentRepository
from src.documents.service import get_document_service
from src.messages.models import MessageReference
from src.messages.references import ReferenceRefused
from tests.documents_support import create_documents_bucket, pdf_with_text
from tests.oauth_handoff import owner_headers


@pytest.fixture
def chat(test_client, monkeypatch):
    monkeypatch.setattr(settings, "cli_runner_base_url", "")
    create_documents_bucket()
    agent = test_client.post(
        "/agents",
        json={"agent_name": "Reader", "agent_architecture": "krishna-memgpt", "agent_provider": "Bedrock",
              "agent_persona": "Reads documents."},
        headers=owner_headers(),
    ).json()
    conversation = test_client.post(
        "/conversations/", json={"title": "Payslips", "agent_id": agent["agent_id"]}, headers=owner_headers()
    ).json()
    return agent["agent_id"], conversation["conversation_id"]


def _upload(test_client, conversation_id, name="payslip.pdf"):
    return test_client.post(
        f"/conversations/{conversation_id}/documents",
        files={"file": (name, pdf_with_text("Net pay 5608.87"), "application/pdf")},
        headers=owner_headers(),
    ).json()


def test_an_upload_waits_to_be_sent_and_leaves_the_composer_once_it_is(test_client, chat, monkeypatch):
    agent_id, conversation_id = chat
    document = _upload(test_client, conversation_id)
    unsent = lambda: [d["document_id"] for d in test_client.get(  # noqa: E731
        f"/conversations/{conversation_id}/documents?unsent=true", headers=owner_headers()).json()]
    assert unsent() == [document["document_id"]]

    started = {}

    def fake_start_turn(**kwargs):
        started.update(kwargs)
        raise RuntimeError("stop here")

    monkeypatch.setattr("src.agents.router.start_turn", fake_start_turn)
    with pytest.raises(RuntimeError, match="stop here"):
        test_client.post(f"/agents/{agent_id}/{conversation_id}/send-message", headers=owner_headers(),
                         json={"content": "what is my net pay?", "references": [{"kind": "document", "id": document["document_id"]}]})

    assert started["references"] == [MessageReference(kind="document", id=document["document_id"], label="payslip.pdf")]
    assert unsent() == []
    all_documents = test_client.get(f"/conversations/{conversation_id}/documents", headers=owner_headers()).json()
    assert [d["document_id"] for d in all_documents] == [document["document_id"]]


def test_a_document_that_isnt_the_conversations_is_refused(test_client, chat):
    agent_id, conversation_id = chat

    response = test_client.post(f"/agents/{agent_id}/{conversation_id}/send-message", headers=owner_headers(),
                                json={"content": "hi", "references": [{"kind": "document", "id": "not-here"}]})

    assert response.status_code == 422 and response.json()["detail"]["code"] == "reference_not_found"


def test_an_unknown_kind_is_refused(test_client, chat):
    agent_id, conversation_id = chat

    response = test_client.post(f"/agents/{agent_id}/{conversation_id}/send-message", headers=owner_headers(),
                                json={"content": "hi", "references": [{"kind": "video", "id": "v"}]})

    assert response.status_code == 422 and response.json()["detail"]["code"] == "reference_kind_unknown"


def _document(**changes) -> Document:
    fields = dict(account_id="acct", owner_kind=OwnerKind.CONVERSATION, owner_id="conv", filename="sales.xlsx")
    return Document(**{**fields, **changes})


def test_the_tag_says_how_far_reading_got_and_never_holds_the_content():
    ready = document_tag(_document(status=DocumentStatus.READY, page_count=3, table_count=2))
    reading = document_tag(_document(status=DocumentStatus.PARSING))
    failed = document_tag(_document(status=DocumentStatus.FAILED, error="the PDF is password protected"))

    assert 'status="ready" pages="3" tables="2"' in ready and "describe_document" in ready
    assert "still being read" in reading and "pages=" not in reading
    assert "password protected" in failed


def test_the_kind_describes_the_conversations_documents_in_one_lookup(dynamodb_table, monkeypatch):
    calls = []
    present = _document(status=DocumentStatus.READY)

    class Service:
        def documents(self, owner):
            calls.append(owner)
            return [present]

    monkeypatch.setattr(conversation_documents, "get_document_service", lambda: Service())
    conversation = Conversation(conversation_id="conv", title="t", agent_id="a", created_by="u", account_id="acct")

    tags = ConversationDocuments().describe(
        conversation, [MessageReference(kind="document", id=present.document_id), MessageReference(kind="document", id="gone")]
    )

    assert list(tags) == [present.document_id] and len(calls) == 1


def test_attaching_another_conversations_document_is_refused(dynamodb_table):
    create_documents_bucket()
    conversation = Conversation(conversation_id="conv", title="t", agent_id="a", created_by="u", account_id="acct")

    with pytest.raises(ReferenceRefused):
        ConversationDocuments().attach(conversation, ["someone-elses"])


def test_the_sweep_removes_only_conversation_uploads_never_sent(dynamodb_table):
    create_documents_bucket()
    repository = DocumentRepository()
    old = datetime.now(timezone.utc) - timedelta(days=2)
    unsent = repository.save(_document(attached_at=0, created_at=old))
    fresh = repository.save(_document(attached_at=0))
    sent = repository.save(_document(attached_at=int(time.time()), created_at=old))
    before_attaching = repository.save(_document(attached_at=None, created_at=old))
    knowledge = repository.save(_document(owner_kind=OwnerKind.KNOWLEDGE_BASE, owner_id="kb", created_at=old))

    assert sweep_unsent() == 1

    owner = DocumentOwner("acct", OwnerKind.CONVERSATION, "conv")
    remaining = {d.document_id for d in get_document_service().documents(owner)}
    assert remaining == {fresh.document_id, sent.document_id, before_attaching.document_id}
    assert repository.get(DocumentOwner("acct", OwnerKind.KNOWLEDGE_BASE, "kb"), knowledge.document_id) is not None
    assert unsent.document_id not in remaining


def test_a_document_sent_while_it_is_being_read_stays_sent(dynamodb_table):
    repository = DocumentRepository()
    document = repository.save(_document(attached_at=0))
    claimed = repository.claim(document.owner, document.document_id, lease_seconds=60, now=int(time.time()))
    assert claimed is not None

    repository.mark_attached(claimed, now=123)
    repository.save_in_flight(claimed.model_copy(update={"status": DocumentStatus.READY}))

    saved = repository.get(document.owner, document.document_id)
    assert saved.status == DocumentStatus.READY and saved.attached_at == 123
