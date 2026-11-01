"""Reporting an agent's response (Google Play's AI-generated content policy)."""
import pytest
from fastapi.testclient import TestClient

from src.conversations.reports import ContentReportRepository
from src.messages.models import Message
from src.messages.repositories import get_message_repository
from tests.mock_data import AGENT_CREATE_REQUEST, CONVERSATION_CREATE_REQUEST, TEST_USER_EMAIL, user_id_for


@pytest.fixture
def emails(monkeypatch):
    sent: list[dict] = []
    monkeypatch.setattr(
        "src.conversations.reports.send_email",
        lambda to, subject, body, html=None, **_: sent.append({"to": to, "subject": subject, "body": body}) or True,
    )
    return sent


@pytest.fixture
def conversation(test_client: TestClient, auth_headers: dict) -> dict:
    agent_id = test_client.post("/agents", json=AGENT_CREATE_REQUEST, headers=auth_headers).json()["agent_id"]
    created = test_client.post(
        "/conversations/", json={**CONVERSATION_CREATE_REQUEST, "agent_id": agent_id}, headers=auth_headers
    ).json()
    repo = get_message_repository("dynamodb")
    question = repo.save(Message(conversation_id=created["conversation_id"], role="user", content="Tell me a joke"))
    answer = repo.save(Message(conversation_id=created["conversation_id"], role="assistant", content="A rude joke"))
    return {**created, "question_id": question.message_id, "answer_id": answer.message_id}


def report(test_client, auth_headers, conversation, message_id=None, **body):
    message_id = message_id or conversation["answer_id"]
    return test_client.post(
        f"/conversations/{conversation['conversation_id']}/messages/{message_id}/report",
        json={"reason": "offensive", **body}, headers=auth_headers,
    )


def test_a_reported_response_is_recorded_and_support_is_told(test_client, auth_headers, conversation, emails):
    response = report(test_client, auth_headers, conversation, note="Not okay")

    assert response.status_code == 200
    [stored] = ContentReportRepository().list_for_conversation(conversation["conversation_id"])
    assert (stored["reason"], stored["note"], stored["reporter_id"]) == ("offensive", "Not okay", user_id_for(TEST_USER_EMAIL))
    [email] = emails
    assert email["to"] == "hello@innomightlabs.com"
    assert "A rude joke" in email["body"] and "offensive" in email["subject"]


def test_reporting_the_same_response_twice_records_and_emails_once(test_client, auth_headers, conversation, emails):
    assert report(test_client, auth_headers, conversation).status_code == 200
    assert report(test_client, auth_headers, conversation, reason="harmful").status_code == 200

    assert len(ContentReportRepository().list_for_conversation(conversation["conversation_id"])) == 1
    assert len(emails) == 1


def test_only_an_agents_response_can_be_reported(test_client, auth_headers, conversation, emails):
    assert report(test_client, auth_headers, conversation, message_id=conversation["question_id"]).status_code == 404
    assert report(test_client, auth_headers, conversation, message_id="missing").status_code == 404
    assert report(test_client, auth_headers, conversation, reason="boring").status_code == 422
    assert emails == []


def test_reporting_requires_sign_in(test_client, conversation, emails):
    assert report(test_client, {}, conversation).status_code == 401


def test_deleting_the_conversation_deletes_its_reports(test_client, auth_headers, conversation, emails):
    report(test_client, auth_headers, conversation)

    assert test_client.delete(f"/conversations/{conversation['conversation_id']}", headers=auth_headers).status_code == 204
    assert ContentReportRepository().list_for_conversation(conversation["conversation_id"]) == []
