"""Documents uploaded to a conversation: read in the background, kept with the conversation, deleted with it."""

import pytest

from src.config import settings
from tests.documents_support import bucket_keys, create_documents_bucket, pdf_with_text
from tests.mock_data import TEST_USER_EMAIL_2
from tests.oauth_handoff import owner_headers


@pytest.fixture
def chat(test_client, monkeypatch):
    monkeypatch.setattr(settings, "cli_runner_base_url", "")
    s3 = create_documents_bucket()
    agent = test_client.post(
        "/agents",
        json={"agent_name": "Reader", "agent_architecture": "krishna-memgpt", "agent_provider": "Bedrock",
              "agent_persona": "Reads documents."},
        headers=owner_headers(),
    )
    assert agent.status_code in (200, 201), agent.text
    conversation = test_client.post(
        "/conversations/", json={"title": "Payslips", "agent_id": agent.json()["agent_id"]}, headers=owner_headers()
    )
    assert conversation.status_code == 201, conversation.text
    return conversation.json()["conversation_id"], s3


def upload(test_client, conversation_id, headers=None):
    return test_client.post(
        f"/conversations/{conversation_id}/documents",
        files={"file": ("payslip.pdf", pdf_with_text("Net pay 5608.87"), "application/pdf")},
        headers=headers or owner_headers(),
    )


def test_a_document_is_read_and_listed_with_the_conversation(test_client, chat):
    conversation_id, s3 = chat

    accepted = upload(test_client, conversation_id)

    assert accepted.status_code == 202
    listed = test_client.get(f"/conversations/{conversation_id}/documents", headers=owner_headers()).json()
    assert [(d["filename"], d["status"], d["owner_kind"]) for d in listed] == [("payslip.pdf", "ready", "conversation")]
    assert any(key.endswith("document.md") for key in bucket_keys(s3))


def test_deleting_the_conversation_deletes_its_documents(test_client, chat):
    conversation_id, s3 = chat
    upload(test_client, conversation_id)

    assert test_client.delete(f"/conversations/{conversation_id}", headers=owner_headers()).status_code == 204

    assert bucket_keys(s3) == set()


def test_a_document_can_be_deleted_on_its_own(test_client, chat):
    conversation_id, s3 = chat
    document_id = upload(test_client, conversation_id).json()["document_id"]

    response = test_client.delete(f"/conversations/{conversation_id}/documents/{document_id}", headers=owner_headers())

    assert response.status_code == 204
    assert test_client.get(f"/conversations/{conversation_id}/documents", headers=owner_headers()).json() == []
    assert bucket_keys(s3) == set()


def test_someone_else_cant_reach_the_conversations_documents(test_client, chat):
    conversation_id, _ = chat
    stranger = owner_headers(TEST_USER_EMAIL_2)

    assert upload(test_client, conversation_id, headers=stranger).status_code == 404
    assert test_client.get(f"/conversations/{conversation_id}/documents", headers=stranger).status_code == 404
