from unittest.mock import patch

from fastapi.testclient import TestClient

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


def test_enquiry_is_emailed_to_the_inbox_with_reply_to_the_sender(test_client: TestClient):
    with patch("src.contact.router.send_email", return_value=True) as send:
        response = test_client.post("/contact/enquiry", json=valid_enquiry())

    assert response.status_code == 200
    to_email, subject, body = send.call_args.args
    assert to_email == ENQUIRY_INBOX
    assert subject == "New public-sector enquiry from Ada Lovelace"
    assert "Analytical Engines Ltd" in body
    assert send.call_args.kwargs["reply_to"] == "ada@example.com"


def test_honeypot_enquiry_is_accepted_but_not_sent(test_client: TestClient):
    with patch("src.contact.router.send_email") as send:
        response = test_client.post("/contact/enquiry", json=valid_enquiry(website="http://spam.example"))

    assert response.status_code == 200
    send.assert_not_called()


def test_enquiry_rejects_unknown_topic_and_short_message(test_client: TestClient):
    with patch("src.contact.router.send_email") as send:
        bad_topic = test_client.post("/contact/enquiry", json=valid_enquiry(topic="spam"))
        short_message = test_client.post("/contact/enquiry", json=valid_enquiry(message="Hi"))

    assert bad_topic.status_code == 422
    assert short_message.status_code == 422
    send.assert_not_called()


def test_second_enquiry_from_same_ip_is_rate_limited(test_client: TestClient):
    with patch("src.contact.router.send_email", return_value=True) as send:
        first = test_client.post("/contact/enquiry", json=valid_enquiry())
        second = test_client.post("/contact/enquiry", json=valid_enquiry())

    assert first.status_code == 200
    assert second.status_code == 429
    assert send.call_count == 1


def test_failed_email_reports_error_and_does_not_consume_rate_limit(test_client: TestClient):
    with patch("src.contact.router.send_email", return_value=False):
        failed = test_client.post("/contact/enquiry", json=valid_enquiry())
    with patch("src.contact.router.send_email", return_value=True):
        retry = test_client.post("/contact/enquiry", json=valid_enquiry())

    assert failed.status_code == 502
    assert ENQUIRY_INBOX in failed.json()["detail"]
    assert retry.status_code == 200
