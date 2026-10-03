from contextlib import contextmanager
from typing import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.contact.github_service import ENQUIRIES_REPO
from src.contact.router import ENQUIRY_INBOX


def valid_enquiry(**overrides: str) -> dict[str, str]:
    return {
        "name": "Ada Lovelace",
        "email": "ada@example.com",
        "organisation": "Analytical Engines Ltd",
        "topic": "public-sector",
        "message": "We are preparing a tender and would like a delivery partner.",
        **overrides,
    }


@contextmanager
def external_services(issue_error: Exception | None = None, email_sent: bool = True) -> Iterator[tuple[AsyncMock, MagicMock]]:
    create_issue = AsyncMock(return_value={"number": 7, "html_url": "https://github.com/x/y/issues/7"})
    if issue_error:
        create_issue.side_effect = issue_error
    with (
        patch("src.contact.router.GitHubService.create_issue", create_issue),
        patch("src.contact.router.send_email", return_value=email_sent) as send_email,
    ):
        yield create_issue, send_email


def test_enquiry_becomes_a_labelled_issue_in_the_private_repo(test_client: TestClient):
    with external_services() as (create_issue, _):
        response = test_client.post("/contact/enquiry", json=valid_enquiry())

    assert response.status_code == 200
    issue = create_issue.call_args.kwargs
    assert issue["repo"] == ENQUIRIES_REPO
    assert issue["title"] == "Enquiry from Ada Lovelace (Analytical Engines Ltd)"
    assert issue["labels"] == ["enquiry", "public-sector"]
    assert "Ada Lovelace <ada@example.com>" in issue["body"]
    assert "would like a delivery partner" in issue["body"]


def test_sender_gets_a_confirmation_email(test_client: TestClient):
    with external_services() as (_, send_email):
        test_client.post("/contact/enquiry", json=valid_enquiry())

    to_email, subject, body = send_email.call_args.args
    assert to_email == "ada@example.com"
    assert subject == "We've received your message"
    assert "a public-sector tender or contract" in body
    assert send_email.call_args.kwargs["reply_to"] == ENQUIRY_INBOX


def test_failed_confirmation_email_still_accepts_the_enquiry(test_client: TestClient):
    with external_services(email_sent=False):
        response = test_client.post("/contact/enquiry", json=valid_enquiry())

    assert response.status_code == 200


def test_honeypot_enquiry_is_accepted_but_not_recorded(test_client: TestClient):
    with external_services() as (create_issue, send_email):
        response = test_client.post("/contact/enquiry", json=valid_enquiry(website="http://spam.example"))

    assert response.status_code == 200
    create_issue.assert_not_called()
    send_email.assert_not_called()


def test_enquiry_rejects_unknown_topic_and_short_message(test_client: TestClient):
    with external_services() as (create_issue, _):
        bad_topic = test_client.post("/contact/enquiry", json=valid_enquiry(topic="spam"))
        short_message = test_client.post("/contact/enquiry", json=valid_enquiry(message="Hi"))

    assert bad_topic.status_code == 422
    assert short_message.status_code == 422
    create_issue.assert_not_called()


def test_second_enquiry_from_same_ip_is_rate_limited(test_client: TestClient):
    with external_services() as (create_issue, _):
        first = test_client.post("/contact/enquiry", json=valid_enquiry())
        second = test_client.post("/contact/enquiry", json=valid_enquiry())

    assert first.status_code == 200
    assert second.status_code == 429
    assert create_issue.call_count == 1


def test_failed_issue_reports_error_without_confirming_or_consuming_rate_limit(test_client: TestClient):
    with external_services(issue_error=RuntimeError("GitHub is down")) as (_, send_email):
        failed = test_client.post("/contact/enquiry", json=valid_enquiry())
    with external_services():
        retry = test_client.post("/contact/enquiry", json=valid_enquiry())

    assert failed.status_code == 502
    assert ENQUIRY_INBOX in failed.json()["detail"]
    send_email.assert_not_called()
    assert retry.status_code == 200
