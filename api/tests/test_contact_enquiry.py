from contextlib import contextmanager
from typing import Iterator
from unittest.mock import AsyncMock, MagicMock, patch

from fastapi.testclient import TestClient

from src.contact.github_service import ENQUIRIES_REPO, GitHubService
from src.contact.router import INNOMIGHT, INNOMIGHTLABS


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


def valid_submission(**overrides: str) -> dict[str, str]:
    return {
        "type": "sales",
        "subject": "Enterprise plan for 200 seats",
        "email": "grace@example.com",
        "description": "We would like to roll InnomightLabs out across our support team.",
        **overrides,
    }


def test_issues_go_to_the_private_enquiries_repo_by_default():
    assert GitHubService.create_issue.__defaults__ == (ENQUIRIES_REPO,)


def test_enquiry_becomes_a_labelled_issue(test_client: TestClient):
    with external_services() as (create_issue, _):
        response = test_client.post("/contact/enquiry", json=valid_enquiry())

    assert response.status_code == 200
    issue = create_issue.call_args.kwargs
    assert "repo" not in issue
    assert issue["title"] == "Enquiry from Ada Lovelace (Analytical Engines Ltd)"
    assert issue["labels"] == ["innomight", "public-sector"]
    assert "Ada Lovelace <ada@example.com>" in issue["body"]
    assert "would like a delivery partner" in issue["body"]


def test_innomight_inbox_is_notified_and_sender_confirmed(test_client: TestClient):
    with external_services() as (_, send_email):
        test_client.post("/contact/enquiry", json=valid_enquiry())

    notification, confirmation = send_email.call_args_list
    assert notification.args[0] == INNOMIGHT.inbox == "hello@innomight.com"
    assert notification.args[1] == "New enquiry (public-sector): Enquiry from Ada Lovelace (Analytical Engines Ltd)"
    assert "https://github.com/x/y/issues/7" in notification.args[2]
    assert notification.kwargs["reply_to"] == "ada@example.com"
    assert confirmation.args[0] == "ada@example.com"
    assert confirmation.args[1] == "We've received your message"
    assert "a public-sector tender or contract" in confirmation.args[2]
    assert confirmation.kwargs["reply_to"] == INNOMIGHT.inbox


def test_contact_form_message_becomes_a_labelled_issue(test_client: TestClient):
    with external_services() as (create_issue, _):
        response = test_client.post("/contact/submit", json=valid_submission())

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "Thanks for getting in touch. We'll reply within two working days."}
    issue = create_issue.call_args.kwargs
    assert "repo" not in issue
    assert issue["title"] == "Enterprise plan for 200 seats"
    assert issue["labels"] == ["innomightlabs", "sales"]
    assert "grace@example.com" in issue["body"]
    assert "innomightlabs.com contact form" in issue["body"]


def test_innomightlabs_inbox_is_notified_and_sender_confirmed(test_client: TestClient):
    with external_services() as (_, send_email):
        test_client.post("/contact/submit", json=valid_submission())

    notification, confirmation = send_email.call_args_list
    assert notification.args[0] == INNOMIGHTLABS.inbox == "hello@innomightlabs.com"
    assert notification.args[1] == "New enquiry (sales): Enterprise plan for 200 seats"
    assert notification.kwargs["reply_to"] == "grace@example.com"
    assert confirmation.args[0] == "grace@example.com"
    assert "Thanks for getting in touch with InnomightLabs" in confirmation.args[2]
    assert "roll InnomightLabs out" in confirmation.args[2]
    assert confirmation.kwargs["reply_to"] == INNOMIGHTLABS.inbox


def test_contact_form_rejects_an_unknown_category(test_client: TestClient):
    with external_services() as (create_issue, _):
        response = test_client.post("/contact/submit", json=valid_submission(type="spam"))

    assert response.status_code == 422
    create_issue.assert_not_called()


def test_both_forms_share_one_rate_limit(test_client: TestClient):
    with external_services() as (create_issue, _):
        first = test_client.post("/contact/submit", json=valid_submission())
        second = test_client.post("/contact/enquiry", json=valid_enquiry())

    assert first.status_code == 200
    assert second.status_code == 429
    assert create_issue.call_count == 1


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
    assert INNOMIGHT.inbox in failed.json()["detail"]
    send_email.assert_not_called()
    assert retry.status_code == 200


def test_both_emails_use_the_house_layout_with_the_innomight_logo(test_client: TestClient):
    from src.email.message import INNOMIGHT_WORDMARK_URL

    with external_services() as (_, send_email):
        test_client.post("/contact/submit", json=valid_submission())

    for sent in send_email.call_args_list:
        html = sent.kwargs["html"]
        assert INNOMIGHT_WORDMARK_URL in html
        assert "roll InnomightLabs out across our support team" in html
        assert "part of" in html
    assert "Open the issue" in send_email.call_args_list[0].kwargs["html"]


def test_a_senders_words_are_escaped_in_the_html(test_client: TestClient):
    attack = "<script>alert(1)</script> and a <a href='https://evil.example'>link</a>, then more words."

    with external_services() as (_, send_email):
        test_client.post("/contact/submit", json=valid_submission(description=attack))

    for sent in send_email.call_args_list:
        assert "<script>" not in sent.kwargs["html"]
        assert "&lt;script&gt;" in sent.kwargs["html"]
        assert "href='https://evil.example'" not in sent.kwargs["html"]


def test_innomight_emails_do_not_call_innomight_its_own_parent(test_client: TestClient):
    with external_services() as (_, send_email):
        test_client.post("/contact/enquiry", json=valid_enquiry())

    assert "part of" not in send_email.call_args_list[1].kwargs["html"]
